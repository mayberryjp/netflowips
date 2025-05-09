import requests  # Add this import
import sqlite3
import csv
import os
from src.utils import log_info, log_error, ip_network_to_range  # Assuming log_info is already defined
from src.database import connect_to_db, get_config_settings, disconnect_from_db  # Assuming connect_to_db is already defined
import logging
from src.const import CONST_SITE, IS_CONTAINER, CONST_CONSOLIDATED_DB
import zipfile

if IS_CONTAINER:
    SITE = os.getenv("SITE", CONST_SITE)

def create_geolocation_db():
    """
    Fetches the MaxMind GeoLite2 database from their API, extracts the CSV files, and creates a SQLite database.
    Also adds LOCAL_NETWORKS with SITE_NAME as country.

    Args:
        api_key (str): The API key for MaxMind's GeoLite2 database.
        blocks_csv_url (str): The URL template for the GeoLite2 country blocks CSV file.
        locations_csv_url (str): The URL template for the GeoLite2 country locations CSV file.
        temp_dir (str): Temporary directory to store downloaded and extracted files.
    """
    logger = logging.getLogger(__name__)

    config_dict = get_config_settings()
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))

    api_key = config_dict.get('MaxMindAPIKey', None)

    # Remove trailing commas to avoid creating tuples
    blocks_csv_url = "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-Country-CSV&license_key={api_key}&suffix=zip"
    locations_csv_url = "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-Country-CSV&license_key={api_key}&suffix=zip"

    temp_dir = "/database"

    try:
        # Step 1: Create temporary directory if it doesn't exist
        os.makedirs(temp_dir, exist_ok=True)

        # Step 2: Download and extract the GeoLite2 database
        log_info(logger, "[INFO] Downloading GeoLite2 database from MaxMind...")
        blocks_zip_path = os.path.join(temp_dir, "GeoLite2-Country-Blocks.zip")
        locations_zip_path = os.path.join(temp_dir, "GeoLite2-Country-Locations.zip")

        # Download blocks CSV
        blocks_response = requests.get(blocks_csv_url.format(api_key=api_key), stream=True)
        locations_response = requests.get(locations_csv_url.format(api_key=api_key), stream=True)

        if blocks_response.status_code != 200:
            log_error(logger, f"[ERROR] Failed to download country blocks CSV: {blocks_response.status_code}")
            return
        with open(blocks_zip_path, "wb") as f:
            f.write(blocks_response.content)

        if locations_response.status_code != 200:
            log_error(logger, f"[ERROR] Failed to download country locations CSV: {locations_response.status_code}")
            return
        with open(locations_zip_path, "wb") as f:
            f.write(locations_response.content)

        log_info(logger, "[INFO] Extracting ZIP files with flattened structure...")

        # Function to extract ZIP files with flattened structure
        def extract_flat(zip_file_path, destination_dir):
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    # Skip directories
                    if file_info.filename[-1] == '/':
                        continue

                    # Get just the base filename without path
                    base_filename = os.path.basename(file_info.filename)

                    # Skip if no filename (just a directory)
                    if not base_filename:
                        continue

                    # Extract the file data
                    file_data = zip_ref.read(file_info.filename)

                    # Write to destination directory with just the base filename
                    target_path = os.path.join(destination_dir, base_filename)
                    with open(target_path, 'wb') as target_file:
                        target_file.write(file_data)

        # Extract each ZIP file with flattened structure
        extract_flat(blocks_zip_path, temp_dir)
        extract_flat(locations_zip_path, temp_dir)

        # Locate the extracted CSV files (which should now be in the root of temp_dir)
        blocks_csv_path = os.path.join(temp_dir, "GeoLite2-Country-Blocks-IPv4.csv")
        locations_csv_path = os.path.join(temp_dir, "GeoLite2-Country-Locations-en.csv")

        if not os.path.exists(blocks_csv_path) or not os.path.exists(locations_csv_path):
            log_error(logger, "[ERROR] Extracted CSV files not found.")
            return

        # Step 3: Load the country locations data into a dictionary
        log_info(logger, "[INFO] Loading country locations data...")
        locations = {}
        with open(locations_csv_path, "r", encoding="utf-8") as locations_file:
            reader = csv.DictReader(locations_file)
            for row in reader:
                geoname_id = row["geoname_id"]
                country_name = row.get("country_name", "")
                locations[geoname_id] = country_name

        conn = connect_to_db(CONST_CONSOLIDATED_DB, "geolocation")
        if conn is None:
            log_error(logger, f"[ERROR] Failed to connect to the database {CONST_CONSOLIDATED_DB}.")
            return
        cursor = conn.cursor()

        # Step 4: Populate the database from the country blocks CSV file
        log_info(logger, f"[INFO] Populating the SQLite database with country blocks data...")
        with open(blocks_csv_path, "r", encoding="utf-8") as blocks_file:
            reader = csv.DictReader(blocks_file)
            for row in reader:
                network = row["network"]
                start_ip, end_ip, netmask = ip_network_to_range(network)
                if start_ip is None:
                    continue

                geoname_id = row.get("geoname_id")
                country_name = locations.get(geoname_id, None)  # Get the country name from the locations dictionary

                cursor.execute("""
                    INSERT OR IGNORE INTO geolocation (
                        network, start_ip, end_ip, netmask, country_name
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    network,
                    start_ip,
                    end_ip,
                    netmask,
                    country_name
                ))

        # After processing CSV files, add LOCAL_NETWORKS
        log_info(logger, f"[INFO] Adding LOCAL_NETWORKS to geolocation database...")

        for network in LOCAL_NETWORKS:
            start_ip, end_ip, netmask = ip_network_to_range(network)
            if start_ip is None:
                continue

            cursor.execute("""
                INSERT OR REPLACE INTO geolocation (
                    network, start_ip, end_ip, netmask, country_name
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                network,
                start_ip,
                end_ip,
                netmask,
                SITE
            ))

        # Create indexes for IP range lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ip_range ON geolocation(start_ip, end_ip)")

        # Commit changes and close the connection
        conn.commit()
        disconnect_from_db(conn)

        log_info(logger, f"[INFO] Geolocation database {CONST_CONSOLIDATED_DB} created successfully.")

    except Exception as e:
        log_error(logger, f"[ERROR] Error creating geolocation database: {e}")

def load_geolocation_data():
    """
    Load geolocation data from the database into memory.

    Returns:
        list: A list of tuples containing (network, country_name).
    """
    logger = logging.getLogger(__name__)
    geolocation_data = []
    conn = connect_to_db(CONST_CONSOLIDATED_DB, "geolocation")
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT network, start_ip, end_ip, netmask, country_name FROM geolocation")
            geolocation_data = cursor.fetchall()
            log_info(logger, f"[INFO] Loaded {len(geolocation_data)} geolocation entries into memory.")
        except sqlite3.Error as e:
            log_error(logger, f"[ERROR] Error loading geolocation data: {e}")
        finally:
            disconnect_from_db(conn)
    return geolocation_data