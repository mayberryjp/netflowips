import sqlite3  # Import the sqlite3 module
from database import connect_to_db, update_allflows, delete_all_records, create_database, get_config_settings, delete_database, init_configurations  # Import from database.py
from detections import update_local_hosts, detect_new_outbound_connections, router_flows_detection, local_flows_detection, foreign_flows_detection  # Import update_local_hosts from detections.py
from notifications import send_test_telegram_message  # Import send_test_telegram_message from notifications.py
from utils import log_info  # Import log_info from utils
from const import CONST_PROCESSING_INTERVAL, IS_CONTAINER, CONST_NEWFLOWS_DB, CONST_ALLFLOWS_DB, CONST_ALERTS_DB, CONST_WHITELIST_DB, CONST_CONFIG_DB, CONST_CREATE_WHITELIST_SQL, CONST_CREATE_ALERTS_SQL, CONST_CREATE_ALLFLOWS_SQL, CONST_CREATE_NEWFLOWS_SQL, CONST_CREATE_CONFIG_SQL
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

            log_info(logger, f"[INFO] Fetched {len(rows)} rows from the database.")
            delete_all_records(CONST_NEWFLOWS_DB)

            # Pass the rows to update_all_flows
            update_allflows(rows, config_dict)

            # Proper way to check config values with default of 0
            if config_dict.get("NewHostsDetection", 0) > 0:
                update_local_hosts(rows, config_dict)

            if config_dict.get("NewOutboundDetection", 0) > 0:
                detect_new_outbound_connections(rows, config_dict)

            if config_dict.get("RouterFlowsDetection", 0) > 0:
                router_flows_detection(rows, config_dict)

            if config_dict.get("ForeignFlowsDetection", 0) > 0:
                foreign_flows_detection(rows, config_dict)

            if config_dict.get("LocalFlowsDetection", 0) > 0:
                local_flows_detection(rows, config_dict)

        except sqlite3.Error as e:
            log_info(logger, f"[ERROR] Error reading from database: {e}")
        finally:
            conn.close()

# Schedule the task to run every 60 seconds
schedule.every(PROCESSING_INTERVAL).seconds.do(process_data)

if __name__ == "__main__":
    log_info(logger, "[INFO] Processor started.")
    
    send_test_telegram_message()
    #delete databases to start clean - temporary
    #delete_database(CONST_ALERTS_DB)
    delete_database(CONST_CONFIG_DB)
    #delete_database(CONST_ALLFLOWS_DB)

    # Initialize all required databases
    create_database(CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL)
    create_database(CONST_ALLFLOWS_DB, CONST_CREATE_ALLFLOWS_SQL)
    create_database(CONST_ALERTS_DB, CONST_CREATE_ALERTS_SQL)
    create_database(CONST_WHITELIST_DB, CONST_CREATE_WHITELIST_SQL)
    create_database(CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL)

    # Initialize configurations
    init_configurations()
    process_data()

    while True:
        schedule.run_pending()
        time.sleep(1)