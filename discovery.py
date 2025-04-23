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
from integrations.dns import dns_lookup  # Import the dns_lookup function from dns.py
from utils import get_usable_ips


def do_discovery():
    logger = logging.getLogger(__name__)

    config_dict= get_config_settings()

    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        return
    
    localhosts_conn = connect_to_db(CONST_LOCALHOSTS_DB)

    if not localhosts_conn:
        log_error(logger, "[ERROR] Unable to connect to localhosts database")
        return

    try:
        localhosts_cursor = localhosts_conn.cursor()

        # Load all existing local hosts into memory
        localhosts_cursor.execute("SELECT ip_address FROM localhosts")
        existing_localhosts = set(row[0] for row in localhosts_cursor.fetchall())
        log_info(logger, f"[INFO] Loaded {len(existing_localhosts)} existing local hosts into memory")

    except Exception as e:
        log_error(logger, f"[ERROR] Error in do_discovery: {e}")
    finally:
        localhosts_conn.close()
    
    DNS_SERVERS = config_dict['ApprovedLocalDnsServersList'].split(',')
    if not DNS_SERVERS:
        log_error(logger, "[ERROR] No DNS servers in configuration to perform DNS lookup")
        return
    
    lookup_results = dns_lookup(existing_localhosts,DNS_SERVERS, config_dict)

#    for ip, result in lookup_results.items():
#        print(f"{ip}: {result}")


if __name__ == "__main__":
    # wait a bit for startup so collector can init configurations
    time.sleep(5)

    logger = logging.getLogger(__name__)
    log_info(logger, f"[INFO] Discovery process started.")

    while True:
        do_discovery()
        time.sleep(60)