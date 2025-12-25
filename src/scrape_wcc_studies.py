#!/usr/bin/env python3
import os
import time
import random
import argparse
import requests
import urllib3
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# Forcefully suppress security warnings for corporate/firewall environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Hardcoded Recent Matches to bypass Lichess's changing page structure
RECENT_MATCHES = [
    ("2021_Carlsen-Nepomniachtchi", "y0SoVnA0"),
    ("2023_Ding-Nepomniachtchi", "kjtf5d2z"),
    ("2024_Ding-Dommaraju", "LF4x850G")
]

def scrape_wcc_studies(start_year):
    output_dir = 'data/WCC_Lichess'
    os.makedirs(output_dir, exist_ok=True)
    
    # Session ensures verify=False is used for index AND file downloads
    session = requests.Session()
    session.verify = False 
    session.headers.update({"User-Agent": "WCC-Scraper-Bot/2.0"})

    study_links = []

    # 1. Add Hardcoded matches if they meet the year criteria
    for name, sid in RECENT_MATCHES:
        try:
            match_year = int(name.split('_')[0])
            if match_year >= start_year:
                study_links.append((name, sid))
        except:
            continue

    # 2. Scrape the historical index for older matches
    url = "https://lichess.org/page/world-championships"
    print(f"Fetching index: {url}")
    try:
        response = session.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the specific section boundaries
        start_node = soup.find(lambda t: t.name in ['h2', 'h3'] and "World Championship Matches" in t.text)
        end_node = soup.find(lambda t: t.name in ['h2', 'h3'] and "Women's" in t.text)
        
        if start_node:
            current = start_node.next_element
            while current and current != end_node:
                # Look for study links inside this section
                if hasattr(current, 'name') and current.name == 'a' and 'study' in current.get('href', ''):
                    full_text = current.parent.get_text()
                    year_match = re.search(r'\b(18|19|20)\d{2}\b', full_text)
                    
                    if year_match:
                        year = int(year_match.group(0))
                        if year >= start_year:
                            sid = current['href'].split('/')[-1]
                            
                            # Create a clean filename
                            label_text = current.parent.get_text(strip=True).replace(" vs. ", "-").replace(" ", "_")
                            clean_label = "".join(c for c in label_text if c.isalnum() or c in ('-', '_')).split('^')[0]
                            
                            # Avoid duplicates from hardcoded list
                            if not any(sid == s[1] for s in study_links):
                                study_links.append((clean_label, sid))
                current = current.next_element
    except Exception as e:
        print(f"Historical index scrape failed: {e}")

    # 3. Execution
    if not study_links:
        print(f"No matches found for year >= {start_year}.")
        return

    print(f"Processing {len(study_links)} matches...")
    for name, sid in study_links:
        file_path = os.path.join(output_dir, f"{name}.pgn")
        
        if os.path.exists(file_path):
            print(f"Skipping {name} (Exists)")
            continue

        print(f"Downloading: {name}...")
        export_url = f"https://lichess.org/api/study/{sid}.pgn"
        
        # Random sleep to avoid rate limiting
        time.sleep(random.uniform(1.2, 2.2))
        
        try:
            res = session.get(export_url)
            if res.status_code == 200:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(res.text)
                print("   Success.")
            else:
                print(f"   Failed: HTTP {res.status_code}")
        except Exception as e:
            print(f"   Error: {e}")

    print("\nTask Complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--start_match_date', type=int, default=1800)
    args = parser.parse_args()
    
    scrape_wcc_studies(args.start_match_date)