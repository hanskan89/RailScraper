# RailScraper Evolution Plan

## Context

RailScraper currently scrapes 2 directional routes (Laagri↔Tallinn) and generates a monolithic HTML page showing both as separate sections. The roadmap calls for adding Kivimäe as a station, auto-detecting user location, remembering preferences, and making the UI more usable on mobile. All personalization must be client-side (static HTML on GitHub Pages — no backend).

The key insight driving this architecture: routes come in **pairs** (A↔B), and the user's core question is always "when's the next train from where I am?" The data model, scraping, and UI should all be organized around this.

---

## Phase 1: Data Model & Scraping Restructure

**File: `RailScraper.py`**

### New config structure (default_config)

Replace the flat `routes` list with a structured model:

```python
{
  "stations": {
    "laagri":  {"name": "Laagri",  "lat": 59.3667, "lng": 24.6333},
    "kivimae": {"name": "Kivimäe", "lat": 59.4019, "lng": 24.7069},
    "tallinn": {"name": "Tallinn", "lat": 59.4400, "lng": 24.7375}
  },
  "route_pairs": [
    {
      "id": "laagri-tallinn",
      "label": "Laagri ↔ Tallinn",
      "stations": ["laagri", "tallinn"],
      "url_templates": {
        "laagri-tallinn": "https://elron.pilet.ee/et/otsing/Laagri/Tallinn/{date}",
        "tallinn-laagri": "https://elron.pilet.ee/et/otsing/Tallinn/Laagri/{date}"
      },
      "selectors": {"trip_container": ".trip-summary__timespan"}
    },
    {
      "id": "kivimae-laagri",
      "label": "Kivimäe ↔ Laagri",
      "stations": ["kivimae", "laagri"],
      "url_templates": {
        "kivimae-laagri": "https://elron.pilet.ee/et/otsing/Kivimäe/Laagri/{date}",
        "laagri-kivimae": "https://elron.pilet.ee/et/otsing/Laagri/Kivimäe/{date}"
      },
      "selectors": {"trip_container": ".trip-summary__timespan"}
    }
  ],
  "output_file": "timetable.html"
}
```

### New output JSON structure (timetable_data.json)

```json
{
  "last_updated": "2026-04-07 05:04:30",
  "stations": {
    "laagri":  {"name": "Laagri",  "lat": 59.3667, "lng": 24.6333},
    "kivimae": {"name": "Kivimäe", "lat": 59.4019, "lng": 24.7069},
    "tallinn": {"name": "Tallinn", "lat": 59.4400, "lng": 24.7375}
  },
  "route_pairs": [
    {
      "id": "laagri-tallinn",
      "label": "Laagri ↔ Tallinn",
      "stations": ["laagri", "tallinn"],
      "directions": {
        "laagri-tallinn": {"from": "laagri", "to": "tallinn", "timetable": [...]},
        "tallinn-laagri": {"from": "tallinn", "to": "laagri", "timetable": [...]}
      }
    },
    {
      "id": "kivimae-laagri",
      "label": "Kivimäe ↔ Laagri",
      "stations": ["kivimae", "laagri"],
      "directions": {
        "kivimae-laagri": {"from": "kivimae", "to": "laagri", "timetable": [...]},
        "laagri-kivimae": {"from": "laagri", "to": "kivimae", "timetable": [...]}
      }
    }
  ]
}
```

### Scraper changes

- `scrape_all_routes()` iterates over `route_pairs`, and for each pair iterates over `url_templates` (2 directions), calling `scrape_route()` for each
- `scrape_route()` signature stays roughly the same — takes a URL + selectors, returns timetable list
- Output assembled into the new JSON structure above
- Station metadata is copied from config into the output JSON (the HTML needs it for geolocation)

This means 4 Selenium page loads instead of 2. Acceptable since it runs in CI once/day.

---

## Phase 2: HTML/UI Overhaul

**File: `RailScraper.py` → `generate_html()` method**

### Layout structure

```
┌─────────────────────────────────┐
│  🚂 Rail Timetables    12:34:56 │  ← header (compact)
├─────────────────────────────────┤
│ [Laagri ↔ Tallinn] [Kivimäe ↔ Laagri] │  ← tab bar (sticky below header)
├─────────────────────────────────┤
│  Laagri → Tallinn    [⇄ Swap]  │  ← direction bar with swap button
├─────────────────────────────────┤
│  (3 upcoming)     [Future Only] │  ← filter bar
├─────────────────────────────────┤
│  ● 12:33  12:54       19m      │  ← timetable rows
│  ● 12:53  13:14       39m      │
│  ...                            │
└─────────────────────────────────┘
```

