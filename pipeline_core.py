"""
Shared BigQuery logic for the Magpie Client Pipeline Runner.

This module has no Streamlit dependency so it can be imported both by the
local Streamlit app (`app.py`) and from a Colab notebook for manual,
one-off runs.

Auth is the caller's responsibility: pass in an already-authenticated
`bigquery.Client`. Locally that's Application Default Credentials
(`gcloud auth application-default login`); in Colab that's
`google.colab.auth.authenticate_user()`.
"""

import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPIError

PROJECT_ID = "sincere-hearth-273704"
CLIENT_QUERY_TABLE = f"{PROJECT_ID}.pipeline.client_query"


def get_client(project_id: str = PROJECT_ID) -> bigquery.Client:
    return bigquery.Client(project=project_id)


def load_clients(client: bigquery.Client) -> pd.DataFrame:
    """Latest generated row per client, i.e. the current query/config for each client."""
    query = f"""
        SELECT client, country, dataset, dest_table, query, generated_at
        FROM `{CLIENT_QUERY_TABLE}`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY client ORDER BY generated_at DESC) = 1
        ORDER BY client
    """
    return client.query(query).to_dataframe()


def load_history(client: bigquery.Client, client_name: str) -> pd.DataFrame:
    query = f"""
        SELECT generated_at, dest_table, LENGTH(query) AS query_len
        FROM `{CLIENT_QUERY_TABLE}`
        WHERE client = @client_name
        ORDER BY generated_at DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("client_name", "STRING", client_name)]
    )
    return client.query(query, job_config=job_config).to_dataframe()


def build_scoped_query(base_query: str, month_str: str) -> str:
    """Wrap a stored (full-history) query so it only returns rows for one month.

    Works regardless of how complex the underlying query is (single SELECT,
    multiple UNION ALL branches, nested CTEs, ...) because it scopes the
    *entire* query as a subquery instead of injecting a WHERE clause into
    each branch.
    """
    trimmed = base_query.strip().rstrip(";")
    return f"SELECT * FROM (\n{trimmed}\n) WHERE month = '{month_str}'"


def dry_run(client: bigquery.Client, scoped_query: str) -> int:
    """Return BigQuery's estimated bytes processed, without running the query for real."""
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    job = client.query(scoped_query, job_config=job_config)
    return job.total_bytes_processed


def preview_rows(client: bigquery.Client, scoped_query: str, limit: int = 50) -> pd.DataFrame:
    return client.query(f"{scoped_query}\nLIMIT {limit}").to_dataframe()


def row_count(client: bigquery.Client, scoped_query: str) -> int:
    df = client.query(f"SELECT COUNT(*) AS n FROM (\n{scoped_query}\n)").to_dataframe()
    return int(df["n"].iloc[0])


def existing_month_count(client: bigquery.Client, dest_table: str, month_str: str) -> int:
    """Rows already present in dest_table for month_str. -1 if the check itself failed."""
    query = f"SELECT COUNT(*) AS n FROM `{dest_table}` WHERE month = '{month_str}'"
    try:
        df = client.query(query).to_dataframe()
        return int(df["n"].iloc[0])
    except GoogleAPIError:
        return -1  # table doesn't exist yet, or column missing


def save_edited_query(
    client: bigquery.Client,
    client_name: str,
    country: str,
    dataset: str,
    dest_table: str,
    edited_query: str,
) -> None:
    """Insert a new row into pipeline.client_query, keeping the previous rows as history."""
    query = f"""
        INSERT INTO `{CLIENT_QUERY_TABLE}` (client, country, dataset, dest_table, generated_at, query)
        VALUES (@client_name, @country, @dataset, @dest_table, CURRENT_TIMESTAMP(), @query)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("client_name", "STRING", client_name),
            bigquery.ScalarQueryParameter("country", "STRING", country),
            bigquery.ScalarQueryParameter("dataset", "STRING", dataset),
            bigquery.ScalarQueryParameter("dest_table", "STRING", dest_table),
            bigquery.ScalarQueryParameter("query", "STRING", edited_query),
        ]
    )
    client.query(query, job_config=job_config).result()


def delete_existing_month(client: bigquery.Client, dest_table: str, month_str: str) -> int:
    """Delete rows for month_str from dest_table.

    Returns the number of rows deleted, or -1 if dest_table doesn't exist yet
    (nothing to delete — the table will simply be created on the following append).
    """
    query = f"DELETE FROM `{dest_table}` WHERE month = '{month_str}'"
    try:
        job = client.query(query)
        job.result()
        return job.num_dml_affected_rows or 0
    except GoogleAPIError:
        return -1


def append_to_dev(client: bigquery.Client, scoped_query: str, dest_table: str):
    """Run scoped_query and append (WRITE_APPEND) its result into dest_table."""
    job_config = bigquery.QueryJobConfig(
        destination=dest_table,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.query(scoped_query, job_config=job_config)
    job.result()
    return job


def replace_month(client: bigquery.Client, scoped_query: str, dest_table: str, month_str: str):
    """Delete existing rows for month_str in dest_table, then append scoped_query's result.

    This guarantees no duplicates within a single month while leaving every
    other month in dest_table untouched (it is not a full-table overwrite).
    Returns (rows_deleted, append_job).
    """
    rows_deleted = delete_existing_month(client, dest_table, month_str)
    job = append_to_dev(client, scoped_query, dest_table)
    return rows_deleted, job
