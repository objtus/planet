# CLAUDE.md — Planet Codebase Guide

This file provides essential context for AI assistants working on the **Planet** project — a personal lifelogging system that collects, stores, and summarizes data from multiple social and health sources.

---

## Project Overview

Planet is a self-hosted personal data aggregator running on Ubuntu 24.04. It:
- Collects data from 17+ sources (Misskey, Mastodon, Last.fm, GitHub, YouTube, weather, iPhone health, Scrapbox, etc.)
- Stores everything in a PostgreSQL database
- Generates AI-written summaries via Ollama (gemma3:12b)
- Exposes a private Flask dashboard (Tailscale-only, port 5000)

**Current Phase**: Phase 6 (AI summaries & Neocities publishing) — M1/M2 complete, M3–M6 in progress.

---

## Repository Structure

```
planet/
├── collectors/          # Data collection scripts (one per source type)
├── importers/           # One-time historical JSON importers
├── ingest/              # Flask API endpoints for iPhone health/photo data
├── summarizer/          # AI summary generation (Ollama)
│   ├── generate.py      # Main CLI entry point (~848 lines)
│   └── prompts/         # Markdown prompt templates with {{PLACEHOLDER}} syntax
├── publisher/           # planet-feed JSON (`python -m publisher.build_feed`) — Neocities summary HTML (M4) TBD
├── dashboard/           # Flask web UI
│   ├── app.py           # Core Flask application (~1,167 lines)
│   ├── static/          # CSS, JS, bundled libraries (Chart.js, marked, DOMPurify)
│   └── templates/       # Jinja2 HTML templates (7 files)
├── db/
│   └── schema.sql       # PostgreSQL schema (source of truth for DB structure)
├── cron/
│   └── crontab.txt      # Cron job definitions
├── docs/                # Comprehensive markdown documentation
│   ├── overview.md
│   ├── current_state.md # Phase/milestone completion status
│   ├── design.md        # Architecture & schema details (19KB)
│   ├── setup.md         # Installation & configuration guide
│   └── api/             # Per-source API reference docs
├── config/              # Gitignored — contains settings.toml with secrets
├── collect_all.py       # Unified runner for all collectors
└── mockup/              # UI design mockups
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12.3 |
| Web framework | Flask |
| Database | PostgreSQL 16 + pg_bigm extension |
| LLM | Ollama (`gemma3:12b`) at `localhost:11434` |
| Frontend | Jinja2 templates, Chart.js, vanilla JS |
| Network access | Tailscale VPN (no public exposure) |
| Hosting | Self-hosted Ubuntu 24.04 server |
| Backup | pCloud via rclone |

**Python dependencies** (installed in `./venv` via pip):
```
flask psycopg2-binary requests feedparser beautifulsoup4 pylast tomllib
```

---

## Configuration

All secrets live in **`config/settings.toml`** (gitignored). A template is at `config/settings.toml.example`.

Sections:
- `[database]` — PostgreSQL connection (host, port, user, password, dbname)
- `[ollama]` — `base_url`, `model`
- `[flask]` — `secret_key`
- `[weather]` — lat/lon for Nagoya
- `[lastfm]` — API key & username
- `[github]` — PAT token & username
- `[youtube]` — API key & channel ID
- `[neocities]` — API key
- `[planet_feed]` — optional `repo_path`, `push` for `publisher.build_feed` (see `docs/planet_feed_setup.md`)
- Per-source Misskey/Mastodon tokens

Load config with `tomllib` (Python 3.11+ stdlib):
```python
import tomllib
with open("config/settings.toml", "rb") as f:
    config = tomllib.load(f)
