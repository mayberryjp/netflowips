import sqlite3  # Import the sqlite3 module
from database import get_whitelist, connect_to_db, update_allflows, delete_all_records, create_database, get_config_settings, delete_database, init_configurations, import_whitelists  # Import from database.py
from detections import remove_whitelist, update_local_hosts, detect_geolocation_flows, detect_new_outbound_connections, router_flows_detection, local_flows_detection, foreign_flows_detection, detect_unauthorized_dns, detect_unauthorized_ntp, detect_incorrect_authoritative_dns, detect_incorrect_ntp_stratum , detect_dead_connections # Import from detections.py, 
from notifications import send_test_telegram_message  # Import send_test_telegram_message from notifications.py
from integrations.maxmind import create_geolocation_db, load_geolocation_data
from utils import log_info, log_warn, log_error  # Import log_info from utils
from const import CONST_LOCALHOSTS_DB, CONST_CREATE_LOCALHOSTS_SQL, CONST_GEOLOCATION_DB, CONST_REINITIALIZE_DB, IS_CONTAINER, CONST_NEWFLOWS_DB, CONST_ALLFLOWS_DB, CONST_ALERTS_DB, CONST_WHITELIST_DB, CONST_CONFIG_DB, CONST_CREATE_WHITELIST_SQL, CONST_CREATE_ALERTS_SQL, CONST_CREATE_ALLFLOWS_SQL, CONST_CREATE_NEWFLOWS_SQL, CONST_CREATE_CONFIG_SQL
import schedule
import time
import logging
import os

if (IS_CONTAINER):
    REINITIALIZE_DB=os.getenv("REINITIALIZE_DB", CONST_REINITIALIZE_DB)

# Function to process data
def process_data(geolocation_data):
    logger = logging.getLogger(__name__)

    log_info(logger,f"[INFO] Processing started.") 

    config_dict = get_config_settings()
    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        return

    """Read data from the database and process it."""
    conn = connect_to_db(CONST_NEWFLOWS_DB)
    if conn and config_dict['ScheduleProcessor'] == 1:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM flows")
            rows = cursor.fetchall()

            # delete newflows so collector can write clean to it again as quickly as possible
            log_info(logger, f"[INFO] Fetched {len(rows)} rows from the database.")
            if (config_dict['CleanNewFlows'] == 1):
                delete_all_records(CONST_NEWFLOWS_DB)

            # Pass the rows to update_all_flows
            update_allflows(rows, config_dict)
            
            # process whitelisted entries and remove from detection rows
            whitelist_entries = get_whitelist()
            log_info(logger, f"[INFO] Fetched {len(whitelist_entries)} whitelist entries from the database.")
            filtered_rows = remove_whitelist(rows, whitelist_entries)

            # Proper way to check config values with default of 0
            if config_dict.get("NewHostsDetection", 0) > 0:
                update_local_hosts(filtered_rows, config_dict)

            if config_dict.get("NewOutboundDetection", 0) > 0:
                detect_new_outbound_connections(filtered_rows, config_dict)

            if config_dict.get("RouterFlowsDetection", 0) > 0:
                router_flows_detection(filtered_rows, config_dict)

            if config_dict.get("ForeignFlowsDetection", 0) > 0:
                foreign_flows_detection(filtered_rows, config_dict)

            if config_dict.get("LocalFlowsDetection", 0) > 0:
                local_flows_detection(filtered_rows, config_dict)

            if config_dict.get("UnauthorizedDNSDetection", 0) > 0:
                detect_unauthorized_dns(filtered_rows, config_dict)
            
            if config_dict.get("UnauthorizedNTPDetection", 0) > 0:
                detect_unauthorized_ntp(filtered_rows, config_dict)

            if config_dict.get("IncorrectAuthoritativeDnsDetection", 0) > 0:
                detect_incorrect_authoritative_dns(filtered_rows, config_dict) 

            if config_dict.get("IncorrectNtpStratumDetection", 0) > 0:
                detect_incorrect_ntp_stratum(filtered_rows, config_dict)

            if config_dict.get("GeolocationFlowsDetection", 0) > 0:
                detect_geolocation_flows(filtered_rows, config_dict, geolocation_data)
            
            if config_dict.get("DeadConnectionDetection", 0) > 0:
                detect_dead_connections(config_dict)
        
            log_info(logger,f"[INFO] Processing finished.")   

        except sqlite3.Error as e:
            log_error(logger, f"[ERROR] Error reading from database: {e}")
        finally:
            conn.close()

if __name__ == "__main__":

    logger = logging.getLogger(__name__)

    STARTUP_DELAY = 30
    log_info(logger,f"[INFO] Processor process pausing {STARTUP_DELAY} seconds before starting up")
    # wait a bit for startup so collector can init configurations
    time.sleep(STARTUP_DELAY)

    log_info(logger, f"[INFO] Processor started.")

    send_test_telegram_message()

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
    #create_database(CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL)
    create_database(CONST_LOCALHOSTS_DB, CONST_CREATE_LOCALHOSTS_SQL)

    create_geolocation_db()
    geolocation_data = load_geolocation_data()

    while True:

        config_dict = get_config_settings()
        if not config_dict:
            log_error(logger, "[ERROR] Failed to load configuration settings")
            exit(1)
    
        PROCESS_RUN_INTERVAL = config_dict.get('ProcessRunInterval', 60)
        log_info(logger, f"[INFO] Process run interval set to {PROCESS_RUN_INTERVAL} seconds.")

        process_data(geolocation_data)
        time.sleep(PROCESS_RUN_INTERVAL)