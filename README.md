# Zero-Cost News Monitor

Production-ready v1 Python project for collecting, filtering, deduplicating, scoring, summarizing, and pushing important news into a WeCom group robot webhook.

## Scope

- Runtime cost: zero
- No paid APIs in runtime
- No LLM inference in runtime
- Chinese and English content supported
- Production v1 sources: YouTube fixed channels, Eastmoney public pages, RSS feeds, configurable public HTML pages
- X/Twitter: placeholder module only
- Weibo: intentionally excluded in v1
- Delivery: WeCom group robot webhook
- Stack: FastAPI, SQLite, requests/httpx, BeautifulSoup, feedparser

## Project Tree

```text
.
├── .env.example
├── .github
│   └── workflows
│       ├── digest.yml
│       └── pipeline.yml
├── README.md
├── api
│   ├── __init__.py
│   ├── server.py
│   └── youtube_webhook.py
├── config
│   ├── __init__.py
│   ├── keywords.yaml
│   ├── settings.py
│   ├── sources.yaml
│   └── tickers.yaml
├── data
│   └── .gitkeep
├── dedup
│   ├── __init__.py
│   └── dedup.py
├── digest
│   ├── __init__.py
│   └── builder.py
├── ingest
│   ├── __init__.py
│   ├── eastmoney_ingest.py
│   ├── rss_ingest.py
│   ├── site_ingest.py
│   ├── x_ingest.py
│   └── youtube_ingest.py
├── jobs
│   ├── __init__.py
│   ├── run_pipeline.py
│   ├── schedule_utils.py
│   └── send_digest.py
├── logs
│   └── .gitkeep
├── normalize
│   ├── __init__.py
│   └── schema.py
├── notify
│   ├── __init__.py
│   └── wecom.py
├── pyproject.toml
├── score
│   ├── __init__.py
│   └── scorer.py
├── scripts
│   ├── __init__.py
│   └── test_wecom.py
├── storage
│   ├── __init__.py
│   └── db.py
└── tests
    ├── __init__.py
    ├── test_dedup.py
    └── test_scorer.py
```

## Setup

### Option A: pip

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[dev]
```

PowerShell alternative:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .[dev]
```

### Option B: uv

```bash
uv venv
uv sync --extra dev
```

### Environment Variables

Copy the example file and update the values you need:

```bash
cp .env.example .env
```

PowerShell alternative:

```powershell
Copy-Item .env.example .env
```

Important variables:

- `WECOM_WEBHOOK_URL`: required for push delivery
- `NEWS_DB_PATH`: SQLite database path, defaults to `data/news_monitor.db`
- `PIPELINE_SCHEDULE_TIMEZONE`: defaults to `Asia/Shanghai`
- `URGENT_THRESHOLD`: immediate alert threshold
- `DIGEST_MIN_SCORE`: scheduled digest minimum score threshold
- `TITLE_SIMILARITY_THRESHOLD`: title-based dedup threshold
- `YOUTUBE_VERIFY_TOKEN`: used by `GET /youtube/webhook`
- `YOUTUBE_WEBHOOK_CALLBACK_URL`: public callback URL if you expose the webhook

## Local Run

### Start API

```bash
python -m api.server
```

Available endpoints:

- `GET /health`
- `GET /youtube/webhook`
- `POST /youtube/webhook`
- `POST /run-pipeline`
- `POST /send-digest`

### Run pipeline once

```bash
python -m jobs.run_pipeline --force
```

### Run digest once

```bash
python -m jobs.send_digest --force
```

### Test the WeCom webhook

```bash
python -m scripts.test_wecom --message "Webhook test from local machine."
```

### Run tests

```bash
pytest
```

## Schedule

The business schedule is implemented in code with timezone-aware gating:

- Every 30 minutes from `05:00` to `14:30` in `Asia/Shanghai`
- Every 2 hours at `15:00`, `17:00`, `19:00`, `21:00`, `23:00`, `01:00`, `03:00` in `Asia/Shanghai`

This is important because GitHub Actions cron is UTC-only and does not natively support named time zones.

## GitHub Actions Setup

Two workflows are included:

- `.github/workflows/pipeline.yml`
- `.github/workflows/digest.yml`
- `.github/workflows/wecom-test.yml`

### Recommended repository secrets

