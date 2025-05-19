
import sys
import os
from pathlib import Path
current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
src_dir = f"{parent_dir}/src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
import logging
import requests
import zipfile
from src.const import CONST_CONSOLIDATED_DB
import json
import sqlite3
from init import *


def create_asn_database():
    """
    Downloads ASN (Autonomous System Number) data from oxl.app,
    extracts IP ranges and ISP information, and stores it in a database.
    
    This enables IP to ISP lookups to identify the provider of an IP address.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Step 1: Create temporary directory if it doesn't exist
        temp_dir = "/database"
        os.makedirs(temp_dir, exist_ok=True)
        zip_path = os.path.join(temp_dir, "asn_ipv4_full.json.zip")
        json_path = os.path.join(temp_dir, "asn_ipv4_full.json")
        
        # Step 2: Download the ASN data file
        log_info(logger, "[INFO] Downloading ASN database from oxl.app...")
        response = requests.get("https://geoip.oxl.app/file/asn_ipv4_full.json.zip", stream=True)
        
        if response.status_code != 200:
            log_error(logger, f"[ERROR] Failed to download ASN database: {response.status_code}")
            return
            
        with open(zip_path, "wb") as f:
            f.write(response.content)
        
        # Step 3: Extract the ZIP file
        log_info(logger, "[INFO] Extracting ASN database ZIP file...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Step 4: Ensure we have the extracted JSON file
        if not os.path.exists(json_path):
            log_error(logger, "[ERROR] ASN JSON file not found after extraction")
            return
        
        # Step 5: Connect to database and prepare table
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "asn")
        if conn is None:
            log_error(logger, f"[ERROR] Failed to connect to the database {CONST_CONSOLIDATED_DB}")
            return
            
        cursor = conn.cursor()
        
        # Create ASN table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asn (
                network TEXT PRIMARY KEY,
                start_ip INTEGER,
                end_ip INTEGER,
                netmask INTEGER,
                asn TEXT,
                isp_name TEXT
            )
        """)
        
        # Step 6: Parse the JSON and insert data into database
        log_info(logger, "[INFO] Processing ASN data and inserting into database...")
        
        # For large files, we'll read and parse line by line
        count = 0
        with open(json_path, 'r') as json_file:
            data = json.load(json_file)
            total_entries = len(data)
            log_info(logger, f"[INFO] Found {total_entries} ASN entries to process")
            
            # Process in batches for better performance
            batch_size = 1000
            current_batch = []
            
            for entry in data:
                network = entry.get("network")
                asn = entry.get("autonomous_system_number")
                isp_name = entry.get("autonomous_system_organization")
                
                if not network or not asn or not isp_name:
                    continue
                    
                # Convert network CIDR to start_ip, end_ip, netmask
                start_ip, end_ip, netmask = ip_network_to_range(network)
                if start_ip is None:
                    continue
                
                # Add to current batch
                current_batch.append((
                    network,
                    start_ip,
                    end_ip,
                    netmask,
                    str(asn),
                    isp_name
                ))
                
                # Insert batch when it reaches the batch size
                if len(current_batch) >= batch_size:
                    cursor.executemany("""
                        INSERT OR REPLACE INTO asn 
                        (network, start_ip, end_ip, netmask, asn, isp_name) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, current_batch)
                    conn.commit()
                    count += len(current_batch)
                    current_batch = []
                    log_info(logger, f"[INFO] Processed {count}/{total_entries} ASN entries")
            
            # Insert any remaining entries
            if current_batch:
                cursor.executemany("""
                    INSERT OR REPLACE INTO asn 
                    (network, start_ip, end_ip, netmask, asn, isp_name) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, current_batch)
                conn.commit()
                count += len(current_batch)
        
        # Step 7: Create indexes for faster lookups
        log_info(logger, "[INFO] Creating indexes on ASN database...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_asn_ip_range ON asn (start_ip, end_ip)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_asn_name ON asn (isp_name)")
        
        # Commit changes and clean up
        conn.commit()
        disconnect_from_db(conn)
        
        log_info(logger, f"[INFO] ASN database created successfully with {count} entries")
        
        # Step 8: Clean up temporary files
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(json_path):
            os.remove(json_path)
            
    except Exception as e:
        log_error(logger, f"[ERROR] Error creating ASN database: {e}")
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def lookup_ip_isp(ip_address):
    """
    Look up the ISP information for a given IP address.
    
    Args:
        ip_address (str): The IP address to look up
        
    Returns:
        dict: A dictionary containing ASN and ISP name, or None if not found
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Convert IP address to integer
        ip_int = ip_to_int(ip_address)
        
        if ip_int is None:
            log_error(logger, f"[ERROR] Invalid IP address format: {ip_address}")
            return None
        
        # Query the database for the ISP
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "asn")
        if not conn:
            log_error(logger, f"[ERROR] Failed to connect to the ASN database")
            return None
            
        try:
            cursor = conn.cursor()
            # Find the range that contains this IP
            cursor.execute("""
                SELECT asn, isp_name, network
                FROM asn 
                WHERE ? BETWEEN start_ip AND end_ip 
                LIMIT 1
            """, (ip_int,))
            
            result = cursor.fetchone()
            if result:
                return {
                    "asn": result[0],
                    "isp_name": result[1],
                    "network": result[2]
                }
            else:
                log_info(logger, f"[INFO] No ISP found for IP address: {ip_address}")
                return None
                
        except sqlite3.Error as e:
            log_error(logger, f"[ERROR] Database error looking up ISP for IP {ip_address}: {e}")
            return None
        finally:
            disconnect_from_db(conn)
            
    except Exception as e:
        log_error(logger, f"[ERROR] Error looking up ISP for IP {ip_address}: {e}")
        return None