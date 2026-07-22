# Magpie Client Pipeline Runner

A local Streamlit UI for running Magpie's per-client BigQuery pipelines without touching the BigQuery console or hand-editing SQL. It lets a non-technical user pick a client, pick a month, preview the data that would be produced, and append it into that client's `_dev` table — with a mandatory dry-run step before anything is written.

## Background

Each client (e.g. `leekumkee`, `hanasui`, `rb`, `soho`, ...) has a BigQuery SQL query that builds its master table by combining one or more category-level source tables, applying client-specific business rules (brand normalization, category remapping, pricing tiers, etc.). These queries are stored as rows in `pipeline.client_query` (project `sincere-hearth-273704`), one row per generation, with the most recent row per client being the "current" version.

Historically, running one of these queries meant:
1. Opening the BigQuery console
2. Finding the right saved query
3. Manually editing the month filter
4. Running it and hoping the destination table is correct

This tool replaces that manual process with a small, safe, reviewable UI.

## Features

- **Client picker** — lists every client with a row in `pipeline.client_query`, loading its latest generated query, target dataset, and destination (`_dev`) table.
- **Month picker** — the query stored in `pipeline.client_query` has no month filter baked in (it selects full history); this tool wraps it as `SELECT * FROM (<query>) WHERE month = '<picked month>'` at run time.
- **Query preview & editing** — the full query is shown in an editable text area so you can tweak it before running. If you run an edited query, the edited version is saved as a new row in `pipeline.client_query` (keeping a full history of what actually ran).
- **Mandatory dry-run** — before the "Run" button is enabled, you must dry-run the scoped query. Dry-run shows:
  - Estimated bytes processed (BigQuery dry-run estimate)
  - Row count that would be appended
  - How many rows already exist in the destination table for that month (a duplicate-append warning)
  - A 50-row sample of the actual result
- **Append, not overwrite** — "Run" appends into the client's `_dev` table (`WRITE_APPEND`). It never truncates or replaces existing data.
- **Generation history** — a table at the bottom shows every past row in `pipeline.client_query` for the selected client, so you can see when it was last (re)generated and how large the query is.

## Prerequisites

- Python 3.8 or newer
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`) installed
- BigQuery access to the `sincere-hearth-273704` project
- Application Default Credentials configured on your machine:

  ```bash
  gcloud auth application-default login
  ```

  This tool never asks for or stores credentials itself — it relies entirely on ADC already set up via the command above.

## Installation

```bash
git clone https://github.com/diegoakila/client_runner.git
cd client_runner
pip install -r requirements.txt
```

## Usage

```bash
streamlit run app.py
```

This opens the app in your browser at `http://localhost:8501`.

1. **Pick a client** from the dropdown (also selectable via URL, e.g. `?client=leekumkee`).
2. **Pick the month** you want to append.
3. **Review or edit the query** in the text box. Expand "View scoped query" to see exactly what will run, including the injected month filter.
4. Click **Dry Run (Preview)**. Check the estimated bytes processed, row count, and — importantly — whether rows for that month already exist in the destination table.
5. If everything looks right, click **Run (Append to _dev)**. This appends the result into the client's `_dev` table.

If you change anything about the query, the client, or the month after a dry-run, the "Run" button is disabled again until you re-run the dry-run — this prevents running a query you never actually previewed.

## How it works

```
pipeline.client_query (BigQuery table)
  columns: client, country, dataset, dest_table, generated_at, query
        │
        ▼
  load latest row per client
        │
        ▼
  wrap: SELECT * FROM (<query>) WHERE month = '<picked month>'
        │
        ├── dry_run()          → estimated bytes processed
        ├── row_count()        → rows that would be appended
        ├── existing_month_count() → rows already in dest_table for that month
        ├── preview_rows()     → 50-row sample
        │
        ▼ (on confirmed Run)
  append_to_dev()  → INSERT via WRITE_APPEND into dest_table
        │
  (if query was edited) save_edited_query() → new row in pipeline.client_query
```

The month-filter injection is deliberately generic: it works the same way regardless of how complex a client's underlying query is (single `SELECT`, multiple `UNION ALL` branches, nested CTEs, etc.), because it wraps the *entire* query as a subquery rather than trying to inject a `WHERE` clause into each branch.

## Current scope / known limitations

- **`_dev` only.** This tool currently only appends into `_dev` tables. Appending into the production `_cross` tables is a deliberate next step, not yet implemented.
- **No automatic duplicate prevention.** The dry-run step warns you if rows already exist for the selected month in the destination table, but it does not block the run — it's on the user to decide.
- **Single-project.** The BigQuery project (`sincere-hearth-273704`) is hardcoded in `app.py`.

## Project structure

```
.
├── app.py             # Streamlit app
├── requirements.txt    # Python dependencies
└── README.md
```
