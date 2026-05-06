# RailScraper

> I have a dream. I have a dream, that instead of slow and messy Elron web I can get my train times in a flash from a static HTML site on my phone with zero loading time. And that dream came true! – Hans

A web scraper that fetches daily train timetables from [Elron](https://elron.pilet.ee) (Estonian railways) and generates a static HTML timetable page. Runs automatically via GitHub Actions.

## Routes

- Laagri ↔ Tallinn
- Kivimäe ↔ Laagri
- Rahumäe ↔ Tallinn

## Using the Timetable

Open [`timetable.html`](https://hanskan89.github.io/RailScraper/timetable.html) (e.g. via GitHub Pages or by hosting the file anywhere static) on your phone or desktop. Everything runs client-side — no server, no spinners.

### Pick a route
- **Tabs** at the top switch between route pairs (Laagri ↔ Tallinn, Kivimäe ↔ Laagri, Rahumäe ↔ Tallinn). On narrow phones the tab strip scrolls horizontally; the active tab auto-centers in view.
- **Swap button (⇄)** flips the direction of the current pair.

### Auto-detect the closest station
On every load the page asks for your location. If allowed, every route pair is oriented so the station nearest you is the *from* station — e.g. if you're in Laagri you'll see "Laagri → Tallinn" and "Laagri → Kivimäe" on their respective tabs without having to swap. Your location is used only in-browser; it is never sent anywhere.

### See the next train at a glance
- The **hero card** at the top shows a live countdown to the next departure (`12m`, `1h 04m`, …) plus the departure → arrival time and train number.
- Each row in the list also has its own countdown that ticks every minute.
- Color cues: **green** = leaves within 15 minutes, **blue** = next upcoming, faded = already departed.

### Filter and remember
- **Future only** toggle hides trains that have already left; flip it off to see the full day.
- Your last picked tab is remembered indefinitely — coming back to the page lands you on the same route. Geolocation only refines the *direction* within that route.

## How It Works

1. A GitHub Actions workflow runs daily at 03:00 UTC (can also be triggered manually)
2. The scraper launches a headless Chrome browser and loads the Elron ticket site for each route
3. Departure and arrival times are extracted from the dynamically rendered page
4. A self-contained HTML page is generated with:
   - Real-time countdown timers to upcoming trains
   - Color-coded status indicators (upcoming, leaving soon, departed)
   - Toggle between showing all trains or only upcoming ones
   - Mobile-responsive layout
5. The updated `timetable.html` and `timetable_data.json` are committed back to the repository

## Setup

### Prerequisites

- Python 3.9+
- Google Chrome

### Installation

```bash
pip install -r requirements.txt
```

### Running locally

```bash
python RailScraper.py
```

This will scrape current timetables, generate `timetable.html`, and save a JSON backup to `timetable_data.json`.

### Configuration

On first run, a `config.json` file is created with default route settings. You can edit it to change:

- Routes (stations and URLs)
- Output file name
- CSS selectors for scraping

## GitHub Actions

The workflow at `.github/workflows/scrape.yml` handles automated daily updates. It can also be triggered manually from the Actions tab using `workflow_dispatch`.