```

---

## Database Schema

Schema is defined in `db/schema.sql`. Always treat this file as the source of truth.

### Core tables

**`data_sources`** — Registry of all 17 data sources
- `id, name, type, base_url, account, config (JSONB), is_active, sort_order, short_name`

**`logs`** — Unified timeline (36,000+ rows)
- `id, source_id, original_id, content, url, metadata (JSONB), is_deleted, timestamp, created_at`
- Indexes on `timestamp`, `source_id`, `metadata`, and FTS (`idx_logs_content_fts` via pg_bigm)

**Source-specific tables** (detailed stats alongside `logs`):
- `misskey_posts` — `post_id, text, cw, reply/renote/reaction counts, visibility, posted_at`
- `mastodon_posts` — `post_id, content, spoiler_text, replies/reblogs/favourites, visibility, posted_at`
- `lastfm_plays` — `track_id, artist, track, album, played_at`
- `youtube_videos` — `video_id, title, duration_sec, view_count, like_count`
- `weather_daily` — `date, temp_max/min/avg, weather_main, humidity`
- `github_activity` — `event_id, event_type, repo_name, commit_count, occurred_at`
- `health_daily` — `date, steps, active_calories, heart_rate_*, exercise_minutes, stand_hours`
- `rss_entries` — `entry_id, title, url, summary, published_at`
- `scrapbox_pages` — `page_title, content, content_plain`

**`url_metadata`** — OGP/Open Graph cache
**`summaries`** — AI-generated summaries (`period_type`, `period_start`, `period_end`, `content`, `model`, `is_published`)

### Key schema conventions

- **Timestamps**: `TIMESTAMPTZ` always; store in UTC, display in JST (UTC+9)
- **Soft deletes**: `is_deleted BOOLEAN` flag — never physically delete log rows
- **Transactional writes**: always write to both `logs` and the source-specific table in one transaction
- **JSONB metadata**: source-specific fields go in `logs.metadata` for the unified timeline
- **Japanese FTS**: pg_bigm 2-gram index on `logs.content` for Japanese full-text search

---

## Development Workflow

### Environment setup

```bash
# Activate virtual environment
source venv/bin/activate

# Run the dashboard locally
python dashboard/app.py

# Run a single collector
python -m collectors.misskey
python -m collectors.lastfm

# Run all collectors
python collect_all.py

# Generate a summary (dry run first)
python -m summarizer.generate --period week --date 2025-W52 --dry-run
python -m summarizer.generate --period week --date 2025-W52
python -m summarizer.generate --period month --date 2025-12
python -m summarizer.generate --period day --date 2025-12-31

# Planet feed JSON → ~/planet-feed (see docs/planet_feed_setup.md)
python -m publisher.build_feed --dry-run
python -m publisher.build_feed --no-push
```

### Service management (production)

```bash
sudo systemctl start planet-dashboard.service
sudo systemctl status planet-dashboard.service
journalctl -u planet-dashboard.service -f
```

### Cron schedule (`cron/crontab.txt`)

| Schedule | Command |
|---|---|
| Every hour (`:00`) | `collectors.misskey` |
| Every hour (`:05`) | `collectors.mastodon` |
| Every hour (`:10`) | `collectors.lastfm` |
| Daily 6 AM JST (`:00`) | `collectors.weather` |
| Daily 6 AM JST (`:05`) | `collectors.github` |
| Daily 6 AM JST (`:10`) | `collectors.rss` |
| Daily 6 AM JST (`:15`) | `collectors.youtube` |
| Daily 6 AM JST (`:20`) | `collectors.scrapbox` |

---

## Code Conventions

### Collectors

Each collector lives in `collectors/<source>.py` and follows a consistent pattern:
- Inherits from `BaseCollector` (or mirrors its interface)
- Implements a `collect()` method
- Reads config from `config/settings.toml`
- Writes atomically to both `logs` and its source-specific table
- Uses `ON CONFLICT DO UPDATE` (upsert) to handle re-runs safely

### Naming

- Files/modules: `snake_case` (e.g., `lastfm_plays`, `collect_all.py`)
- Database tables & columns: `snake_case`
- Column suffixes: `_count`, `_id`, `_at` (timestamp), `_url`
- Source type strings: lowercase (e.g., `"misskey"`, `"lastfm"`, `"health"`)

### Dashboard (`dashboard/app.py`)

- Flask Blueprint structure — all routes are in `app.py`
- API endpoints return JSON; UI routes return rendered templates
- JST conversion applied at display time, not storage time
- Frontend uses `fetch()` + Chart.js — no build step required
- **Calendar timeline**: timestamp links to the entry’s source URL when `logs.url` is set; no separate ↗ control
- **Search (`/search`)**: hit timestamps link to `/?view=day&date=YYYY-MM-DD` (JST day); Last.fm rows expose the same soft-delete button + `POST /api/logs/<id>/soft-delete` as the calendar (see `docs/dashboard_ui.md`)

### Summarizer prompts (`summarizer/prompts/`)

- Markdown templates using `{{PLACEHOLDER}}` syntax for variable substitution
- Language: Japanese (all prompts and generated content are in Japanese)
- Hierarchy: daily → weekly → monthly summaries

### Error handling

- Collectors log errors and continue (do not crash the cron process)
- Dashboard returns JSON error responses with HTTP status codes
- Use Python logging module, not `print()`

---

## Dashboard API Reference

**Base URL**: `http://<tailscale-ip>:5000`

