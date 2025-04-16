import sqlite3
import csv
import os
from utils import log_info  # Assuming log_info is already defined
from database import connect_to_db  # Assuming connect_to_db is already defined

def create_geolocation_db(
    blocks_csv_path="geolite/GeoLite2-Country-Blocks-IPv4.csv",
    locations_csv_path="geolite/GeoLite2-Country-Locations-en.csv",
    db_name="/database/geolocation.db"
):
    """
    Reads the MaxMind GeoLite2 database from CSV files and creates a SQLite database.

    Args:
        blocks_csv_path (str): The path to the GeoLite2 country blocks CSV file.
        locations_csv_path (str): The path to the GeoLite2 country locations CSV file.
        db_name (str): The name of the SQLite database to create.
    """
    try:
        # Step 1: Check if the CSV files exist
        if not os.path.exists(blocks_csv_path):
            log_info(None, f"[ERROR] Country blocks CSV file not found at {blocks_csv_path}.")
            return
        if not os.path.exists(locations_csv_path):
            log_info(None, f"[ERROR] Country locations CSV file not found at {locations_csv_path}.")
            return

        # Step 2: Load the country locations data into a dictionary
        log_info(None, "Loading country locations data...")
        locations = {}
        with open(locations_csv_path, "r", encoding="utf-8") as locations_file:
            reader = csv.DictReader(locations_file)
            for row in reader:
                geoname_id = row["geoname_id"]
                country_name = row.get("country_name", "")
                locations[geoname_id] = country_name

        # Step 3: Create the SQLite database
        log_info(None, f"Creating SQLite database: {db_name}...")
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Create the table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geolocation (
                network TEXT PRIMARY KEY,
                geoname_id INTEGER,
                country_name TEXT,
                registered_country_geoname_id INTEGER,
                represented_country_geoname_id INTEGER,
                is_anonymous_proxy INTEGER,
                is_satellite_provider INTEGER
            )
        """)

        # Step 4: Populate the database from the country blocks CSV file
        log_info(None, "Populating the SQLite database with country blocks data...")
        with open(blocks_csv_path, "r", encoding="utf-8") as blocks_file:
            reader = csv.DictReader(blocks_file)
            for row in reader:
                geoname_id = row.get("geoname_id")
                country_name = locations.get(geoname_id, None)  # Get the country name from the locations dictionary
                cursor.execute("""
                    INSERT OR IGNORE INTO geolocation (
                        network, geoname_id, country_name, registered_country_geoname_id,
                        represented_country_geoname_id, is_anonymous_proxy, is_satellite_provider
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["network"],
                    geoname_id,
                    country_name,
                    row.get("registered_country_geoname_id"),
                    row.get("represented_country_geoname_id"),
                    row.get("is_anonymous_proxy"),
                    row.get("is_satellite_provider")
                ))

        # Commit changes and close the connection
        conn.commit()
        conn.close()

        log_info(None, f"Geolocation database {db_name} created successfully.")

    except Exception as e:
        log_info(None, f"Error creating geolocation database: {e}")

def load_geolocation_data():
    """
    Load geolocation data from the database into memory.

    Returns:
        list: A list of tuples containing (network, country_name).
    """
    geolocation_data = []
    conn = connect_to_db("/database/geolocation.db")
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT network, country_name FROM geolocation")
            geolocation_data = cursor.fetchall()
            log_info(None, f"[INFO] Loaded {len(geolocation_data)} geolocation entries into memory.")
        except sqlite3.Error as e:
            log_info(None, f"[ERROR] Error loading geolocation data: {e}")
        finally:
            conn.close()
    return geolocation_data