import sqlite3  # Import the sqlite3 module
from database import get_localhosts, get_whitelist, connect_to_db, update_allflows, delete_all_records, create_database, get_config_settings, delete_database, init_configurations, import_whitelists  # Import from database.py
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
from integrations.piholedhcp import get_pihole_dhcp_clients
from utils import get_usable_ips


def do_discovery():
    logger = logging.getLogger(__name__)

    config_dict= get_config_settings()

    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        return

    if config_dict.get("EnableLocalDiscoveryProcess", 0) < 1:
        log_info(logger, "[INFO] Discovery process is not enabled so stopping here.")
        return

    existing_localhosts = get_localhosts()
    
    DNS_SERVERS = config_dict['ApprovedLocalDnsServersList'].split(',')

    if DNS_SERVERS and config_dict.get('DiscoveryReverseDns', 0) > 0:
        lookup_results = dns_lookup(existing_localhosts, DNS_SERVERS, config_dict)
    else:
        log_error(logger, "[ERROR] No DNS servers in configuration to perform DNS lookup or DnsDiscoveryNotEnabled")

    if config_dict.get('DiscoveryPiholeDhcp', 0) > 0:
        dhcp_results = get_pihole_dhcp_clients(existing_localhosts, config_dict)


#    for ip, result in lookup_results.items():
#        print(f"{ip}: {result}")


if __name__ == "__main__":
    # wait a bit for startup so collector can init configurations
    time.sleep(5)
    logger = logging.getLogger(__name__)

    config_dict = get_config_settings()
    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        exit(1)

    log_info(logger, f"[INFO] Discovery process started.")

    DISCOVERY_RUN_INTERVAL = config_dict.get("DiscoveryProcessRunInterval", 86400)  # Default to 60 seconds if not set

    while True:
        do_discovery()
        time.sleep(DISCOVERY_RUN_INTERVAL)