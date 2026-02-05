#!/usr/bin/env python3
"""
Comprehensive LQK Site Updater
This script handles everything needed to update the site:
1. Parses LQK.txt
2. Handles CSV files
3. Removes duplicates
4. Converts to site format
5. Updates site/cars.json and LQK.json
"""

import re
import json
import csv
import os
import sys
import subprocess
from datetime import datetime

# ============================================================================
# PARSING FUNCTIONS
# ============================================================================

def parse_lqk_file(input_file):
    """Parse LQK.txt and return list of car entries"""

    cars = []
    current_car = {}

    if not os.path.exists(input_file):
        print(f"  Warning: {input_file} not found")
        return []

    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()

            # Match car info line: "YEAR MAKE MODEL available for parts YEAR MAKE MODEL"
            car_match = re.match(r'^(\d{4})\s+([^ ]+)\s+(.+?)\s+available for parts', line)
            if car_match:
                # Save previous car if exists
                if current_car and 'year' in current_car:
                    cars.append(current_car)

                # Start new car entry
                year = car_match.group(1)
                make = car_match.group(2)
                model = car_match.group(3).strip()
                current_car = {
                    'year': year,
                    'make': make,
                    'model': model,
                    'location': '',
                    'available': ''
                }

            # Match section/row/space line
            section_match = re.search(r'Section:\s*(.+?)\s+Row:\s*(.+?)\s+Space:\s*(.+)', line)
            if section_match and current_car:
                section = section_match.group(1).strip()
                row = section_match.group(2).strip()
                space = section_match.group(3).strip()
                current_car['location'] = f"{section} {row} {space}".strip()

            # Match available date line
            date_match = re.search(r'Available:\s+(.+)', line)
            if date_match and current_car:
                current_car['available'] = date_match.group(1).strip()

    # Don't forget the last car
    if current_car and 'year' in current_car:
        cars.append(current_car)

    return cars

def parse_csv_file(csv_file):
    """Parse CSV file and return list of car entries"""

    cars = []

    if not os.path.exists(csv_file):
        print(f"  Warning: {csv_file} not found")
        return []

    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Parse car name into make and model
                car_name = row.get('car', '').strip()
                parts = car_name.split(' ', 1)

                make = parts[0] if parts else ''
                model = parts[1] if len(parts) > 1 else ''

                cars.append({
                    'year': row.get('year', '').strip(),
                    'make': make,
                    'model': model,
                    'location': row.get('location', '').strip(),
                    'available': row.get('date', '').strip()
                })
    except Exception as e:
        print(f"  Error parsing {csv_file}: {e}")

    return cars

# ============================================================================
# DUPLICATE REMOVAL
# ============================================================================

def remove_duplicates(cars):
    """Remove duplicate entries based on year, make, model (merges different locations)"""

    # Group by year, make, model only
    car_groups = {}

    for car in cars:
        # Create key by car type only (not location or date)
        key = (car['year'], car['make'], car['model'])

        if key not in car_groups:
            car_groups[key] = []

        car_groups[key].append(car)

    # For each group, keep only the one with the most recent date
    unique_cars = []
    duplicates_removed = 0

    for key, group in car_groups.items():
        if len(group) == 1:
            unique_cars.append(group[0])
        else:
            # Multiple entries for same car type - keep the one with newest date
            duplicates_removed += len(group) - 1

            # Sort by date and keep the newest
            group_sorted = sorted(group, key=lambda x: parse_date(x['available']), reverse=True)
            unique_cars.append(group_sorted[0])

    print(f"  Removed {duplicates_removed} duplicate entries")

    return unique_cars

# ============================================================================
# DATA CONVERSION
# ============================================================================

def parse_date(date_str):
    """Parse date string for sorting"""
    parts = date_str.split('/')
    if len(parts) == 3:
        month, day, year = map(int, parts)
        return (year, month, day)
    return (0, 0, 0)

def convert_to_site_format(cars):
    """Convert car data to site format and sort by date"""

    # Remove duplicates
    cars = remove_duplicates(cars)

    # Sort by available date (newest first)
    cars_sorted = sorted(cars, key=lambda x: parse_date(x['available']), reverse=True)

    return cars_sorted

