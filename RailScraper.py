#!/usr/bin/env python3
"""
Rail Timetable Scraper Web App
Scrapes two rail websites daily and generates a static HTML timetable page.
"""

from bs4 import BeautifulSoup
import json
import datetime
from zoneinfo import ZoneInfo
import time
from typing import List, Dict, Tuple
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# elron.pilet.ee renders the trip list within a few seconds but keeps the
# document busy for far longer, so navigation is capped generously and a
# timeout is treated as "look at the DOM anyway" rather than as a failure.
PAGE_LOAD_TIMEOUT = 45
CONTENT_TIMEOUT = 20
SETTLE_POLLS = 10
ROUTE_ATTEMPTS = 3


class RailScraper:
    def setup_webdriver(self):
        """Setup Chrome WebDriver with appropriate options."""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # Run in background
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            # Images contribute nothing to the timetable and only slow the load.
            chrome_options.add_argument('--blink-settings=imagesEnabled=false')
            # 'eager' returns at DOMContentLoaded instead of blocking on the
            # window load event, which the target site can take 30s+ to fire.
            chrome_options.page_load_strategy = 'eager'

            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            logger.info("WebDriver initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise
    
    def close_webdriver(self):
        """Close the WebDriver."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver closed successfully")
            except Exception as e:
                logger.error(f"Error closing WebDriver: {str(e)}")
    def __init__(self, config_file='config.json'):
        """Initialize the rail scraper with configuration."""
        self.config = self.load_config(config_file)
        self.driver = None
        self.setup_webdriver()
    
    def load_config(self, config_file: str) -> Dict:
        """Load configuration from JSON file."""
        default_config = {
            "stations": {
                "laagri":    {"name": "Laagri",    "lat": 59.3544, "lng": 24.6275},
                "kivimae":   {"name": "Kivimäe",   "lat": 59.3770, "lng": 24.6566},
                "rahumae":   {"name": "Rahumäe",   "lat": 59.3888, "lng": 24.7044},
                "nomme":     {"name": "Nõmme",     "lat": 59.3861, "lng": 24.6863},
                "lillekula": {"name": "Lilleküla", "lat": 59.4248, "lng": 24.7280},
                "tallinn":   {"name": "Tallinn",   "lat": 59.4400, "lng": 24.7375}
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
                    "id": "kivimae-tallinn",
                    "label": "Kivimäe ↔ Tallinn",
                    "stations": ["kivimae", "tallinn"],
                    "url_templates": {
                        "kivimae-tallinn": "https://elron.pilet.ee/et/otsing/Kivim%C3%A4e/Tallinn/{date}",
                        "tallinn-kivimae": "https://elron.pilet.ee/et/otsing/Tallinn/Kivim%C3%A4e/{date}"
                    },
                    "selectors": {"trip_container": ".trip-summary__timespan"}
                },
                {
                    "id": "rahumae-tallinn",
                    "label": "Rahumäe ↔ Tallinn",
                    "stations": ["rahumae", "tallinn"],
                    "url_templates": {
                        "rahumae-tallinn": "https://elron.pilet.ee/et/otsing/Rahum%C3%A4e/Tallinn/{date}",
                        "tallinn-rahumae": "https://elron.pilet.ee/et/otsing/Tallinn/Rahum%C3%A4e/{date}"
                    },
                    "selectors": {"trip_container": ".trip-summary__timespan"}
                },
                {
                    "id": "nomme-tallinn",
                    "label": "Nõmme ↔ Tallinn",
                    "stations": ["nomme", "tallinn"],
                    "url_templates": {
                        "nomme-tallinn": "https://elron.pilet.ee/et/otsing/N%C3%B5mme/Tallinn/{date}",
                        "tallinn-nomme": "https://elron.pilet.ee/et/otsing/Tallinn/N%C3%B5mme/{date}"
                    },
                    "selectors": {"trip_container": ".trip-summary__timespan"}
                },
                {
                    "id": "lillekula-nomme",
                    "label": "Lilleküla ↔ Nõmme",
                    "stations": ["lillekula", "nomme"],
                    "url_templates": {
                        "lillekula-nomme": "https://elron.pilet.ee/et/otsing/Lillek%C3%BCla/N%C3%B5mme/{date}",
                        "nomme-lillekula": "https://elron.pilet.ee/et/otsing/N%C3%B5mme/Lillek%C3%BCla/{date}"
                    },
                    "selectors": {"trip_container": ".trip-summary__timespan"}
                }
            ],
            "output_file": "timetable.html"
        }
        
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.info(f"Config file {config_file} not found. Creating default config.")
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            return default_config
    
    def get_current_date_url(self, url_template: str) -> str:
        """Generate URL with current date in YYYY-MM-DD format."""
        current_date = datetime.datetime.now(ZoneInfo('Europe/Tallinn')).strftime('%Y-%m-%d')
        return url_template.format(date=current_date)
    
    def navigate(self, url: str):
        """Load a URL, tolerating a slow window load event.

        The trip list is present in the DOM long before the document finishes
        loading, so a page load timeout is recoverable: stop the load and let
        the caller inspect whatever rendered.
        """
        try:
            self.driver.get(url)
        except TimeoutException:
            logger.warning("Page load timed out, using partially loaded page")
            try:
                self.driver.execute_script('window.stop();')
            except WebDriverException as e:
                logger.warning(f"Could not stop page load: {str(e)}")

    def wait_for_trips(self, trip_selector: str):
        """Wait for trip containers to appear, then for their count to settle."""
        try:
            WebDriverWait(self.driver, CONTENT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, trip_selector))
            )
        except TimeoutException:
            logger.warning(f"No trip containers appeared within {CONTENT_TIMEOUT}s")
            return

        # The list renders incrementally; poll until it stops growing so we
        # never parse a half-populated timetable.
        previous = -1
        for _ in range(SETTLE_POLLS):
            time.sleep(1)
            current = len(self.driver.find_elements(By.CSS_SELECTOR, trip_selector))
            if current == previous:
                return
            previous = current
        logger.warning("Trip list still growing when the settle budget ran out")

    def parse_trips(self, selectors: Dict) -> List[Dict]:
        """Parse departure/arrival times and train numbers from the loaded page."""
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')

        # Find all trip containers (parent level for times + train number)
        trip_containers = soup.select('.trip-summary')

        timetable = []

        # Extract times and train number from each trip container
        import re
        time_pattern = re.compile(r'\b([0-2]?[0-9]):([0-5][0-9])\b')

        for container in trip_containers:
            timespan = container.select_one(selectors['trip_container'])
            if not timespan:
                continue

            span_times = [
                match.group()
                for span in timespan.find_all('span')
                if (match := time_pattern.search(span.get_text()))
            ]

            if len(span_times) >= 2:
                departure_time = span_times[0]
                arrival_time = span_times[1]

                train_number = ''
                line_num_el = container.select_one('.line-number')
                if line_num_el:
                    train_number = line_num_el.get_text(strip=True)

                trip_data = {
                    'departure': departure_time,
                    'arrival': arrival_time,
                    'train': train_number
                }
                timetable.append(trip_data)

        # Remove duplicates while preserving order
        seen = set()
        unique_timetable = []
        for trip in timetable:
            trip_key = (trip['departure'], trip['arrival'])
            if trip_key not in seen:
                seen.add(trip_key)
                unique_timetable.append(trip)

        return unique_timetable

    def scrape_route(self, url_template: str, selectors: Dict, direction_label: str) -> List[Dict]:
        """Scrape timetable data for a single route direction using Selenium."""
        url = self.get_current_date_url(url_template)

        for attempt in range(1, ROUTE_ATTEMPTS + 1):
            logger.info(f"Scraping {direction_label} from {url} (attempt {attempt}/{ROUTE_ATTEMPTS})")
            try:
                self.navigate(url)
                self.wait_for_trips(selectors['trip_container'])
                timetable = self.parse_trips(selectors)
            except WebDriverException as e:
                logger.error(f"Error scraping {direction_label}: {str(e)}")
                timetable = []

            if timetable:
                logger.info(f"Found {len(timetable)} unique schedules for {direction_label}")
                return timetable

            logger.warning(f"No schedules extracted for {direction_label} on attempt {attempt}")

        logger.error(f"Giving up on {direction_label} after {ROUTE_ATTEMPTS} attempts")
        return []

    def load_previous_timetables(self, path: str = 'timetable_data.json') -> Dict[str, Dict]:
        """Index the last committed run by direction id, for stale fallback."""
        try:
            with open(path, 'r') as f:
                previous = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.info(f"No usable previous timetable data ({str(e)})")
            return {}

        indexed = {}
        fallback_date = previous.get('service_date') or previous.get('last_updated', '')[:10]
        for pair in previous.get('route_pairs', []):
            for direction_id, direction in pair.get('directions', {}).items():
                if direction.get('timetable'):
                    indexed[direction_id] = {
                        'timetable': direction['timetable'],
                        'stale_from': direction.get('stale_from') or fallback_date
                    }
        return indexed

    def scrape_all_routes(self) -> Tuple[Dict, List[str]]:
        """Scrape all configured route pairs and directions.

        Returns the scraped data plus the direction ids that yielded nothing.
        A direction that fails keeps the previously scraped timetable, flagged
        with 'stale_from', so the page shows a dated schedule rather than
        claiming there are no trains at all.
        """
        service_date = datetime.datetime.now(ZoneInfo('Europe/Tallinn')).strftime('%Y-%m-%d')
        all_data = {
            'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'service_date': service_date,
            'stations': self.config['stations'],
            'route_pairs': []
        }

        previous = self.load_previous_timetables()
        failed = []

        for pair in self.config['route_pairs']:
            pair_data = {
                'id': pair['id'],
                'label': pair['label'],
                'stations': pair['stations'],
                'directions': {}
            }

            for direction_id, url_template in pair['url_templates'].items():
                stations = direction_id.split('-')
                from_station = stations[0]
                to_station = stations[1]
                direction_label = f"{self.config['stations'][from_station]['name']} → {self.config['stations'][to_station]['name']}"

                timetable = self.scrape_route(url_template, pair['selectors'], direction_label)
                direction_data = {
                    'from': from_station,
                    'to': to_station,
                    'timetable': timetable
                }

                if not timetable:
                    failed.append(direction_id)
                    stale = previous.get(direction_id)
                    if stale:
                        logger.warning(
                            f"Keeping {len(stale['timetable'])} schedules scraped on "
                            f"{stale['stale_from']} for {direction_label}"
                        )
                        direction_data['timetable'] = stale['timetable']
                        direction_data['stale_from'] = stale['stale_from']

                pair_data['directions'][direction_id] = direction_data

            all_data['route_pairs'].append(pair_data)

        return all_data, failed

    def generate_html(self, data: Dict) -> str:
        """Generate HTML page with client-side rendering, tabs, geolocation, and persistence."""
        data_json = json.dumps(data)
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rail Timetables</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f1117;
            color: #e0e0e0;
            min-height: 100vh;
        }}
        .header {{
            background: #1a1d28;
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #2a2d3a;
        }}
        .header-title {{
            font-size: 1.1em;
            font-weight: 600;
        }}
        .tab-bar-wrap {{
            position: sticky;
            top: 0;
            z-index: 100;
            background: #1a1d28;
            border-bottom: 2px solid #2a2d3a;
        }}
        .tab-bar-wrap::after {{
            content: '';
            position: absolute;
            top: 0; right: 0; bottom: 2px;
            width: 32px;
            pointer-events: none;
            background: linear-gradient(to right, rgba(26,29,40,0), #1a1d28);
            opacity: 1;
            transition: opacity 0.15s;
        }}
        .tab-bar-wrap.scrolled-end::after {{ opacity: 0; }}
        .tab-bar {{
            display: flex;
            padding: 0 12px;
            overflow-x: auto;
            scrollbar-width: none;
            -ms-overflow-style: none;
        }}
        .tab-bar::-webkit-scrollbar {{ display: none; }}
        .tab {{
            flex: 0 0 auto;
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
        }}
        .tab.active {{
            color: #7c8aff;
            border-bottom-color: #7c8aff;
        }}
        .direction-bar {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 12px;
            padding: 14px 20px;
            background: #1e2130;
        }}
        .direction-label {{
            font-size: 1.05em;
            font-weight: 600;
        }}
        .swap-btn {{
            background: #2a2d3a;
            border: 1px solid #3a3d4a;
            color: #7c8aff;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 1.1em;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            -webkit-tap-highlight-color: transparent;
        }}
        .swap-btn:active {{ background: #3a3d4a; }}
        .hero {{
            background: linear-gradient(135deg, #1e2a4a 0%, #1a2040 100%);
            margin: 16px;
            padding: 24px;
            border-radius: 16px;
            text-align: center;
            border: 1px solid #2a3a5a;
        }}
        .hero-countdown {{
            font-size: 2.8em;
            font-weight: 700;
            color: #7c8aff;
            font-family: 'SF Mono', 'Fira Code', monospace;
            line-height: 1.1;
        }}
        .hero-time {{
            font-size: 1.2em;
            color: #8b8fa3;
            margin-top: 6px;
        }}
        .hero-label {{
            font-size: 0.85em;
            color: #5a5e70;
            margin-top: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .hero.no-trains {{
            border-color: #3a2a2a;
            background: linear-gradient(135deg, #2a1a1a 0%, #201a1a 100%);
        }}
        .hero.no-trains .hero-countdown {{
            color: #666;
            font-size: 1.2em;
        }}
        .filter-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 20px;
            border-bottom: 1px solid #1e2130;
        }}
        .upcoming-count {{
            font-size: 0.85em;
            color: #5a5e70;
        }}
        .filter-btn {{
            background: none;
            border: 1px solid #2a2d3a;
            color: #6b7080;
            padding: 6px 14px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.8em;
            transition: all 0.2s;
            -webkit-tap-highlight-color: transparent;
        }}
        .filter-btn.active {{
            border-color: #7c8aff;
            color: #7c8aff;
        }}
        .timetable {{
            padding: 0 12px 100px;
        }}
        .train-row {{
            display: flex;
            align-items: center;
            padding: 14px 12px;
            border-bottom: 1px solid #1a1d28;
            transition: opacity 0.2s;
        }}
        .train-row.past {{ opacity: 0.3; }}
        .train-row.soon {{
            background: #1e2a1e;
            border-left: 3px solid #4caf50;
            border-radius: 4px;
            margin: 2px 0;
        }}
        .train-row.next {{
            background: #1a1e3a;
            border-left: 3px solid #7c8aff;
            border-radius: 4px;
            margin: 2px 0;
        }}
        .train-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 14px;
            flex-shrink: 0;
        }}
        .dot-past {{ background: #444; }}
        .dot-soon {{ background: #4caf50; }}
        .dot-future {{ background: #7c8aff; }}
        .train-times {{
            flex: 1;
            display: flex;
            gap: 8px;
            align-items: baseline;
        }}
        .train-dep {{
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 1.15em;
            font-weight: 600;
        }}
        .train-arr {{
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 0.9em;
            color: #5a5e70;
        }}
        .train-arrow {{
            color: #3a3d4a;
            font-size: 0.8em;
        }}
        .train-number {{
            font-size: 0.7em;
            color: #4a4d5a;
            background: #1a1d28;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 4px;
            font-family: 'SF Mono', 'Fira Code', monospace;
        }}
        .train-countdown {{
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 0.95em;
            color: #5a5e70;
            text-align: right;
            min-width: 60px;
        }}
        .train-row.soon .train-countdown {{ color: #4caf50; font-weight: 600; }}
        .train-row.next .train-countdown {{ color: #7c8aff; }}
        .no-trains-msg {{
            text-align: center;
            color: #444;
            padding: 40px 20px;
            font-style: italic;
        }}
        .stale-banner {{
            margin: 0 16px 12px;
            padding: 10px 14px;
            border-radius: 10px;
            background: #2a2416;
            border: 1px solid #4a3f22;
            color: #c9a961;
            font-size: 0.8em;
            text-align: center;
        }}
        .last-updated {{
            text-align: center;
            color: #3a3d4a;
            font-size: 0.75em;
            padding: 20px;
        }}
        .hidden {{ display: none !important; }}
    </style>
</head>
<body>
    <div class="header">
        <span class="header-title">Rail Timetables</span>
    </div>
    <div class="tab-bar-wrap" id="tabBarWrap">
        <div class="tab-bar" id="tabBar"></div>
    </div>
    <div class="direction-bar">
        <span class="direction-label" id="directionLabel"></span>
        <button class="swap-btn" id="swapBtn" onclick="swapDirection()">&#8644;</button>
    </div>
    <div class="hero" id="hero">
        <div class="hero-label">Next train</div>
        <div class="hero-countdown" id="heroCountdown"></div>
        <div class="hero-time" id="heroTime"></div>
    </div>
    <div class="stale-banner hidden" id="staleBanner"></div>
    <div class="filter-bar">
        <span class="upcoming-count" id="upcomingCount"></span>
        <button class="filter-btn active" id="filterBtn" onclick="toggleFilter()">Future only</button>
    </div>
    <div class="timetable" id="timetable"></div>
    <div class="last-updated">Updated: {data['last_updated']}</div>

    <script>
        const DATA = {data_json};

        let activePairIndex = 0;
        let activeDirectionIndex = 0; // 0 = first direction, 1 = second
        let pairDirections = []; // per-pair preferred direction index
        let showFutureOnly = true;

        // --- Geolocation & Persistence ---

        function haversine(lat1, lng1, lat2, lng2) {{
            const R = 6371;
            const dLat = (lat2 - lat1) * Math.PI / 180;
            const dLng = (lng2 - lng1) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                      Math.sin(dLng/2) * Math.sin(dLng/2);
            return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        }}

        function findClosestStation(lat, lng) {{
            let closest = null;
            let minDist = Infinity;
            for (const [id, st] of Object.entries(DATA.stations)) {{
                const d = haversine(lat, lng, st.lat, st.lng);
                if (d < minDist) {{
                    minDist = d;
                    closest = id;
                }}
            }}
            return closest;
        }}

        // Geolocation refines the active direction (closest "from" station wins).
        // It only picks the active pair on first-ever visit, when no manual choice
        // has been persisted — the user's last manual tab tap is authoritative for
        // pair selection on every subsequent load.
        function applyGeoSelection(lat, lng, keepActivePair) {{
            let bestPairIdx = 0;
            let bestDist = Infinity;

            DATA.route_pairs.forEach((pair, pi) => {{
                const dirKeys = Object.keys(pair.directions);
                let pairBestDirIdx = 0;
                let pairBestDist = Infinity;
                dirKeys.forEach((key, di) => {{
                    const fromId = pair.directions[key].from;
                    const st = DATA.stations[fromId];
                    const d = haversine(lat, lng, st.lat, st.lng);
                    if (d < pairBestDist) {{
                        pairBestDist = d;
                        pairBestDirIdx = di;
                    }}
                }});
                pairDirections[pi] = pairBestDirIdx;
                if (pairBestDist < bestDist) {{
                    bestDist = pairBestDist;
                    bestPairIdx = pi;
                }}
            }});

            if (!keepActivePair) {{
                activePairIndex = bestPairIdx;
            }}
            activeDirectionIndex = pairDirections[activePairIndex];

            persistChoice();
            renderAll();
        }}

        function loadPreferences() {{
            // 1. Restore last manual route choice — authoritative for which pair is active.
            let havePersistedPair = false;
            try {{
                const last = JSON.parse(localStorage.getItem('railscraper_last_pair'));
                if (last) {{
                    activePairIndex = last.pair;
                    if (Array.isArray(last.pairDirs)) pairDirections = last.pairDirs;
                    activeDirectionIndex = pairDirections[activePairIndex] ?? last.dir ?? 0;
                    havePersistedPair = true;
                }}
            }} catch(e) {{}}

            // 2. Always run geolocation to refine direction within the active pair
            //    (and to pick the pair itself on a first-ever visit).
            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(
                    pos => applyGeoSelection(pos.coords.latitude, pos.coords.longitude, havePersistedPair),
                    () => {{}}
                );
            }}
        }}

        function persistChoice() {{
            try {{
                localStorage.setItem('railscraper_last_pair', JSON.stringify({{
                    pair: activePairIndex,
                    dir: activeDirectionIndex,
                    pairDirs: pairDirections
                }}));
            }} catch(e) {{}}
        }}

        function saveManualChoice() {{ persistChoice(); }}

        // --- Rendering ---

        function getActivePair() {{ return DATA.route_pairs[activePairIndex]; }}

        function getActiveDirection() {{
            const pair = getActivePair();
            const keys = Object.keys(pair.directions);
            return pair.directions[keys[activeDirectionIndex]];
        }}

        function renderTabs() {{
            const bar = document.getElementById('tabBar');
            bar.innerHTML = '';
            let activeEl = null;
            DATA.route_pairs.forEach((pair, i) => {{
                const tab = document.createElement('div');
                tab.className = 'tab' + (i === activePairIndex ? ' active' : '');
                tab.textContent = pair.label;
                tab.onclick = () => {{
                    activePairIndex = i;
                    activeDirectionIndex = pairDirections[i] ?? 0;
                    saveManualChoice();
                    renderAll();
                }};
                bar.appendChild(tab);
                if (i === activePairIndex) activeEl = tab;
            }});
            if (activeEl) {{
                activeEl.scrollIntoView({{ inline: 'center', block: 'nearest', behavior: 'auto' }});
            }}
            scheduleFadeUpdate();
        }}

        function updateTabBarFade() {{
            const bar = document.getElementById('tabBar');
            const wrap = document.getElementById('tabBarWrap');
            if (!bar || !wrap) return;
            const atEnd = bar.scrollLeft + bar.clientWidth >= bar.scrollWidth - 1;
            const overflowing = bar.scrollWidth > bar.clientWidth + 1;
            wrap.classList.toggle('scrolled-end', atEnd || !overflowing);
        }}

        let _fadeRaf = 0;
        function scheduleFadeUpdate() {{
            if (_fadeRaf) return;
            _fadeRaf = requestAnimationFrame(() => {{
                _fadeRaf = 0;
                updateTabBarFade();
            }});
        }}

        function renderDirection() {{
            const dir = getActiveDirection();
            const fromName = DATA.stations[dir.from].name;
            const toName = DATA.stations[dir.to].name;
            document.getElementById('directionLabel').textContent = fromName + ' \\u2192 ' + toName;
        }}

        function swapDirection() {{
            const pair = getActivePair();
            const keys = Object.keys(pair.directions);
            activeDirectionIndex = (activeDirectionIndex + 1) % keys.length;
            pairDirections[activePairIndex] = activeDirectionIndex;
            saveManualChoice();
            renderAll();
        }}

        function parseTime(timeStr) {{
            const [h, m] = timeStr.split(':').map(Number);
            const now = new Date();
            return new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m);
        }}

        function formatCountdown(diffMs) {{
            if (diffMs < 0) return 'Gone';
            const mins = Math.floor(diffMs / 60000);
            const hrs = Math.floor(mins / 60);
            const rem = mins % 60;
            if (hrs > 0) return hrs + 'h ' + rem + 'm';
            if (mins > 0) return mins + 'm';
            return 'Now';
        }}

        function renderTimetable() {{
            const dir = getActiveDirection();
            const timetable = dir.timetable;
            const container = document.getElementById('timetable');
            const now = new Date();

            // This direction failed to re-scrape, so these times were captured
            // on an earlier date and may not match today's service.
            const staleBanner = document.getElementById('staleBanner');
            staleBanner.classList.toggle('hidden', !dir.stale_from);
            if (dir.stale_from) {{
                staleBanner.textContent = 'Could not refresh this route \\u2014 showing the schedule from ' + dir.stale_from;
            }}

            if (!timetable || timetable.length === 0) {{
                container.innerHTML = '<div class="no-trains-msg">No timetable data available</div>';
                document.getElementById('hero').classList.add('no-trains');
                document.getElementById('heroCountdown').textContent = 'No data';
                document.getElementById('heroTime').textContent = '';
                document.getElementById('upcomingCount').textContent = '';
                return;
            }}

            let nextTrain = null;
            let upcomingCount = 0;
            let html = '';

            timetable.forEach(train => {{
                const depTime = parseTime(train.departure);
                const diffMs = depTime - now;
                const isPast = diffMs < 0;
                const isSoon = !isPast && diffMs <= 15 * 60000;
                const isNext = !isPast && !nextTrain;

                if (!isPast) {{
                    upcomingCount++;
                    if (!nextTrain) nextTrain = {{ ...train, diffMs }};
                }}

                if (showFutureOnly && isPast) return;

                let rowClass = 'train-row';
                let dotClass = 'train-dot dot-future';
                if (isPast) {{ rowClass += ' past'; dotClass = 'train-dot dot-past'; }}
                else if (isSoon) {{ rowClass += ' soon'; dotClass = 'train-dot dot-soon'; }}
                else if (isNext) {{ rowClass += ' next'; }}

                const trainNumHtml = train.train ? '<span class="train-number">' + train.train + '</span>' : '';

                html += '<div class="' + rowClass + '">' +
                    '<div class="' + dotClass + '"></div>' +
                    '<div class="train-times">' +
                        '<span class="train-dep">' + train.departure + '</span>' +
                        '<span class="train-arrow">&#8594;</span>' +
                        '<span class="train-arr">' + train.arrival + '</span>' +
                        trainNumHtml +
                    '</div>' +
                    '<div class="train-countdown">' + (isPast ? '' : formatCountdown(diffMs)) + '</div>' +
                '</div>';
            }});

            container.innerHTML = html || '<div class="no-trains-msg">No upcoming trains today</div>';

            // Hero
            const hero = document.getElementById('hero');
            if (nextTrain) {{
                hero.classList.remove('no-trains');
                document.getElementById('heroCountdown').textContent = formatCountdown(nextTrain.diffMs);
                const heroTrainNum = nextTrain.train ? ' #' + nextTrain.train : '';
                document.getElementById('heroTime').textContent = nextTrain.departure + ' \\u2192 ' + nextTrain.arrival + heroTrainNum;
            }} else {{
                hero.classList.add('no-trains');
                document.getElementById('heroCountdown').textContent = 'No more trains today';
                document.getElementById('heroTime').textContent = '';
            }}

            document.getElementById('upcomingCount').textContent = upcomingCount + ' upcoming';
        }}

        function toggleFilter() {{
            showFutureOnly = !showFutureOnly;
            const btn = document.getElementById('filterBtn');
            btn.classList.toggle('active', showFutureOnly);
            btn.textContent = showFutureOnly ? 'Future only' : 'Show all';
            renderTimetable();
        }}

        function renderAll() {{
            renderTabs();
            renderDirection();
            renderTimetable();
        }}

        // --- Init ---

        function init() {{
            loadPreferences();
            renderAll();
            const bar = document.getElementById('tabBar');
            if (bar) bar.addEventListener('scroll', scheduleFadeUpdate, {{ passive: true }});
            window.addEventListener('resize', scheduleFadeUpdate);
            setInterval(() => {{
                renderTimetable();
            }}, 60000);
        }}

        document.addEventListener('DOMContentLoaded', init);
    </script>
</body>
</html>"""
        return html
    
    def save_html(self, html_content: str):
        """Save HTML content to file."""
        output_file = self.config['output_file']
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"HTML file saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving HTML file: {str(e)}")
    
    def run_scraping_job(self) -> List[str]:
        """Run the complete scraping job. Returns the direction ids that failed."""
        logger.info("Starting daily scraping job...")

        try:
            # Scrape all routes
            data, failed = self.scrape_all_routes()

            # Generate HTML
            html_content = self.generate_html(data)

            # Save HTML file
            self.save_html(html_content)

            # Save data as JSON backup
            with open('timetable_data.json', 'w') as f:
                json.dump(data, f, indent=2)

            logger.info("Scraping job completed successfully!")
            return failed

        finally:
            # Always close the webdriver
            self.close_webdriver()

def main():
    """Main function to run the scraper once (optimized for GitHub Actions)."""
    scraper = RailScraper()

    logger.info("Running rail scraper...")
    failed = scraper.run_scraping_job()
    logger.info("Scraper completed!")

    # Exit non-zero so a silent scrape regression shows up as a red CI run
    # instead of quietly publishing a timetable full of holes.
    if failed:
        logger.error(f"Scraping failed for {len(failed)} direction(s): {', '.join(failed)}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()
