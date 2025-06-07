#!/usr/bin/env python3
"""
Rail Timetable Scraper Web App
Scrapes two rail websites daily and generates a static HTML timetable page.
"""

import requests
from bs4 import BeautifulSoup
import json
import datetime
import schedule
import time
import os
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
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
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
            "routes": [
                {
                    "name": "Laagri to Tallinn",
                    "url_template": "https://elron.pilet.ee/et/otsing/Laagri/Tallinn/{date}",
                    "departure_station": "Laagri",
                    "arrival_station": "Tallinn",
                    "selectors": {
                        "trip_container": ".trip-summary__timespan"
                    }
                },
                {
                    "name": "Tallinn to Laagri", 
                    "url_template": "https://elron.pilet.ee/et/otsing/Tallinn/Laagri/{date}",
                    "departure_station": "Tallinn",
                    "arrival_station": "Laagri",
                    "selectors": {
                        "trip_container": ".trip-summary__timespan"
                    }
                }
            ],
            "output_file": "timetable.html",
            "scrape_time": "06:00"
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
        current_date = datetime.datetime.now().strftime('%Y-%m-%d')
        return url_template.format(date=current_date)
    
    def scrape_route(self, route_config: Dict) -> List[Dict]:
        """Scrape timetable data for a single route using Selenium."""
        try:
            # Generate URL with current date
            url = self.get_current_date_url(route_config['url_template'])
            logger.info(f"Scraping {route_config['name']} from {url}")
            
            # Load the page
            self.driver.get(url)
            
            # Wait for the page to load and data to populate
            logger.info("Waiting for dynamic content to load...")
            time.sleep(5)  # Wait 5 seconds for dynamic content
            
            # Additional wait for specific elements to be present
            try:
                # Wait up to 10 seconds for at least one trip container to appear
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, route_config['selectors']['trip_container']))
                )
                logger.info("Trip containers found, proceeding with extraction")
            except TimeoutException:
                logger.warning("Timeout waiting for trip containers, proceeding anyway")
            
            # Get page source and parse with BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Find all trip timespan containers
            trip_containers = soup.select(route_config['selectors']['trip_container'])
            
            timetable = []
            
            # Extract times from each trip container
            import re
            time_pattern = re.compile(r'\b([0-2]?[0-9]):([0-5][0-9])\b')
            
            for container in trip_containers:

                span_times = [
                    match.group()
                    for span in container.find_all('span')
                    if (match := time_pattern.search(span.get_text()))
                ]
                
                if len(span_times) >= 2:
                    departure_time = span_times[0]
                    arrival_time = span_times[1]
            
                    trip_data = {
                        'departure': departure_time,
                        'arrival': arrival_time
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
            
            logger.info(f"Found {len(unique_timetable)} unique schedules for {route_config['name']}")
            return unique_timetable
        except Exception as e:
            logger.error(f"Error scraping {route_config['name']}: {str(e)}")
            return []
    
    def scrape_all_routes(self) -> Dict:
        """Scrape all configured routes."""
        all_data = {
            'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'routes': {}
        }
        
        for route in self.config['routes']:
            timetable = self.scrape_route(route)
            all_data['routes'][route['name']] = {
                'departure_station': route['departure_station'],
                'arrival_station': route['arrival_station'],
                'timetable': timetable
            }
        
        return all_data
    
    def generate_html(self, data: Dict) -> str:
        """Generate HTML page from scraped data with client-side time filtering."""
        html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Rail Timetables</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .header {{
                text-align: center;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                border-radius: 10px;
                margin-bottom: 30px;
                position: relative;
            }}
            .current-time {{
                position: absolute;
                top: 10px;
                right: 20px;
                font-size: 0.9em;
                opacity: 0.9;
            }}
            .route {{
                background: white;
                margin: 20px 0;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .route h2 {{
                color: #333;
                border-bottom: 3px solid #667eea;
                padding-bottom: 10px;
                margin-bottom: 15px;
            }}
            .route-info {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 5px;
                margin: 15px 0;
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
            }}
            .route-details {{
                display: flex;
                gap: 20px;
                flex-wrap: wrap;
            }}
            .filter-controls {{
                display: flex;
                gap: 10px;
                align-items: center;
                margin-top: 10px;
            }}
            .filter-toggle {{
                background: #667eea;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.9em;
                transition: background-color 0.3s;
            }}
            .filter-toggle:hover {{
                background: #5a6fd8;
            }}
            .filter-toggle.active {{
                background: #28a745;
            }}
            .show-all-toggle {{
                background: #6c757d;
            }}
            .show-all-toggle:hover {{
                background: #5a6268;
            }}
            .upcoming-count {{
                color: #28a745;
                font-weight: bold;
                margin-left: 10px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }}
            th, td {{
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }}
            th {{
                background-color: #667eea;
                color: white;
            }}
            tr:nth-child(even) {{
                background-color: #f2f2f2;
            }}
            tr:hover {{
                background-color: #e8f4f8;
            }}
            .time-cell {{
                font-weight: bold;
                font-family: 'Courier New', monospace;
            }}
            .past-time {{
                opacity: 0.5;
                color: #999;
            }}
            .next-train {{
                background-color: #d4edda !important;
                border-left: 4px solid #28a745;
            }}
            .leaving-soon {{
                background-color: #fff3cd !important;
                border-left: 4px solid #ffc107;
            }}
            .hidden {{
                display: none !important;
            }}
            .last-updated {{
                text-align: center;
                color: #666;
                font-style: italic;
                margin-top: 30px;
            }}
            .no-data {{
                text-align: center;
                color: #999;
                padding: 20px;
                font-style: italic;
            }}
            .no-upcoming {{
                text-align: center;
                color: #dc3545;
                padding: 20px;
                font-style: italic;
                background: #f8d7da;
                border-radius: 5px;
                margin-top: 15px;
            }}
            .status-indicator {{
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                margin-right: 8px;
            }}
            .status-upcoming {{
                background-color: #28a745;
            }}
            .status-soon {{
                background-color: #ffc107;
            }}
            .status-past {{
                background-color: #dc3545;
            }}
            @media (max-width: 768px) {{
                .route-info {{
                    flex-direction: column;
                    align-items: flex-start;
                }}
                .filter-controls {{
                    margin-top: 15px;
                    flex-wrap: wrap;
                }}
                .current-time {{
                    position: static;
                    margin-top: 10px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚂 Rail Timetables</h1>
            <p>Current train schedules for your daily commute</p>
            <div class="current-time" id="currentTime"></div>
        </div>
    """
        
        for route_name, route_data in data['routes'].items():
            # Create a unique ID for each route
            route_id = route_name.lower().replace(' ', '-').replace('to', 'to')
            
            html_template += f"""
        <div class="route" id="route-{route_id}">
            <h2>{route_name}</h2>
            <div class="route-info">
                <div class="route-details">
                    <span><strong>From:</strong> {route_data['departure_station']}</span>
                    <span><strong>To:</strong> {route_data['arrival_station']}</span>
                </div>
                <div class="filter-controls">
                    <button class="filter-toggle active" onclick="toggleFilter('{route_id}', true)">
                        Future Only
                    </button>
                    <button class="filter-toggle show-all-toggle" onclick="toggleFilter('{route_id}', false)">
                        Show All
                    </button>
                    <span class="upcoming-count" id="count-{route_id}"></span>
                </div>
            </div>
    """
            
            if route_data['timetable']:
                html_template += f"""
            <table id="table-{route_id}">
                <thead>
                    <tr>
                        <th>Status</th>
                        <th>Departure Time</th>
                        <th>Arrival Time</th>
                        <th>Time Until Departure</th>
                    </tr>
                </thead>
                <tbody>
    """
                for i, schedule in enumerate(route_data['timetable']):
                    html_template += f"""
                    <tr class="train-row" data-route="{route_id}" data-departure="{schedule['departure']}" data-index="{i}">
                        <td class="status-cell">
                            <span class="status-indicator" id="status-{route_id}-{i}"></span>
                            <span id="status-text-{route_id}-{i}"></span>
                        </td>
                        <td class="time-cell departure-time">{schedule['departure']}</td>
                        <td class="time-cell arrival-time">{schedule['arrival']}</td>
                        <td class="countdown" id="countdown-{route_id}-{i}"></td>
                    </tr>
    """
                html_template += """
                </tbody>
            </table>
            <div class="no-upcoming hidden" id="no-upcoming-""" + route_id + """">
                No upcoming trains for today. Check back tomorrow!
            </div>
    """
            else:
                html_template += """
            <div class="no-data">No timetable data available</div>
    """
            
            html_template += "    </div>\n"
        
        html_template += f"""
        <div class="last-updated">
            Last updated: {data['last_updated']}
        </div>
    
        <script>
            // Global state
            const routeFilters = {{}};
            
            // Initialize filters (all routes start with future-only filter active)
            {json.dumps([route['name'].lower().replace(' ', '-').replace('to', 'to') for route in self.config['routes']])}.forEach(routeId => {{
                routeFilters[routeId] = true; // true = show future only, false = show all
            }});
    
            function parseTime(timeStr) {{
                const [hours, minutes] = timeStr.split(':').map(Number);
                const now = new Date();
                const timeToday = new Date(now.getFullYear(), now.getMonth(), now.getDate(), hours, minutes);
                
                // If the time has passed today, assume it's for tomorrow
                if (timeToday < now) {{
                    timeToday.setDate(timeToday.getDate() + 1);
                }}
                
                return timeToday;
            }}
    
            function formatTimeUntil(targetTime) {{
                const now = new Date();
                const diffMs = targetTime - now;
                
                if (diffMs < 0) {{
                    return 'Departed';
                }}
                
                const diffMinutes = Math.floor(diffMs / (1000 * 60));
                const diffHours = Math.floor(diffMinutes / 60);
                const remainingMinutes = diffMinutes % 60;
                
                if (diffHours > 0) {{
                    return `${{diffHours}}h ${{remainingMinutes}}m`;
                }} else if (diffMinutes > 0) {{
                    return `${{diffMinutes}}m`;
                }} else {{
                    return 'Now';
                }}
            }}
    
            function updateTimeDisplay() {{
                const now = new Date();
                document.getElementById('currentTime').textContent = now.toLocaleTimeString();
            }}
    
            function updateTrainStatus() {{
                const now = new Date();
                
                document.querySelectorAll('.train-row').forEach(row => {{
                    const routeId = row.dataset.route;
                    const departureTime = row.dataset.departure;
                    const index = row.dataset.index;
                    const targetTime = parseTime(departureTime);
                    const diffMs = targetTime - now;
                    const diffMinutes = Math.floor(diffMs / (1000 * 60));
                    
                    // Update countdown
                    const countdownEl = document.getElementById(`countdown-${{routeId}}-${{index}}`);
                    const statusIndicator = document.getElementById(`status-${{routeId}}-${{index}}`);
                    const statusText = document.getElementById(`status-text-${{routeId}}-${{index}}`);
                    
                    if (diffMs < 0) {{
                        // Train has departed
                        row.classList.add('past-time');
                        row.classList.remove('next-train', 'leaving-soon');
                        statusIndicator.className = 'status-indicator status-past';
                        statusText.textContent = 'Departed';
                        countdownEl.textContent = 'Departed';
                    }} else if (diffMinutes <= 15) {{
                        // Train leaving soon (within 15 minutes)
                        row.classList.add('leaving-soon');
                        row.classList.remove('past-time', 'next-train');
                        statusIndicator.className = 'status-indicator status-soon';
                        statusText.textContent = 'Soon';
                        countdownEl.textContent = formatTimeUntil(targetTime);
                    }} else {{
                        // Future train
                        row.classList.add('next-train');
                        row.classList.remove('past-time', 'leaving-soon');
                        statusIndicator.className = 'status-indicator status-upcoming';
                        statusText.textContent = 'Upcoming';
                        countdownEl.textContent = formatTimeUntil(targetTime);
                    }}
                    
                    // Apply filtering
                    const showFutureOnly = routeFilters[routeId];
                    if (showFutureOnly && diffMs < 0) {{
                        row.classList.add('hidden');
                    }} else {{
                        row.classList.remove('hidden');
                    }}
                }});
                
                // Update counters for each route
                Object.keys(routeFilters).forEach(routeId => {{
                    updateUpcomingCount(routeId);
                }});
            }}
    
            function updateUpcomingCount(routeId) {{
                const rows = document.querySelectorAll(`[data-route="${{routeId}}"]`);
                const upcomingCount = Array.from(rows).filter(row => {{
                    const departureTime = row.dataset.departure;
                    const targetTime = parseTime(departureTime);
                    const now = new Date();
                    return targetTime > now;
                }}).length;
                
                const countEl = document.getElementById(`count-${{routeId}}`);
                if (countEl) {{
                    countEl.textContent = `(${{upcomingCount}} upcoming)`;
                }}
                
                // Show/hide no upcoming message
                const noUpcomingEl = document.getElementById(`no-upcoming-${{routeId}}`);
                const tableEl = document.getElementById(`table-${{routeId}}`);
                
                if (routeFilters[routeId] && upcomingCount === 0) {{
                    if (noUpcomingEl) noUpcomingEl.classList.remove('hidden');
                    if (tableEl) tableEl.classList.add('hidden');
                }} else {{
                    if (noUpcomingEl) noUpcomingEl.classList.add('hidden');
                    if (tableEl) tableEl.classList.remove('hidden');
                }}
            }}
    
            function toggleFilter(routeId, showFutureOnly) {{
                routeFilters[routeId] = showFutureOnly;
                
                // Update button states
                const routeDiv = document.getElementById(`route-${{routeId}}`);
                const buttons = routeDiv.querySelectorAll('.filter-toggle');
                buttons.forEach(btn => btn.classList.remove('active'));
                
                if (showFutureOnly) {{
                    routeDiv.querySelector('.filter-toggle:first-of-type').classList.add('active');
                }} else {{
                    routeDiv.querySelector('.show-all-toggle').classList.add('active');
                }}
                
                // Reapply filtering
                updateTrainStatus();
            }}
    
            // Initialize and start updates
            function init() {{
                updateTimeDisplay();
                updateTrainStatus();
                
                // Update every 30 seconds
                setInterval(() => {{
                    updateTimeDisplay();
                    updateTrainStatus();
                }}, 30000);
            }}
    
            // Start when page loads
            document.addEventListener('DOMContentLoaded', init);
        </script>
    </body>
    </html>
    """
        return html_template
    
    def save_html(self, html_content: str):
        """Save HTML content to file."""
        output_file = self.config['output_file']
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"HTML file saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving HTML file: {str(e)}")
    
    def run_scraping_job(self):
        """Run the complete scraping job."""
        logger.info("Starting daily scraping job...")
        
        try:
            # Scrape all routes
            data = self.scrape_all_routes()
            
            # Generate HTML
            html_content = self.generate_html(data)
            
            # Save HTML file
            self.save_html(html_content)
            
            # Save data as JSON backup
            with open('timetable_data.json', 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info("Scraping job completed successfully!")
            
        finally:
            # Always close the webdriver
            self.close_webdriver()

def main():
    """Main function to run the scraper once (optimized for GitHub Actions)."""
    scraper = RailScraper()
    
    logger.info("Running rail scraper...")
    scraper.run_scraping_job()
    logger.info("Scraper completed!")

if __name__ == "__main__":
    main()
