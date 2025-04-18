import sqlite3
import csv
import os
import socket
import struct
from ipaddress import IPv4Network
from utils import log_info, log_warn, log_error  # Assuming log_info is already defined
from database import connect_to_db  # Assuming connect_to_db is already defined
import logging
from const import CONST_LOCAL_NETWORKS, CONST_SITE, IS_CONTAINER


if IS_CONTAINER:
    LOCAL_NETWORKS = os.getenv("LOCAL_NETWORKS", CONST_LOCAL_NETWORKS)
    LOCAL_NETWORKS = [LOCAL_NETWORKS] if ',' not in LOCAL_NETWORKS else LOCAL_NETWORKS.split(',')
    SITE = os.getenv("SITE", CONST_SITE)

def ip_network_to_range(network):
    """
    Convert a CIDR network to start and end IP addresses as integers using inet_aton.
    
    Args:
        network (str): Network in CIDR notation (e.g., '192.168.1.0/24')
    
    Returns:
        tuple: (start_ip, end_ip, netmask) as integers
    """
    try:
        net = IPv4Network(network)
        # Convert IP addresses to integers using inet_aton and struct.unpack
        start_ip = struct.unpack('!L', socket.inet_aton(str(net.network_address)))[0]
        end_ip = struct.unpack('!L', socket.inet_aton(str(net.broadcast_address)))[0]
        netmask = struct.unpack('!L', socket.inet_aton(str(net.netmask)))[0]
        
        return start_ip, end_ip, netmask
    except Exception as e:
        log_warn(None, f"[WARN] Invalid network format {network}: {e}")
        return None, None, None

def create_geolocation_db(
    blocks_csv_path="geolite/GeoLite2-Country-Blocks-IPv4.csv",
    locations_csv_path="geolite/GeoLite2-Country-Locations-en.csv",
    db_name="/database/geolocation.db"
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

        # Step 3: Create the SQLite database
        log_info(logger, f"[INFO] Creating SQLite database: {db_name}...")
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Create the table with new columns
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geolocation (
                network TEXT PRIMARY KEY,
                start_ip INTEGER,
                end_ip INTEGER,
                netmask INTEGER,
                geoname_id INTEGER,
                country_name TEXT,
                registered_country_geoname_id INTEGER,
                represented_country_geoname_id INTEGER,
                is_anonymous_proxy INTEGER,
                is_satellite_provider INTEGER
            )
        """)

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
                        network, start_ip, end_ip, netmask, geoname_id, country_name,
                        registered_country_geoname_id, represented_country_geoname_id,
                        is_anonymous_proxy, is_satellite_provider
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    network,
                    start_ip,
                    end_ip,
                    netmask,
                    geoname_id,
                    country_name,
                    row.get("registered_country_geoname_id"),
                    row.get("represented_country_geoname_id"),
                    row.get("is_anonymous_proxy"),
                    row.get("is_satellite_provider")
                ))

        # After processing CSV files, add LOCAL_NETWORKS
        log_info(logger, f"[INFO] Adding LOCAL_NETWORKS to geolocation database...")
        for network in LOCAL_NETWORKS:
            start_ip, end_ip, netmask = ip_network_to_range(network)
            if start_ip is None:
                continue
                
            cursor.execute("""
                INSERT OR REPLACE INTO geolocation (
                    network, start_ip, end_ip, netmask,
                    country_name, is_anonymous_proxy, is_satellite_provider
                ) VALUES (?, ?, ?, ?, ?, 0, 0)
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

        log_info(logger, f"[INFO] Geolocation database {db_name} created successfully.")

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
    conn = connect_to_db("/database/geolocation.db")
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT network, country_name FROM geolocation")
            geolocation_data = cursor.fetchall()
            log_info(logger, f"[INFO] Loaded {len(geolocation_data)} geolocation entries into memory.")
        except sqlite3.Error as e:
            log_error(logger, f"[ERROR] Error loading geolocation data: {e}")
        finally:
            conn.close()
    return geolocation_data