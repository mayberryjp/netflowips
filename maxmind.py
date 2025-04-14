import sqlite3
import csv
import os
import requests
import gzip
import shutil
from utils import log_info  # Assuming log_info is already defined

def create_geolocation_db(maxmind_url, db_name="geolocation.db"):
    """
    Downloads the MaxMind GeoLite2 database, extracts it, and creates a SQLite database.

    Args:
        maxmind_url (str): The URL to download the MaxMind GeoLite2 database.
        db_name (str): The name of the SQLite database to create.
    """
    try:
        # Step 1: Download the MaxMind GeoLite2 database
        log_info(None, "Downloading MaxMind GeoLite2 database...")
        response = requests.get(maxmind_url, stream=True)
        if response.status_code != 200:
            log_info(None, f"Failed to download database. HTTP Status: {response.status_code}")
            return

        # Save the downloaded file
        compressed_file = "GeoLite2-City.tar.gz"
        with open(compressed_file, "wb") as f:
            f.write(response.content)

        # Step 2: Extract the downloaded file
        log_info(None, "Extracting the database...")
        extracted_dir = "GeoLite2-City"
        with gzip.open(compressed_file, "rb") as f_in:
            with open("GeoLite2-City.tar", "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        shutil.unpack_archive("GeoLite2-City.tar", extracted_dir)

        # Locate the CSV file (GeoLite2-City-Blocks-IPv4.csv)
        csv_file = None
        for root, dirs, files in os.walk(extracted_dir):
            for file in files:
                if file.endswith("GeoLite2-City-Blocks-IPv4.csv"):
                    csv_file = os.path.join(root, file)
                    break

        if not csv_file:
            log_info(None, "GeoLite2 CSV file not found.")
            return

        # Step 3: Create the SQLite database
        log_info(None, f"Creating SQLite database: {db_name}...")
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Create the table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geolocation (
                network TEXT PRIMARY KEY,
                geoname_id INTEGER,
                registered_country_geoname_id INTEGER,
                represented_country_geoname_id INTEGER,
                is_anonymous_proxy INTEGER,
                is_satellite_provider INTEGER,
                latitude REAL,
                longitude REAL,
                accuracy_radius INTEGER
            )
        """)

        # Step 4: Populate the database from the CSV file
        log_info(None, "Populating the SQLite database...")
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cursor.execute("""
                    INSERT OR IGNORE INTO geolocation (
                        network, geoname_id, registered_country_geoname_id,
                        represented_country_geoname_id, is_anonymous_proxy,
                        is_satellite_provider, latitude, longitude, accuracy_radius
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["network"],
                    row.get("geoname_id"),
                    row.get("registered_country_geoname_id"),
                    row.get("represented_country_geoname_id"),
                    row.get("is_anonymous_proxy"),
                    row.get("is_satellite_provider"),
                    row.get("latitude"),
                    row.get("longitude"),
                    row.get("accuracy_radius")
                ))

        # Commit changes and close the connection
        conn.commit()
        conn.close()

        log_info(None, f"Geolocation database {db_name} created successfully.")

        # Clean up temporary files
        os.remove(compressed_file)
        os.remove("GeoLite2-City.tar")
        shutil.rmtree(extracted_dir)

    except Exception as e:
        log_info(None, f"Error creating geolocation database: {e}")