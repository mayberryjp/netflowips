import sqlite3
import csv
import os
from utils import log_info, log_error, ip_network_to_range  # Assuming log_info is already defined
from database import connect_to_db, create_database, get_config_settings  # Assuming connect_to_db is already defined
import logging
from const import CONST_SITE, IS_CONTAINER, CONST_GEOLOCATION_DB, CONST_CREATE_GEOLOCATION_SQL

if IS_CONTAINER:
    SITE = os.getenv("SITE", CONST_SITE)

def create_geolocation_db(
    blocks_csv_path="/database/geolite/GeoLite2-Country-Blocks-IPv4.csv",
    locations_csv_path="/database/geolite/GeoLite2-Country-Locations-en.csv",
):
    """
    Reads the MaxMind GeoLite2 database from CSV files and creates a SQLite database.
    Also adds LOCAL_NETWORKS with SITE_NAME as country.

    Args:
        blocks_csv_path (str): The path to the GeoLite2 country blocks CSV file.
        locations_csv_path (str): The path to the GeoLite2 country locations CSV file.
        db_name (str): The name of the SQLite database to create.
    """
    logger = logging.getLogger(__name__)
    try:
        # Step 1: Check if the CSV files exist
        if not os.path.exists(blocks_csv_path):
            log_error(logger, f"[ERROR] Country blocks CSV file not found at {blocks_csv_path}.")
            return
        if not os.path.exists(locations_csv_path):
            log_error(logger, f"[ERROR] Country locations CSV file not found at {locations_csv_path}.")
            return

        # Step 2: Load the country locations data into a dictionary
        log_info(logger, "[INFO] Loading country locations data...")
        locations = {}
        with open(locations_csv_path, "r", encoding="utf-8") as locations_file:
            reader = csv.DictReader(locations_file)
            for row in reader:
                geoname_id = row["geoname_id"]
                country_name = row.get("country_name", "")
                locations[geoname_id] = country_name


        create_database(CONST_GEOLOCATION_DB, CONST_CREATE_GEOLOCATION_SQL)

        conn=connect_to_db(CONST_GEOLOCATION_DB)
        if conn is None:
            log_error(logger, f"[ERROR] Failed to connect to the database {CONST_GEOLOCATION_DB}.")
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
        config_dict = get_config_settings()
        for network in config_dict['LocalNetworks'].split(','):
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
        conn.close()

        log_info(logger, f"[INFO] Geolocation database {CONST_GEOLOCATION_DB} created successfully.")

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
    conn = connect_to_db(CONST_GEOLOCATION_DB)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT network, start_ip, end_ip, netmask, country_name FROM geolocation")
            geolocation_data = cursor.fetchall()
            log_info(logger, f"[INFO] Loaded {len(geolocation_data)} geolocation entries into memory.")
        except sqlite3.Error as e:
            log_error(logger, f"[ERROR] Error loading geolocation data: {e}")
        finally:
            conn.close()
    return geolocation_data