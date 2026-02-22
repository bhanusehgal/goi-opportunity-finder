# GoI Opportunity Finder

Production-ready Python pipeline that discovers Government of India opportunities (EOI/RFP/Tenders/Challenges), scores relevance for drones/robotics/IT, deduplicates, stores in SQLite, and emails a daily digest.

## Features

- Sources: CPPP/eProcure, GeM, iDEX
- Normalized schema with deterministic `unique_id`
- Hard filtering + weighted scoring
- Primary and fuzzy dedupe
- SQLite persistence for opportunities, runs, decisions
- Plaintext + HTML email digest with next-step recommendations
- Respectful scraping: low request rate, caching, retries, custom user-agent

## Project Layout

```text
goi-opportunity-finder/
  README.md
  requirements.txt
  .env.example
  config/
    keywords.yaml
    negatives.yaml
    buyers.yaml
  connectors/
    eprocure.py
    gem.py
    idex.py
  core/
    schema.py
    normalize.py
    scoring.py
    dedupe.py
    storage.py
    digest.py
    emailer.py
    logging_setup.py
  run_daily.py
  tests/
    test_scoring.py
    test_dedupe.py
    test_normalize.py
  data/
    cache/
    db.sqlite
```

## Setup

1. Create and activate virtual environment.
2. Install dependencies.
3. Configure environment variables.

```bash
cd goi-opportunity-finder
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

## Environment Configuration

Edit `.env`:

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
- `EMAIL_FROM`, `EMAIL_TO`
- `GOI_FINDER_USER_AGENT` (clear contact user-agent)
- `REQUEST_DELAY_SECONDS` (default 1.5)
- `ALLOW_NEGATIVE_WITH_PENALTY` (`true`/`false`)

No secrets are hardcoded in source.

## Run Locally

```bash
cd goi-opportunity-finder
python run_daily.py
```

Output artifacts:

- Logs: `data/finder.log`
- Cache: `data/cache/`
- SQLite DB: `data/db.sqlite`

## Static HTML Dashboard

Generate static dashboard data from SQLite:

```bash
cd goi-opportunity-finder
python export_static.py
```

Serve locally:

```bash
python -m http.server 8080 --directory web
```

Open `http://127.0.0.1:8080`.

## Netlify Deploy (API)

Set in `.env` or shell:

- `NETLIFY_AUTH_TOKEN` (required)
- `NETLIFY_SITE_ID` (optional, deploy to existing site)
- `NETLIFY_SITE_NAME` (optional, used when creating new site)

Then deploy:

```bash
cd goi-opportunity-finder
python export_static.py
python deploy_netlify.py
```

Repository auto-deploy is configured via `netlify.toml` at repo root (`build.command=python export_static.py`, `publish=web`).

## Tests

```bash
cd goi-opportunity-finder
pytest -q
```

## Cron (06:30 America/Chicago)

Add to crontab:

```cron
CRON_TZ=America/Chicago
30 6 * * * cd /path/to/goi-opportunity-finder && /path/to/venv/bin/python run_daily.py >> data/cron.log 2>&1
```

If running from Windows, schedule via WSL cron or Task Scheduler equivalent.

## Updating Relevance Rules

- `config/keywords.yaml`: add/remove positive domain terms, procurement terms, service/strict indicators.
- `config/buyers.yaml`: maintain high-probability buyer/org list with weights.
- `config/negatives.yaml`: tune noise filters.

## Respectful Scraping Notes

- Uses request delay (`REQUEST_DELAY_SECONDS`)
- Uses local HTML cache with freshness window
- Retries with fallback to stale cache and sample records
- Sends explicit user-agent
