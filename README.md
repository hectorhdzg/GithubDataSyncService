# GitHub Data Sync Service

A Flask-based service that synchronizes GitHub issues and pull request metadata into a SQLite database and exposes that data through REST APIs. The project includes background automation, a static management UI, and setup scripts for bootstrapping the database.

## Features
- Synchronizes issues and pull requests for a configurable repository catalog stored in SQLite.
- REST endpoints for repository management, manual sync triggers, cached data access, and health monitoring.
- APScheduler background job that performs a full sync every two hours by default.
- Static management UI (in `src/ui`) served by the Flask app for quick manual operations.
- Setup scripts for creating the schema and seeding the default repository list.

## Project structure
- `src/app.py` – Flask application, sync logic, and API endpoints.
- `data/` – Default location for the SQLite database (`github_issues.db`) and rotating log (`sync-service.log`).
- `setup/setup.py` – Unified setup runner (schema + data in one step).
- `setup/setup_database.py` – Creates or upgrades the database schema.
- `setup/populate_repositories.py` – Seeds the repository table from `setup/data/repositories.json`.
- `setup/data/repositories.json` – Editable list of tracked repositories.
- `src/ui/` – Static HTML/JS assets for the management console.
- `tests/test_service.py` – 83 unit tests with mocked HTTP and isolated temp databases.
- `check_history.py` – Quick CLI utility to print recent sync history.

## Prerequisites
- Python 3.11 or newer (3.10 may work but is not validated).
- GitHub personal access token (optional but recommended for higher API limits).
- `sqlite3`, included with standard Python builds on Windows.

## Quick start
1. Create and activate a virtual environment:
  ```powershell
  python -m venv .venv
  .\.\.venv\Scripts\Activate.ps1
  ```
2. Install dependencies:
  ```powershell
  pip install -r requirements.txt
  ```
3. Prepare the database:
  ```powershell
  python setup\setup.py
  ```
  This creates the schema and seeds the default repository list in one step. You can also run `python setup\setup.py --schema` or `--data` individually.
4. Start the service:
  ```powershell
  python src\app.py
  ```
  The API listens on `http://localhost:8000` by default. Set `PORT` to override.
5. Open `http://localhost:8000/` to use the management UI, or call the REST endpoints directly.

## Environment variables
- `GITHUB_TOKEN` – Personal access token for authenticated GitHub requests.
- `DATABASE_PATH` – Override the default SQLite path. Defaults to `data/github_issues.db` locally or `/tmp/github_issues.db` on Azure.
- `PORT` – Port used by Flask (defaults to `8000`).
- `FLASK_DEBUG` – Set to `true` to enable Flask debug mode for local development.

## API overview

### Health and metadata
- `GET /health` – Service heartbeat and dependency status.
- `GET /api/stats` – Aggregated totals for issues, pull requests, and repositories.
- `GET /api/statistics` – Dashboard-friendly counts plus the last sync timestamp.
- `GET /api/data/freshness` – Last update timestamps per repository for issues and pull requests.
- `GET /api/sync/status` – Summary of the most recent sync session.

### Repository management
- `GET /api/repositories?includeInactive=true&includeFilters=true` – List repositories with optional inactive rows and JSON filters.
- `POST /api/repositories` – Add a repository. Required JSON keys: `repo`, `display_name`, `main_category`, `classification`, `priority`. Optional: `is_active`.
- `PUT /api/repositories/<owner/repo>` – Update repository metadata.
- `DELETE /api/repositories/<owner/repo>` – Remove a repository and associated sync metadata.
- `GET /api/repositories/<owner/repo>/filters` – Retrieve filter configuration.
- `PUT /api/repositories/<owner/repo>/filters` – Replace filter configuration (expects serializable JSON under the `filters` key).
- `GET /api/repositories/<owner/repo>/labels` – Get cached labels for a repository (pass `?force=true` to refresh from GitHub).

### Data retrieval
- `GET /api/issues?repository=<owner/repo>&state=<state>&limit=<n>` – Return cached issues. Parameters are optional; `limit` defaults to 10000.
- `GET /api/pull_requests?repository=<owner/repo>&state=<state>&limit=<n>` – Return cached pull requests. Parameters mirror the issues endpoint.

### Sync operations
- `POST /api/sync/repositories/<owner/repo>/issues` – Sync issues for a repository.
- `POST /api/sync/repositories/<owner/repo>/prs` – Sync pull requests for a repository.
- `POST /api/sync/repositories/<owner/repo>` – Sync issues and pull requests in a single session.
- `POST /api/sync/full` – Run a full sync across all active repositories.
- `GET /api/sync/history?limit=<n>` – Retrieve recent sync history entries (default limit is 20).
- `POST /api/sync/history/sample` – Insert sample sync history entries for demos.

### Automatic scheduler
- `GET /api/scheduler/status` – Inspect scheduler state, next run time, and job id.
- `POST /api/scheduler/enable` – Enable the automatic sync job.
- `POST /api/scheduler/disable` – Disable the job without shutting down the service.

## Logging and data
- Logs are stored in `data/sync-service.log` with rotation (10 MB per file, five backups).
- SQLite tables include `repositories`, `issues`, `pull_requests`, `sync_history`, `sync_metadata`, and `repository_labels`.
- Use `check_history.py` to print recent successful sync sessions from the database.

## Testing
- Run the test suite with pytest:
  ```powershell
  python -m pytest tests/test_service.py -v
  ```
- 83 unit tests cover endpoints, sync logic, normalization, filtering, and scheduling.
- All external HTTP calls are mocked; each test gets an isolated temporary database.

## Utilities
- All setup scripts (`setup/setup.py`, `setup_database.py`, `populate_repositories.py`) are idempotent and safe to rerun.
- Edit `setup/data/repositories.json` to add or modify the list of tracked repositories before running setup.

## Deployment notes
- Use a WSGI server such as Gunicorn in production (`gunicorn src.app:app`).
- Set `DATABASE_PATH` to a writable location in your hosting environment.
- When running on Azure App Service the application automatically stores the database under `/tmp/github_issues.db` and continues logging to `data/sync-service.log`.
