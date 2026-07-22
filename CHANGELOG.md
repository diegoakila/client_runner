# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Planned

- Support appending into the production `_cross` tables (currently `_dev` only).
- Optional hard block (not just a warning) when rows already exist for the selected month.

## [0.1.0] - 2026-07-22

### Added

- Initial version of the Magpie Client Pipeline Runner Streamlit app.
- Client picker sourced from `pipeline.client_query` (latest row per client).
- Month picker that scopes any stored query via `SELECT * FROM (<query>) WHERE month = '<month>'`.
- Editable query preview, with edited versions saved as new rows in `pipeline.client_query`.
- Mandatory dry-run step before running: estimated bytes processed, row count, existing-row-for-month check, and a 50-row sample.
- Append (not overwrite) into the client's `_dev` table.
- Generation history table per client.