def save_to_json(data, output_file):
    """Save data to JSON file"""

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def save_to_lqk_consolidated(data, output_file):
    """Save data to LQK.json in consolidated format"""

    # Group by car (make + model) and year
    car_groups = {}

    for car in data:
        car_name = f"{car['make']} {car['model']}"
        year = car['year']
        key = (car_name, year)

        if key not in car_groups:
            car_groups[key] = {'dates': [], 'locations': []}

        car_groups[key]['dates'].append(car['available'])
        car_groups[key]['locations'].append(car['location'])

    # Convert to consolidated format
    consolidated = []
    for (car_name, year), data in sorted(car_groups.items()):
        # Get unique dates and locations (keeping first occurrence order)
        unique_dates = []
        seen_dates = set()
        for date in data['dates']:
            if date not in seen_dates:
                unique_dates.append(date)
                seen_dates.add(date)

        unique_locations = []
        seen_locations = set()
        for loc in data['locations']:
            if loc not in seen_locations:
                unique_locations.append(loc)
                seen_locations.add(loc)

        # Format dates string with counts
        date_count = len(unique_dates)
        if date_count == 1:
            dates_str = f"(1) {unique_dates[0]}"
        else:
            dates_str = ", ".join([f"({i+1}) {date}" for i, date in enumerate(unique_dates)])

        # Format locations string with counts
        loc_count = len(unique_locations)
        if loc_count == 1:
            locations_str = f"(1) {unique_locations[0]}"
        else:
            locations_str = ", ".join([f"({i+1}) {loc}" for i, loc in enumerate(unique_locations)])

        consolidated.append({
            'car': car_name,
            'year': year,
            'count': str(date_count),
            'dates': dates_str,
            'locations': locations_str
        })

    # Sort by car name, then year
    consolidated.sort(key=lambda x: (x['car'], x['year']))

    # Save to JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(consolidated, f, indent=2)

# ============================================================================
# SERVER FUNCTIONS
# ============================================================================

def start_server(port=8001):
    """Start the web server in the site directory"""

    site_dir = Path(__file__).parent.parent / "site"

    if not site_dir.exists():
        print(f"Error: Site directory not found at {site_dir}")
        return False

    try:
        print(f"\nStarting server on port {port}...")
        print(f"Serving from: {site_dir}")
        print(f"Open: http://localhost:{port}/")
        print("\nPress Ctrl+C to stop the server")

        os.chdir(site_dir)
        subprocess.run(['python3', '-m', 'http.server', str(port)])

    except KeyboardInterrupt:
        print("\nServer stopped.")
        return True
    except Exception as e:
        print(f"Error starting server: {e}")
        return False

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    # Configuration
    lqk_file = "LQK.txt"
    csv_files = ["LQK.csv", "LQK_consolidated.csv"]
    site_json = "../site/cars.json"
    lqk_json = "LQK.json"
    port = 8001

    print("=" * 70)
    print("LQK Site Updater")
    print("=" * 70)

    all_cars = []

    # Step 1: Parse LQK.txt
    print(f"\n[1/4] Parsing {lqk_file}...")
    cars_from_txt = parse_lqk_file(lqk_file)
    if cars_from_txt:
        all_cars.extend(cars_from_txt)
        print(f"  ✓ Found {len(cars_from_txt)} entries from LQK.txt")

    # Step 2: Parse CSV files (if they exist)
    print(f"\n[2/4] Parsing CSV files...")
    csv_found = False
    for csv_file in csv_files:
        if os.path.exists(csv_file):
            cars_from_csv = parse_csv_file(csv_file)
            if cars_from_csv:
                all_cars.extend(cars_from_csv)
                print(f"  ✓ Found {len(cars_from_csv)} entries from {csv_file}")
                csv_found = True

    if not all_cars:
        print("\n  No data found! Please ensure LQK.txt exists.")
        return 1

    print(f"  Total entries before deduplication: {len(all_cars)}")

    # Step 3: Convert and deduplicate
    print(f"\n[3/4] Processing data...")
    cars_final = convert_to_site_format(all_cars)
    print(f"  ✓ Final count: {len(cars_final)} unique entries")

    # Show date range
    if cars_final:
        dates = [car['available'] for car in cars_final if car.get('available')]
        if dates:
            dates_sorted = sorted(dates, key=parse_date, reverse=True)
            print(f"  Date range: {dates_sorted[-1]} to {dates_sorted[0]}")

        # Show some examples
        print("\n  Newest 5 entries:")
        for i, car in enumerate(cars_final[:5], 1):
            loc = car.get('location', 'N/A')[:35]
            print(f"    {i}. {car['year']} {car['make']} {car['model']} - {car['available']} - {loc}")

    # Step 4: Save files
    print(f"\n[4/4] Saving files...")
    save_to_json(cars_final, site_json)
    print(f"  ✓ Saved {len(cars_final)} entries to site/cars.json")

    save_to_lqk_consolidated(cars_final, lqk_json)
    print(f"  ✓ Saved {len(cars_final)} consolidated entries to {lqk_json}")

    print(f"\n{'=' * 70}")
    print("✓ Site updated successfully!")
    print("=" * 70)

    # Ask if user wants to start server
    try:
        response = input("\nDo you want to start the web server? (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            start_server(port)
        else:
            print(f"\nTo view the site:")
            print(f"  cd ../site && python3 -m http.server {port}")
            print(f"  Then open: http://localhost:{port}/")
    except KeyboardInterrupt:
        print("\nExiting...")

    return 0

if __name__ == "__main__":
    sys.exit(main())