### Tab bar
- One tab per route pair, using `label` from data
- Active tab visually highlighted
- Clicking a tab switches the visible timetable (JS show/hide, no page reload)
- Tabs are sticky/fixed so they're always accessible without scrolling

### Direction toggle
- Shows current direction as text: "Laagri → Tallinn"
- Swap button (⇄) flips direction within the pair
- Swapping updates the timetable immediately (both directions' data are already in the HTML)

### Data embedding
- The full JSON data (stations + route_pairs with timetables) is embedded in a `<script>` tag as a JS object
- All timetable rendering is done client-side from this data
- This replaces the current approach of server-rendering each row in Python

Why: Currently the Python generates every `<tr>` in the template. With dynamic tab/direction switching, the JS needs access to all data anyway. Embedding the JSON and rendering client-side is cleaner than generating hidden tables for every direction.

---

## Phase 3: Geolocation & Persistence

### Geolocation flow

```
Page load
  → Check localStorage for "railscraper_geo"
  → If exists AND timestamp < 30 min ago:
      Use cached { pair_id, direction }
  → Else:
      Call navigator.geolocation.getCurrentPosition()
      → On success:
          Calculate haversine distance to each station
          For each route pair, find the closer station → that's "from"
          Select the pair where user is nearest to any station
          Save to localStorage: { pair_id, direction, timestamp }
          Apply selection
      → On error/denied:
          Fall back to localStorage "railscraper_last_pair"
          If nothing: default to first pair, first direction
```

### localStorage keys

| Key | Value | TTL |
|-----|-------|-----|
| `railscraper_geo` | `{ pair: "laagri-tallinn", from: "laagri", ts: 1712500000 }` | 30 min |
| `railscraper_last_pair` | `{ pair: "kivimae-laagri", from: "kivimae" }` | Permanent (overwritten on manual switch) |

### Preference priority (highest first)
1. Fresh geo cache (< 30 min old)
2. Last manually selected pair (`railscraper_last_pair`)
3. Default: first route pair, first direction

### Manual override
- When user taps a tab or swaps direction, save to `railscraper_last_pair`
- This does NOT clear the geo cache — next page load within 30 min will still use geo
- Rationale: if you're at Laagri station and tap "Kivimäe ↔ Laagri" manually, you probably want that for this session, but next time geo should still work

---

## Phase 4: UI/UX Polish

- Clean, minimal design — the goal is "glance at phone, know when next train is"
- Large, readable departure times (the primary info)
- Countdown as the most prominent element for the next train
- "Next train" card at the top of the timetable (hero element) showing the very next departure prominently
- Muted past trains, highlighted "leaving soon" (< 15 min)
- Mobile-first: designed for phone viewport, scales up for desktop
- Smooth transitions when switching tabs/directions

---

## Implementation Order

1. **Phase 1** first — restructure data model and add Kivimäe scraping. Verify the 4 routes scrape correctly before touching HTML.
2. **Phase 2** next — rebuild HTML with tabs + direction toggle + client-side rendering from embedded JSON.
3. **Phase 3** — add geolocation and localStorage persistence on top of the working UI.
4. **Phase 4** — visual polish pass.

Each phase produces a working, deployable state.

---

## Files Modified

- `RailScraper.py` — config restructure, scraper loop changes, complete `generate_html()` rewrite
- `timetable_data.json` — new structure (auto-generated)
- `timetable.html` — new output (auto-generated)
- `.github/workflows/scrape.yml` — no changes expected

---

## Long-term Readiness

This architecture is ready for "all stops on the line":
- Add a station to `stations` dict with coordinates
- Add a route pair to `route_pairs` with its URL templates
- The tab bar, geolocation, and persistence all scale automatically — no JS changes needed
- The "Home Route" cookie feature (long-term roadmap) slots in as a third localStorage key with highest priority in the preference chain

---

## Verification

1. Run `python RailScraper.py` locally — confirm it scrapes all 4 directions and produces valid JSON + HTML
2. Open `timetable.html` in a browser — verify tabs switch, direction swap works, countdown timers run
3. Test geolocation: use Chrome DevTools to mock location near Laagri, near Tallinn, near Kivimäe — verify correct auto-selection
4. Test persistence: select a tab manually, reload within 30 min — verify it remembers
5. Test geo denied: block location permission — verify fallback to last pair
6. Push to GitHub, verify Actions workflow runs and Pages deploys correctly
