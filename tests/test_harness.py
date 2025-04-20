import sqlite3
import logging
from datetime import datetime
import os
from utils import log_info
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from const import (
    CONST_NEWFLOWS_DB, 
    CONST_TEST_SOURCE_DB,
    CONST_ALLFLOWS_DB,
    CONST_ALERTS_DB,
    CONST_WHITELIST_DB
)
from utils import log_info
from maxmind import ( load_geolocation_data, create_geolocation_db )
from database import (
    get_config_settings,
    get_whitelist_entries,
    connect_to_db,
    update_allflows,
    delete_database
)
from detections import (
    update_LOCAL_NETWORKS,
    detect_new_outbound_connections,
    router_flows_detection,
    foreign_flows_detection,
    local_flows_detection,
    detect_geolocation_flows,
    remove_whitelist
)

def copy_flows_to_newflows():
    """
    Copy all flows from source databases defined in CONST_TEST_SOURCE_DB to newflows.db
    """
    logger = logging.getLogger(__name__)

    for source_db in CONST_TEST_SOURCE_DB:
        try:
            if not os.path.exists(source_db):
                log_info(logger, f"[WARN] Database not found: {source_db}")
                continue

            # Connect to source database
            source_conn = sqlite3.connect(source_db)
            source_cursor = source_conn.cursor()
            
            # Connect to newflows database
            newflows_conn = sqlite3.connect(CONST_NEWFLOWS_DB)
            newflows_cursor = newflows_conn.cursor()
            
            # Get all flows from source
            source_cursor.execute("SELECT * FROM flows")
            rows = source_cursor.fetchall()
            
            # Insert flows into newflows
            for row in rows:
                newflows_cursor.execute("""
                    INSERT INTO flows (
                        src_ip, dst_ip, src_port, dst_port, protocol,
                        packets, bytes, flow_start, flow_end, last_seen, times_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, row)
                
            newflows_conn.commit()
            log_info(logger, f"[INFO] Copied {len(rows)} flows from {source_db}")
            
        except sqlite3.Error as e:
            log_info(logger, f"[ERROR] Database error processing {source_db}: {e}")
        finally:
            if 'source_conn' in locals():
                source_conn.close()
            if 'newflows_conn' in locals():
                newflows_conn.close()

def main():
    """Main function to copy flows from multiple databases"""
    start_time = datetime.now()
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    delete_database(CONST_ALLFLOWS_DB)
    delete_database(CONST_ALERTS_DB)
    delete_database(CONST_WHITELIST_DB)

    
    config_dict = get_config_settings()
    
    copy_flows_to_newflows()

    conn = connect_to_db(CONST_NEWFLOWS_DB)

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flows")
    rows = cursor.fetchall()

    update_allflows(rows, config_dict)

    whitelist_entries = get_whitelist_entries()
    log_info(logger, f"[INFO] Fetched {len(whitelist_entries)} whitelist entries from the database.")
    filtered_rows = remove_whitelist(rows, whitelist_entries)

    update_LOCAL_NETWORKS(filtered_rows, config_dict)
    detect_new_outbound_connections(filtered_rows, config_dict)
    router_flows_detection(filtered_rows, config_dict)
    foreign_flows_detection(filtered_rows, config_dict)
    local_flows_detection(filtered_rows, config_dict)

    banned_countries = config_dict.get("BannedCountryList", "").strip()

    create_geolocation_db()
    geolocation_data = load_geolocation_data()

    detect_geolocation_flows(filtered_rows, config_dict, geolocation_data)

    log_info(logger,f"[INFO] Processing finished.")   
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    log_info(logger, f"[INFO] Total execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    main()