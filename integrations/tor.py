from utils import log_info, log_error
import logging
from database import connect_to_db, delete_all_records, create_database
from const import CONST_GEOLOCATION_DB, CONST_CREATE_TORNODES_SQL
from datetime import datetime, timedelta
import requests

def update_tor_nodes(config_dict):
    """
    Download and update Tor node list from dan.me.uk.
    Deletes all existing entries in the tornodes table before updating.
    """
    logger = logging.getLogger(__name__)
    log_info(logger, "[INFO] Starting tor node processing")

    create_database(CONST_GEOLOCATION_DB, CONST_CREATE_TORNODES_SQL)    
    conn = connect_to_db(CONST_GEOLOCATION_DB)

    tor_nodes_url = config_dict.get('TorNodesUrl','https://www.dan.me.uk/torlist/?full')
    
    try:
        cursor = conn.cursor()

        # Use delete_all_records to clear the tornodes table
        delete_all_records(CONST_GEOLOCATION_DB, "tornodes")

        log_info(logger,"[INFO] About to request tor node list from dan.me.uk")
        # Download new list with timeout
        response = requests.get(
            tor_nodes_url, 
            headers={'User-Agent': 'HomelabIDS TorNode Checker (homelabids.com)'},
            timeout=30  # 30 second timeout
        )
        if response.status_code != 200:
            log_error(logger, f"[ERROR] Failed to download Tor node list: {response.status_code}")
            return
        log_info(logger, "[INFO] Successfully downloaded Tor node list")
        # Parse IPs (one per line)
        tor_nodes = set(ip.strip() for ip in response.text.split('\n') if ip.strip())
        
        # Update database with new Tor nodes
        cursor.executemany("""
            INSERT INTO tornodes (ip_address, import_date) 
            VALUES (?, CURRENT_TIMESTAMP)
        """, [(ip,) for ip in tor_nodes])
        
        conn.commit()
        log_info(logger, f"[INFO] Updated Tor node list with {len(tor_nodes)} nodes")
        
    except Exception as e:
        log_error(logger, f"[ERROR] Error updating Tor nodes: {e}")
    finally:
        if conn:
            conn.close()

    log_info(logger, "[INFO] Finished tor node processing")