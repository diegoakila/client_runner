# Magpie Client Pipeline Runner

A local Streamlit UI for running Magpie's per-client BigQuery pipelines without touching the BigQuery console or hand-editing SQL. It lets a non-technical user pick a client, pick a month, preview the data that would be produced, and run it into that client's `_dev` table — with a mandatory dry-run step before anything is written, and no duplicates if you run the same month twice.

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
  - How many rows already exist in the destination table for that month (they'll be replaced, not duplicated)
  - A 50-row sample of the actual result
- **Delete-then-append, scoped to one month** — "Run" first deletes any existing rows for the selected month in the client's `_dev` table, then appends the fresh result. Running the same month twice never creates duplicates. Every other month in the table is left untouched — this is not a full-table overwrite.
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
5. If everything looks right, click **Run (Replace month in _dev)**. This deletes any existing rows for that month, then appends the fresh result into the client's `_dev` table.

If you change anything about the query, the client, or the month after a dry-run, the "Run" button is disabled again until you re-run the dry-run — this prevents running a query you never actually previewed.

## Manual runs from Colab

The Streamlit app is meant for interactive, one-off use. If you'd rather run a client manually from a Colab notebook (no local Python setup, no scheduling), use [`colab_runner.ipynb`](colab_runner.ipynb):

1. Open it in Colab (upload it, or open directly from GitHub via `File > Open notebook > GitHub` and paste the repo URL).
2. Run the cells top to bottom. The first cell clones this repo and authenticates using your own Google account via Colab's built-in auth flow (`google.colab.auth.authenticate_user()`) — no credentials are stored in the notebook.
3. Pick a client and month, review the dry-run output, then set `CONFIRM = True` in the last cell and re-run it to actually run (delete + append).

It reuses the exact same logic as the Streamlit app (both import `pipeline_core.py`), just with a notebook-shaped, step-by-step flow instead of a web UI — nothing is scheduled or automated.

The notebook also has an optional **section 7, batch mode**: dry-runs every client in `pipeline.client_query` for one chosen month, shows a summary table (rows to append, existing rows for that month per client), and runs (delete + append) all of them only after you set `BATCH_CONFIRM = True`. It skips the per-client 50-row sample and query editing from the single-client flow — use it when you want to run the same month for every client at once instead of one at a time.

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
  replace_month()
        ├── delete_existing_month() → DELETE FROM dest_table WHERE month = '<picked month>'
        └── append_to_dev()         → INSERT via WRITE_APPEND into dest_table
        │
  (if query was edited) save_edited_query() → new row in pipeline.client_query
```

The month-filter injection is deliberately generic: it works the same way regardless of how complex a client's underlying query is (single `SELECT`, multiple `UNION ALL` branches, nested CTEs, etc.), because it wraps the *entire* query as a subquery rather than trying to inject a `WHERE` clause into each branch.

## Current scope / known limitations

- **`_dev` only.** This tool currently only runs against `_dev` tables. Running into the production `_cross` tables is a deliberate next step, not yet implemented.
- **Delete + append is not atomic.** BigQuery has no cross-statement transactions here — the delete and the append are two separate jobs run back to back. If the append fails right after a successful delete, that month is left empty in the destination table until you re-run. This is judged an acceptable trade-off for a manual tool (dry-run makes failures unlikely, and re-running is always safe), but is worth knowing.
- **Single-project.** The BigQuery project (`sincere-hearth-273704`) is hardcoded in `pipeline_core.py`.

## Project structure

```
.
├── app.py               # Streamlit app (UI only)
├── pipeline_core.py      # Shared BigQuery logic (no Streamlit dependency)
├── colab_runner.ipynb    # Manual, notebook-based runner using pipeline_core.py
├── requirements.txt      # Python dependencies
├── CHANGELOG.md
└── README.md
```
