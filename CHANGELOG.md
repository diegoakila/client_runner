# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- `pipeline_core.py`: extracted all BigQuery logic out of `app.py` into a Streamlit-independent module, so it can be reused elsewhere.
- `colab_runner.ipynb`: manual, notebook-based runner (no scheduling) that reuses `pipeline_core.py` for one-off runs from Colab, authenticating via `google.colab.auth.authenticate_user()`.
- `colab_runner.ipynb` section 7: optional batch mode that dry-runs and (after explicit confirmation) runs every client in `pipeline.client_query` for one chosen month in a single pass.

### Changed

- **Running is now delete-then-append, scoped to one month** (`pipeline_core.replace_month`), instead of a plain append. Running the same client + month twice no longer creates duplicates — the existing rows for that month are deleted first. Every other month in the destination table is untouched. Applies to both the Streamlit app and both flows in `colab_runner.ipynb` (single-client and batch mode). Verified against a real BigQuery table: running twice in a row leaves the row count unchanged instead of doubling.

### Planned

- Support running into the production `_cross` tables (currently `_dev` only).

## [0.1.0] - 2026-07-22

### Added

- Initial version of the Magpie Client Pipeline Runner Streamlit app.
- Client picker sourced from `pipeline.client_query` (latest row per client).
- Month picker that scopes any stored query via `SELECT * FROM (<query>) WHERE month = '<month>'`.
- Editable query preview, with edited versions saved as new rows in `pipeline.client_query`.
- Mandatory dry-run step before running: estimated bytes processed, row count, existing-row-for-month check, and a 50-row sample.
- Append (not overwrite) into the client's `_dev` table.
- Generation history table per client.
