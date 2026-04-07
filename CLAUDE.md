# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RailScraper is a Python web scraper that fetches Estonian rail (Elron) timetables for Laagri↔Tallinn routes and generates a static HTML timetable page. It runs daily via GitHub Actions (cron at 03:00 UTC) and commits the updated `timetable.html` and `timetable_data.json` back to the repo.

## Commands

```bash
# Run the scraper (requires Chrome installed)
python RailScraper.py

# Install dependencies
pip install -r requirements.txt
```

There are no tests, linter, or build steps configured.

## Architecture

The entire application is a single file: `RailScraper.py`.

- **`RailScraper` class** — uses Selenium (headless Chrome) to load the Elron ticket site, waits for JS-rendered content, then parses trip times with BeautifulSoup. Routes are configured via a `config.json` (auto-created with defaults if missing).
- **`generate_html()`** — produces a self-contained HTML page with inline CSS/JS. The client-side JS handles real-time countdown timers, past-train filtering, and status indicators (no server needed).
- **`main()`** — single-run entrypoint optimized for GitHub Actions (no scheduling loop).

## Key Files

- `RailScraper.py` — scraper + HTML generator
- `timetable.html` — generated output (committed by CI)
- `timetable_data.json` — JSON backup of scraped data (committed by CI)
- `.github/workflows/scrape.yml` — GitHub Actions workflow (daily cron + manual dispatch)
- `config.json` — route configuration (auto-generated on first run, not committed)

## Scraping Details

- Target site: `elron.pilet.ee` — URLs are date-templated (`{date}` replaced with `YYYY-MM-DD`)
- CSS selector for trips: `.trip-summary__timespan`
- Times are extracted via regex from `<span>` elements within each trip container
- A 5-second sleep + 10-second WebDriverWait is used for JS content to render
