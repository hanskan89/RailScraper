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
        """Generate HTML page from scraped data."""
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
        }}
        .route-info {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 0;
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
    </style>
</head>
<body>
    <div class="header">
        <h1>🚂 Rail Timetables</h1>
        <p>Current train schedules for your daily commute</p>
    </div>
"""
        
        for route_name, route_data in data['routes'].items():
            html_template += f"""
    <div class="route">
        <h2>{route_name}</h2>
        <div class="route-info">
            <strong>From:</strong> {route_data['departure_station']} 
            <strong>To:</strong> {route_data['arrival_station']}
        </div>
"""
            
            if route_data['timetable']:
                html_template += """
        <table>
            <thead>
                <tr>
                    <th>Departure Time</th>
                    <th>Arrival Time</th>
                </tr>
            </thead>
            <tbody>
"""
                for schedule in route_data['timetable']:
                    html_template += f"""
                <tr>
                    <td>{schedule['departure']}</td>
                    <td>{schedule['arrival']}</td>
                </tr>
"""
                html_template += """
            </tbody>
        </table>
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
