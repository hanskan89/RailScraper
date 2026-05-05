# Add Rahumäe ↔ Tallinn route + scrollable mobile tab bar

**Status:** approved
**Date:** 2026-05-05

## Goal

Add a third route pair (Rahumäe ↔ Tallinn) to the timetable app, and make the route tab bar scale gracefully on narrow phones where three tabs no longer fit comfortably side-by-side. When a returning user has a remembered route, that tab should be both selected and visible (not hidden behind overflow).

## Background

The app currently scrapes two route pairs and renders them as `flex: 1` tabs that stretch to fill the bar. With three tabs at full labels (`Laagri ↔ Tallinn`, `Kivimäe ↔ Laagri`, `Rahumäe ↔ Tallinn`) on a 375px viewport each tab gets ~125px — text wraps or feels cramped, and the layout has no headroom for a fourth route.

Geolocation and last-route persistence already exist (`loadPreferences` → geo cache → fresh geolocation → `railscraper_last_pair` localStorage). They iterate `route_pairs` generically, so adding a pair requires no logic changes there. What is missing: when a remembered route is restored, nothing scrolls it into view in the (newly scrollable) tab bar.

## Decisions

- **Mobile tab UX: horizontal scroll with edge-fade hint** (Option A). Chosen over reducing labels (ambiguous for the `Kivimäe ↔ Laagri` pair where neither station alone identifies the route) and multi-line wrap (causes layout-shift between viewport widths and eats sticky-header space).
- **Tab sizing: content-sized always** (`flex: 0 0 auto`, "A1"). Chosen over `flex: 1 0 auto` for consistent behavior at any tab count; left-aligned whitespace with few tabs is acceptable.
- **Restored route revealed via `scrollIntoView`** in `renderTabs()`. The same call also auto-centers a manually-tapped tab if it was partially visible. `behavior: 'auto'` (no animation) on render so initial paint stays snappy.
- **Coordinates corrected** as part of this change (user-supplied):
  - Laagri: `59.3544, 24.6275`
  - Kivimäe: `59.3770, 24.6566`
  - Tallinn: `59.4400, 24.7375` (unchanged)
  - Rahumäe: `59.3888, 24.7044` (new)

## Out of scope

- Adding more routes beyond Rahumäe.
- Desktop layout changes (current desktop layout is fine with 3+ tabs).
- Test infrastructure (project has none today; manual verification only).
- Dynamic / runtime config UI.
- README rewrite (current link to `timetable.html` already covers user discovery).

## Design

### 1. Configuration & data

`RailScraper.py` `load_config()` default config (currently RailScraper.py:63-92) is updated to:

```json
{
  "stations": {
    "laagri":   { "name": "Laagri",   "lat": 59.3544, "lng": 24.6275 },
    "kivimae":  { "name": "Kivimäe",  "lat": 59.3770, "lng": 24.6566 },
    "rahumae":  { "name": "Rahumäe",  "lat": 59.3888, "lng": 24.7044 },
    "tallinn":  { "name": "Tallinn",  "lat": 59.4400, "lng": 24.7375 }
  },
  "route_pairs": [
    { "id": "laagri-tallinn",  "label": "Laagri ↔ Tallinn",  "stations": ["laagri", "tallinn"],
      "url_templates": {
        "laagri-tallinn": "https://elron.pilet.ee/et/otsing/Laagri/Tallinn/{date}",
        "tallinn-laagri": "https://elron.pilet.ee/et/otsing/Tallinn/Laagri/{date}"
      },
      "selectors": { "trip_container": ".trip-summary__timespan" }
    },
    { "id": "kivimae-laagri",  "label": "Kivimäe ↔ Laagri",  "stations": ["kivimae", "laagri"],
      "url_templates": {
        "kivimae-laagri": "https://elron.pilet.ee/et/otsing/Kivim%C3%A4e/Laagri/{date}",
        "laagri-kivimae": "https://elron.pilet.ee/et/otsing/Laagri/Kivim%C3%A4e/{date}"
      },
      "selectors": { "trip_container": ".trip-summary__timespan" }
    },
    { "id": "rahumae-tallinn", "label": "Rahumäe ↔ Tallinn", "stations": ["rahumae", "tallinn"],
      "url_templates": {
        "rahumae-tallinn": "https://elron.pilet.ee/et/otsing/Rahum%C3%A4e/Tallinn/{date}",
        "tallinn-rahumae": "https://elron.pilet.ee/et/otsing/Tallinn/Rahum%C3%A4e/{date}"
      },
      "selectors": { "trip_container": ".trip-summary__timespan" }
    }
  ],
  "output_file": "timetable.html"
}
```

The Rahumäe pair is appended last so it appears as the third tab. `scrape_all_routes()` already iterates `route_pairs` generically — no scraper code changes needed.

**Local `config.json` migration:** the file is gitignored and auto-generated. Anyone with a stale local file deletes it (or hand-edits) to pick up the new pair and corrected coordinates. CI generates a fresh config each run, so the workflow is unaffected. This is documented but not handled in code.

### 2. Tab bar — scrollable horizontal layout

The current `.tab-bar` is `position: sticky` and is rendered directly inside `<body>`. To anchor an edge-fade overlay on it without disturbing sticky positioning, wrap the tab bar in a sticky wrapper and let the inner element scroll:

```html
<div class="tab-bar-wrap">
  <div class="tab-bar" id="tabBar"></div>
</div>
```

