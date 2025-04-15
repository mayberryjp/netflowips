import sqlite3  # Import the sqlite3 module
from database import connect_to_db, update_allflows, delete_all_records, delete_database, get_config_settings, init_alerts_db, init_whitelist_db, init_config_db # Import from database.py
from detections import update_local_hosts, detect_new_outbound_connections  # Import update_local_hosts from detections.py
#from maxmind import create_geolocation_db  # Import the function from maxmind.py
from utils import log_info  # Import log_info from utils
from const import CONST_PROCESSING_INTERVAL, IS_CONTAINER, CONST_NEWFLOWS_DB, CONST_ALERTS_DB, CONST_CONFIG_DB  # Import PROCESSING_INTERVAL from const
import schedule
import time
import logging
import os

# Initialize logger
logger = logging.getLogger(__name__)

if (IS_CONTAINER):
    PROCESSING_INTERVAL=os.getenv("PROCESSING_INTERVAL", CONST_PROCESSING_INTERVAL)

# Function to process data
def process_data():
    config_dict = get_config_settings()
    if not config_dict:
        log_info(logger, "[ERROR] Failed to load configuration settings")
        return

    """Read data from the database and process it."""
    conn = connect_to_db(CONST_NEWFLOWS_DB)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM flows")
            rows = cursor.fetchall()
            delete_all_records(CONST_NEWFLOWS_DB)
            log_info(logger, f"[INFO] Fetched {len(rows)} rows from the database.")

            # Proper way to check config values with default of 0
            if config_dict.get("NewHostsDetection", 0) > 0:
                update_local_hosts(rows, config_dict)

            if config_dict.get("NewOutboundDetection", 0) > 0:
                detect_new_outbound_connections(rows, config_dict)

            # Pass the rows to update_all_flows
            update_allflows(rows, config_dict)

        except sqlite3.Error as e:
            log_info(logger, f"[ERROR] Error reading from database: {e}")
        finally:
            conn.close()

# Schedule the task to run every 60 seconds
schedule.every(PROCESSING_INTERVAL).seconds.do(process_data)

if __name__ == "__main__":
    log_info(logger, "[INFO] Processor started.")
    delete_database(CONST_ALERTS_DB)
    delete_database(CONST_CONFIG_DB)
    init_config_db()
    init_alerts_db()
    init_whitelist_db()
    while True:
        schedule.run_pending()
        time.sleep(1)