| Method | Path | Description |
|---|---|---|
| GET | `/` | Calendar view (main UI) |
| GET | `/search` | Keyword search (`q`) + optional `source_id`, `date_from`, `date_to` |
| GET | `/api/heatmap` | Heatmap data (`?year=Y&month=M&metric=posts/plays/steps/weather`) |
| GET | `/api/timeline` | Timeline entries (`?date=YYYY-MM-DD&period=day/week/month/year&sources=…`) |
| GET | `/api/stats` | Statistics aggregates (`?period=month/year`) |
| GET | `/api/summaries` | List all published summaries |
| GET | `/api/summary` | Single summary (`?period=week/month&date=YYYY-Www/YYYY-MM`) |
| GET | `/api/sources` | List all data sources |
| POST | `/api/collect/<stype>` | Manually trigger collection for a source type |
| POST | `/api/import/streaming-csv` | Netflix / Prime viewing history CSV (`multipart`: `file`, optional `netflix_profile`). Sources page drag-and-drop |
| POST | `/api/logs/<id>/soft-delete` | Soft-delete one Last.fm log (`is_deleted`; Last.fm only). Used from calendar and search timelines |
| PATCH | `/api/summaries/<id>/publish` | Toggle publication status |
| POST | `/api/ingest` | iPhone ショートカット統合（JSON `source`: `health` / `photo` / `screen_time`）。ヘルスは任意 `health_segment`、`archive`（手動過去投入のタイムライン日付固定）。詳細 `docs/iphone_shortcuts.md` |

---

## Testing

There is **no automated test suite**. Verification is manual:

1. **Collectors**: Run `python -m collectors.<name>` and check log output + DB rows
2. **Summarizer**: Use `--dry-run` flag to preview without writing to DB
3. **Dashboard**: Open in browser via Tailscale and verify UI
4. **Ingest**: Use iPhone Shortcuts or `curl` to POST test payloads

When making changes, manually test the affected component before committing.

---

## Key Documentation Files

Always check `docs/` before making architectural decisions:

| File | Contents |
|---|---|
| `docs/overview.md` | Project goals and tech stack summary |
| `docs/current_state.md` | Phase/milestone status checklist |
| `docs/design.md` | Full architecture & DB schema rationale (19KB) |
| `docs/dashboard_ui.md` | Calendar / search / timeline UI behavior (links, Last.fm delete) |
| `docs/setup.md` | Installation walkthrough |
| `docs/decisions.md` | Design rationale (why PostgreSQL, Ollama, etc.) |
| `docs/phase6_plan.md` | Remaining milestones (M3–M6) |
| `docs/api/` | Per-service API references |

---

## Important Notes for AI Assistants

1. **No public exposure**: This system is private (Tailscale-only). Do not add public auth or rate limiting unless explicitly asked.

2. **Japanese language**: Content, prompts, and display text are Japanese. Preserve this when editing templates or prompts.

3. **Dual writes**: Any new collector must write to both `logs` (unified timeline) and its source-specific table in a single transaction.

4. **UTC/JST**: Always store timestamps as UTC (`TIMESTAMPTZ`). Apply JST offset (+9h) only in display/query layers.

5. **pg_bigm FTS**: Japanese full-text search uses pg_bigm 2-gram index. Use `LIKE '%keyword%'` on indexed columns — standard `tsvector` does not work for Japanese.

6. **No test suite**: Be extra careful with DB migrations and schema changes. There is no automated regression safety net.

7. **Soft deletes**: Use `is_deleted = TRUE` on `logs` rows — never `DELETE`.

8. **Config is gitignored**: `config/settings.toml` is never committed. Reference `config/settings.toml.example` for structure.

9. **venv path**: The Python virtual environment is at `./venv/`. Always activate with `source venv/bin/activate` or use `./venv/bin/python` directly.

10. **Ollama dependency**: Summary generation requires Ollama running locally with `gemma3:12b` pulled. The dashboard gracefully degrades if Ollama is unavailable.