```css
.tab-bar-wrap {
  position: sticky;
  top: 0;
  z-index: 100;
  background: #1a1d28;
  border-bottom: 2px solid #2a2d3a;
}
.tab-bar-wrap::after {
  /* right-side fade indicating more content */
  content: '';
  position: absolute;
  top: 0; right: 0; bottom: 0;
  width: 32px;
  pointer-events: none;
  background: linear-gradient(to right, transparent, #1a1d28);
  opacity: 1;
  transition: opacity 0.15s;
}
.tab-bar-wrap.scrolled-end::after { opacity: 0; }

.tab-bar {
  display: flex;
  padding: 0 12px;
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.tab-bar::-webkit-scrollbar { display: none; }

.tab {
  flex: 0 0 auto;            /* content-sized, no stretch (A1) */
  padding: 14px 16px;
  text-align: center;
  cursor: pointer;
  font-size: 0.9em;
  font-weight: 500;
  color: #6b7080;
  border-bottom: 3px solid transparent;
  transition: all 0.2s;
  -webkit-tap-highlight-color: transparent;
  white-space: nowrap;
}
```

**Notes on what changed vs. the old tab bar:**

- `position: sticky`, `z-index`, `background`, and `border-bottom` move from `.tab-bar` to `.tab-bar-wrap`. The inner `.tab-bar` only handles flex layout + horizontal scroll.
- Removed `scroll-snap` entirely — with content-sized tabs and `scrollIntoView({ inline: 'center' })` driving placement, snap behavior would either be redundant or fight the center alignment.
- `flex: 1` on `.tab` becomes `flex: 0 0 auto` (decision A1: content-sized, no stretch).

**Edge-fade behavior:**

- Right-side `::after` gradient (32px wide, fading to the bar's background color) hints that more tabs are off-screen.
- A scroll listener on `.tab-bar` toggles `.scrolled-end` on `.tab-bar-wrap` when `scrollLeft + clientWidth >= scrollWidth - 1` (1px tolerance for sub-pixel scroll positions). Throttled via `requestAnimationFrame`.
- Same helper called from `renderTabs()` after layout, and on `window.resize`.
- Left-edge fade is intentionally **not** added — the active tab usually starts visible at the left, and a left fade adds visual noise without much benefit. Can be added later if needed.

### 3. Reveal active tab on render

Update `renderTabs()` in `RailScraper.py:601-616` to scroll the active tab into view after appending:

```js
function renderTabs() {
  const bar = document.getElementById('tabBar');
  bar.innerHTML = '';
  let activeEl = null;
  DATA.route_pairs.forEach((pair, i) => {
    const tab = document.createElement('div');
    tab.className = 'tab' + (i === activePairIndex ? ' active' : '');
    tab.textContent = pair.label;
    tab.onclick = () => {
      activePairIndex = i;
      activeDirectionIndex = pairDirections[i] ?? 0;
      saveManualChoice();
      renderAll();
    };
    bar.appendChild(tab);
    if (i === activePairIndex) activeEl = tab;
  });
  if (activeEl) {
    activeEl.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'auto' });
  }
  updateTabBarFade();   // recompute edge-fade after layout settles
}
```

This handles three cases with one call:

1. **Initial restore** — last-used route remembered in localStorage gets centered in the tab bar so the user immediately sees it as active.
2. **Geo-arrival update** — when async geolocation arrives ~1-2s later and selects a different pair, `renderAll()` runs again and the new active tab is centered.
3. **Manual tap** — if the tapped tab was partially clipped at the edge, it slides into the center; if already fully visible, `scrollIntoView` is a no-op.

`behavior: 'auto'` (not `smooth`) keeps initial paint snappy.

### 4. Persistence behavior with 3 routes

`pairDirections` is an array indexed by pair index. Existing saved values from a 2-route world (length 2) remain valid because the read site uses `pairDirections[activePairIndex] ?? 0`, so a missing third entry falls back to direction 0. **No migration code needed.**

### 5. Files touched

- `RailScraper.py` — `load_config()` default config (stations + route_pairs), `.tab-bar-wrap` / `.tab-bar` / `.tab` CSS, edge-fade CSS + scroll-listener JS helper, HTML markup wraps `<div class="tab-bar">` in `<div class="tab-bar-wrap">`, `renderTabs()` JS function.
- `timetable.html` — regenerated by next scrape; not edited by hand.
- `timetable_data.json` — regenerated by next scrape.

No new files, no new dependencies.

## Verification (manual)

The project has no test setup. After implementation:

1. **Run scraper locally:** delete any stale `config.json`, run `python RailScraper.py`, confirm three pairs scraped without errors and `timetable.html` regenerated.
2. **Desktop browser (≥768px):** open `timetable.html`. All three tabs visible. Tabs are content-sized, left-aligned with whitespace on the right (A1 behavior). Clicking each tab switches the route. Swap button works on each.
3. **Mobile viewport (375px, e.g., DevTools iPhone SE):**
   - Tabs scroll horizontally with no visible scrollbar.
   - Right-edge fade visible when not scrolled to the end; disappears when scrolled to end.
   - Tapping a tab partially clipped at the right edge centers it in the bar.
4. **Persistence + reveal:** select the third tab (Rahumäe ↔ Tallinn). Reload the page. The third tab is active **and** scrolled into view, not hidden under right-side overflow.
5. **Geolocation:** allow location permission near Tallinn → expect a route with Tallinn as `from`. Disallow → falls back to last-saved route. (Test with a Geolocation override in DevTools using lat/lng near each station.)
6. **Past-data resilience:** old localStorage from before this change (length-2 `pairDirections`) loads cleanly without console errors.
