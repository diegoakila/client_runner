"""
Local UI to run client pipelines (Magpie).

For each client (row in `pipeline.client_query`), lets a user:
  - pick which client to run
  - pick which month to append
  - preview / edit the underlying query
  - dry-run (row count + bytes estimate + sample) before committing
  - append the result into the client's `_dev` table

Auth: uses Application Default Credentials already set up on this machine
(gcloud auth application-default login). No credentials are entered in this app.

The BigQuery logic itself lives in `pipeline_core.py` (no Streamlit
dependency), so it can also be reused from a Colab notebook for manual runs.
"""

import datetime

import streamlit as st
from google.api_core.exceptions import GoogleAPIError

import pipeline_core as core

st.set_page_config(page_title="Magpie Client Pipeline Runner", layout="wide")


@st.cache_resource
def get_client():
    return core.get_client()


st.title("Magpie Client Pipeline Runner")
st.caption(
    "Pick a client, pick the month to append, preview/edit the query, dry-run it, then run. "
    "Run = append into that client's `_dev` table (not an overwrite)."
)

bq = get_client()

try:
    clients_df = core.load_clients(bq)
except GoogleAPIError as e:
    st.error(f"Failed to load the client list from `pipeline.client_query`: {e}")
    st.stop()

if clients_df.empty:
    st.warning("No rows found in `pipeline.client_query` yet.")
    st.stop()

col1, col2 = st.columns([2, 1])

client_options = clients_df["client"].tolist()
default_client = st.query_params.get("client")
default_index = client_options.index(default_client) if default_client in client_options else 0

with col1:
    client_name = st.selectbox("Client", client_options, index=default_index)
    st.query_params["client"] = client_name

row = clients_df[clients_df["client"] == client_name].iloc[0]
dataset = row["dataset"]
dest_table = row["dest_table"]
country = row["country"]
base_query = row["query"]
generated_at = row["generated_at"]

with col2:
    st.metric("Dataset", dataset)
    st.text(f"Dest table:\n{dest_table}")
    st.caption(f"Query last generated: {generated_at}")

month_date = st.date_input(
    "Month to append",
    value=datetime.date.today().replace(day=1),
    help="Used as the WHERE month = '<this date>' filter (day is always forced to the 1st).",
)
month_str = month_date.replace(day=1).isoformat()

st.subheader("Query (editable)")
edited_query = st.text_area("Base query", value=base_query, height=350)

query_changed = edited_query.strip() != base_query.strip()
if query_changed:
    st.info(
        "This query has been edited from the saved version. Running it will save the new "
        "version as a new row in `pipeline.client_query`."
    )

scoped_query = core.build_scoped_query(edited_query, month_str)

with st.expander("View scoped query (what actually gets executed)"):
    st.code(scoped_query, language="sql")

st.divider()

if "dry_run_ok" not in st.session_state:
    st.session_state.dry_run_ok = False
    st.session_state.dry_run_signature = None

current_signature = (client_name, month_str, edited_query)

btn_col1, btn_col2 = st.columns(2)

with btn_col1:
    if st.button("Dry Run (Preview)", type="secondary"):
        with st.spinner("Running dry-run..."):
            try:
                bytes_processed = core.dry_run(bq, scoped_query)
                n_rows = core.row_count(bq, scoped_query)
                existing_n = core.existing_month_count(bq, dest_table, month_str)
                sample_df = core.preview_rows(bq, scoped_query, limit=50)

                st.session_state.dry_run_ok = True
                st.session_state.dry_run_signature = current_signature
                st.session_state.dry_run_bytes = bytes_processed
                st.session_state.dry_run_rows = n_rows
                st.session_state.dry_run_existing = existing_n
                st.session_state.dry_run_sample = sample_df
            except GoogleAPIError as e:
                st.session_state.dry_run_ok = False
                st.error(f"Dry-run failed: {e}")

if st.session_state.dry_run_ok and st.session_state.dry_run_signature == current_signature:
    mb = st.session_state.dry_run_bytes / (1024 ** 2)
    m1, m2, m3 = st.columns(3)
    m1.metric("Estimated data processed", f"{mb:,.1f} MB")
    m2.metric("Rows to be appended", f"{st.session_state.dry_run_rows:,}")
    if st.session_state.dry_run_existing > 0:
        m3.metric(
            f"Existing rows for {month_str} in dest",
            f"{st.session_state.dry_run_existing:,}",
            delta="check for duplicates!",
            delta_color="inverse",
        )
    elif st.session_state.dry_run_existing == 0:
        m3.metric(f"Existing rows for {month_str} in dest", "0")
    else:
        m3.metric("Existing rows", "N/A")

    if st.session_state.dry_run_existing > 0:
        st.warning(
            f"There are already {st.session_state.dry_run_existing:,} rows for month {month_str} "
            f"in `{dest_table}`. If you proceed, this month's data will be duplicated "
            "(append does not delete existing data)."
        )

    st.write("Sample result (first 50 rows):")
    st.dataframe(st.session_state.dry_run_sample, use_container_width=True)

    with btn_col2:
        if st.button("Run (Append to _dev)", type="primary"):
            with st.spinner("Running append..."):
                try:
                    if query_changed:
                        core.save_edited_query(bq, client_name, country, dataset, dest_table, edited_query)
                        st.toast("Edited query saved as a new row in pipeline.client_query")

                    job = core.append_to_dev(bq, scoped_query, dest_table)
                    st.success(
                        f"Successfully appended "
                        f"{job.num_dml_affected_rows if job.num_dml_affected_rows is not None else st.session_state.dry_run_rows:,} "
                        f"rows into `{dest_table}` for month {month_str}."
                    )
                    st.session_state.dry_run_ok = False
                except GoogleAPIError as e:
                    st.error(f"Run failed: {e}")
else:
    with btn_col2:
        st.button(
            "Run (Append to _dev)",
            type="primary",
            disabled=True,
            help="Run Dry Run first (and make sure the query/month haven't changed since the dry-run).",
        )

st.divider()
st.subheader(f"Generation history for `{client_name}`")
st.dataframe(core.load_history(bq, client_name), use_container_width=True)