- `WECOM_WEBHOOK_URL`
- `YOUTUBE_VERIFY_TOKEN`
- `YOUTUBE_WEBHOOK_SECRET`
- `YOUTUBE_WEBHOOK_CALLBACK_URL`

### How scheduling works in GitHub Actions

`pipeline.yml` runs every 30 minutes in UTC and then lets Python decide whether the current time matches the `Asia/Shanghai` business schedule.

During a scheduled run, `pipeline.yml` now does both steps in one job:

- collect and score new items
- send the digest from the same SQLite state

This avoids cache races between separate scheduled workflows that would otherwise restore and save different copies of the SQLite file.

`digest.yml` is kept as a manual workflow for troubleshooting or on-demand sending.

### First GitHub bootstrap

For the very first manual GitHub run, use the `Pipeline` workflow with `bootstrap=true`.

That mode will:

- collect and score items
- store them in SQLite cache
- suppress urgent pushes
- mark the collected baseline as already sent

After that, scheduled runs can continue normally without replaying the initial backlog into WeCom.

### SQLite state in GitHub Actions

GitHub-hosted runners are ephemeral, so the workflows restore and save `data/news_monitor.db` through the GitHub cache action. This is a practical zero-cost v1 approach, but it is still best-effort persistence rather than durable database hosting.

## WeCom Group Robot Setup

1. Create a group robot in your WeCom group.
2. Copy the webhook URL.
3. Put it into `.env` or GitHub secret `WECOM_WEBHOOK_URL`.
4. Run `python -m scripts.test_wecom` to validate delivery.

Supported formats:

- `markdown`
- `text`

Long digests are chunked into multiple messages before sending.

## How To Add Sources

All source definitions live in `config/sources.yaml`.

### YouTube

Add a channel entry under `youtube.channels`:

```yaml
- id: UCxxxxxxxxxxxxxxxxxxxxxx
  name: Example Channel
  enabled: true
  official: true
  tags: [international-ai, official]
```

The project supports:

- RSS polling fallback for fixed channel IDs
- Webhook receiving through `POST /youtube/webhook`
- Webhook verification through `GET /youtube/webhook`

### Eastmoney

Add or edit pages under `eastmoney.pages`.

Each page can define:

- `url`
- `adapter`
- `enabled`
- `base_url`
- `selectors`
- `tags`

Eastmoney layouts vary, so the parser is adapter-based and selector-driven on purpose.

### RSS

Add entries under `rss.feeds`.

### Public HTML pages

Add entries under `sites.pages` and choose a supported adapter.

## Normalization Schema

Each item is normalized to:

- `id`
- `source`
- `source_type`
- `title`
- `body`
- `url`
- `author`
- `published_at`
- `fetched_at`
- `language`
- `tags`
- `symbols`
- `score`
- `score_reasons`
- `is_urgent`
- `fingerprint`

All items are stored in SQLite, and sent items are tracked separately to avoid duplicate pushes.

## Deduplication

Dedup runs in two passes:

1. Normalize and compare URLs first
2. Compare title similarity second

The URL normalizer strips common tracking parameters such as `utm_*`, `fbclid`, and fragments.

The title matcher uses a simple configurable similarity threshold from `.env`:

- `TITLE_SIMILARITY_THRESHOLD`

## Scoring

Scoring is rule-based only in v1.

Configured dimensions:

- keyword weights
- source type weights
- source name weights
- ticker and company alias weights
- urgency keyword boosts
- recency boosts
- official source boosts
- duplicate penalties

The score output includes:

- total score
- reasons list
- urgent boolean

All rules live in:

- `config/keywords.yaml`
- `config/tickers.yaml`

## Digest Output

Each digest row includes:

- title
- source
- time
- one-line Chinese summary
- one-line English summary
- impacted assets and tags
- score
- link

Summaries are template-based and heuristic-only. No external AI APIs are used.

## Known Limitations

- X/Twitter is a placeholder only in v1.
- Weibo is intentionally excluded in v1.
- GitHub Actions persistence for SQLite is best-effort via cache, not a real database.
- HTML selectors for Eastmoney and public sites may need adjustment over time.
- YouTube webhook receiving requires a public callback URL if you want push instead of polling.
- There is no browser automation or login flow in v1; only public pages and feeds are supported.

## Design Principles

- Prefer reliability over sophistication
- Keep everything configurable
- Keep runtime cost at zero
- Avoid runtime dependency on paid APIs and LLMs
- Keep the code modular and easy to extend in v2
