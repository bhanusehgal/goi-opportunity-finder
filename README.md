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
- `PUBLISHED_FROM`, `PUBLISHED_TO` (optional default date window in `YYYY-MM-DD`)
- `EPROCURE_MAX_PAGES` (optional pagination cap for range backfills)

No secrets are hardcoded in source.

## Run Locally

```bash
cd goi-opportunity-finder
python run_daily.py
```

Date-range crawl example (first two months of 2026):

```bash
cd goi-opportunity-finder
python run_daily.py --published-from 2026-01-01 --published-to 2026-02-29
python export_static.py
```

In date-range mode, eProcure paginates page-by-page and stops when `e-Published Date` goes older than `--published-from`.
Optional safety cap: `--eprocure-max-pages 500`.

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

### Live Refresh Button (Hosted Netlify Site)

The dashboard includes:

- `Refresh Live Sources`: triggers a new Netlify build
- `Set Build Hook`: saves your Netlify build-hook URL in browser local storage

Setup once:

1. In Netlify UI: `Site configuration` -> `Build & deploy` -> `Build hooks`
2. Create a hook (for your production branch, usually `main`)
3. Open your hosted dashboard and click `Set Build Hook`
4. Paste the build-hook URL

Then click `Refresh Live Sources` any time. The page will poll `opportunities.json` and auto-update when the new crawl is published.

You can also use `Published from` and `Published to` fields in the dashboard to filter rendered opportunities by published date.

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

Repository auto-deploy is configured via `netlify.toml` at repo root (`build.command=python run_daily.py && python export_static.py`, `publish=web`).

## Auto Push To GitHub

Manual one-time push:

```bash
cd goi-opportunity-finder
git add README.md netlify.toml web/index.html web/styles.css web/app.js .gitignore scripts/auto_publish.py
git commit -m "Add refresh controls and auto-publish helper"
git push origin main
```

Automated local publish loop (no PAT required, uses your existing GitHub auth):

```bash
cd goi-opportunity-finder
python scripts/auto_publish.py --watch
```

Behavior:

- Polls every 20 seconds
- Auto-commits and pushes eligible code/config changes
- Skips runtime files like `data/`, `__pycache__/`, `.env`, and `$null`
- Each push triggers Netlify auto-deploy (if site is linked to GitHub)

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

Fallback sample records are marked as inactive mock entries and excluded from live dashboard output. This prevents broken placeholder links from appearing as real opportunities.
