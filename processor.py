import sqlite3  # Import the sqlite3 module
from database import get_whitelist_entries, connect_to_db, update_allflows, delete_all_records, create_database, get_config_settings, delete_database, init_configurations  # Import from database.py
from detections import remove_whitelist, update_LOCAL_NETWORKS, detect_geolocation_flows, detect_new_outbound_connections, router_flows_detection, local_flows_detection, foreign_flows_detection  # Import update_LOCAL_NETWORKS from detections.py
from notifications import send_test_telegram_message  # Import send_test_telegram_message from notifications.py
from integrations.maxmind import create_geolocation_db, load_geolocation_data
from utils import log_info, log_warn, log_error  # Import log_info from utils
from const import CONST_GEOLOCATION_DB, CONST_SCHEDULE_PROCESSOR, CONST_CLEAN_NEWFLOWS,CONST_REINITIALIZE_DB,CONST_PROCESSING_INTERVAL, IS_CONTAINER, CONST_NEWFLOWS_DB, CONST_ALLFLOWS_DB, CONST_ALERTS_DB, CONST_WHITELIST_DB, CONST_CONFIG_DB, CONST_CREATE_WHITELIST_SQL, CONST_CREATE_ALERTS_SQL, CONST_CREATE_ALLFLOWS_SQL, CONST_CREATE_NEWFLOWS_SQL, CONST_CREATE_CONFIG_SQL
import schedule
import time
import logging
import os

# Initialize logger


if (IS_CONTAINER):
    PROCESSING_INTERVAL=os.getenv("PROCESSING_INTERVAL", CONST_PROCESSING_INTERVAL)
    REINITIALIZE_DB=os.getenv("REINITIALIZE_DB", CONST_REINITIALIZE_DB)
    CLEAN_NEWFLOWS=os.getenv("CLEAN_NEWFLOWS", CONST_CLEAN_NEWFLOWS)
    SCHEDULE_PROCESSOR=os.getenv("SCHEDULE_PROCESSOR", CONST_SCHEDULE_PROCESSOR)

# Function to process data
def process_data(geolocation_data):
    logger = logging.getLogger(__name__)
    config_dict = get_config_settings()
    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        return

    """Read data from the database and process it."""
    conn = connect_to_db(CONST_NEWFLOWS_DB)
    if conn and SCHEDULE_PROCESSOR:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM flows")
            rows = cursor.fetchall()

            # delete newflows so collector can write clean to it again as quickly as possible
            log_info(logger, f"[INFO] Fetched {len(rows)} rows from the database.")
            if (CLEAN_NEWFLOWS):
                delete_all_records(CONST_NEWFLOWS_DB)

            # Pass the rows to update_all_flows
            update_allflows(rows, config_dict)

            # process whitelisted entries and remove from detection rows
            whitelist_entries = get_whitelist_entries()
            log_info(logger, f"[INFO] Fetched {len(whitelist_entries)} whitelist entries from the database.")
            filtered_rows = remove_whitelist(rows, whitelist_entries)

            # Proper way to check config values with default of 0
            if config_dict.get("NewHostsDetection", 0) > 0:
                update_LOCAL_NETWORKS(filtered_rows, config_dict)

            if config_dict.get("NewOutboundDetection", 0) > 0:
                detect_new_outbound_connections(filtered_rows, config_dict)

            if config_dict.get("RouterFlowsDetection", 0) > 0:
                router_flows_detection(filtered_rows, config_dict)

            if config_dict.get("ForeignFlowsDetection", 0) > 0:
                foreign_flows_detection(filtered_rows, config_dict)

            if config_dict.get("LocalFlowsDetection", 0) > 0:
                local_flows_detection(filtered_rows, config_dict)

            banned_countries = config_dict.get("BannedCountryList", "").strip()

            if config_dict.get("GeolocationFlowsDetection", 0) > 0 and banned_countries:
                # Call the geolocation detection function here
                detect_geolocation_flows(filtered_rows, config_dict, geolocation_data)
        
            log_info(logger,f"[INFO] Processing finished.")   

        except sqlite3.Error as e:
            log_error(logger, f"[ERROR] Error reading from database: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    logger = logging.getLogger(__name__)

    log_info(logger, f"[INFO] Processor started.")

    send_test_telegram_message()
    delete_database(CONST_CONFIG_DB)

    if (REINITIALIZE_DB):
        delete_database(CONST_ALLFLOWS_DB)
        delete_database(CONST_ALERTS_DB)
        delete_database(CONST_WHITELIST_DB)
        delete_database(CONST_CONFIG_DB)
        delete_database(CONST_GEOLOCATION_DB)

    # Initialize all required databases
    create_database(CONST_ALLFLOWS_DB, CONST_CREATE_ALLFLOWS_SQL)
    create_database(CONST_ALERTS_DB, CONST_CREATE_ALERTS_SQL)
    create_database(CONST_WHITELIST_DB, CONST_CREATE_WHITELIST_SQL)
    create_database(CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL)

    # Initialize configurations
    init_configurations()

    create_geolocation_db()
    geolocation_data = load_geolocation_data()

    while True:
        process_data(geolocation_data)
        time.sleep(60)