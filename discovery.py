import sqlite3  # Import the sqlite3 module
from database import update_localhosts, get_localhosts, get_whitelist, connect_to_db, update_allflows, delete_all_records, create_database, get_config_settings, delete_database, init_configurations, import_whitelists  # Import from database.py
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
from integrations.nmap_fingerprint import os_fingerprint
from utils import get_usable_ips


def do_discovery():
    logger = logging.getLogger(__name__)

    config_dict = get_config_settings()

    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        return

    if config_dict.get("EnableLocalDiscoveryProcess", 0) < 1:
        log_info(logger, "[INFO] Discovery process is not enabled so stopping here.")
        return

    existing_localhosts = get_localhosts()
    
    DNS_SERVERS = config_dict['ApprovedLocalDnsServersList'].split(',')

    if DNS_SERVERS and config_dict.get('DiscoveryReverseDns', 0) > 0:
        dns_results = dns_lookup(existing_localhosts, DNS_SERVERS, config_dict)
    else:
        log_error(logger, "[ERROR] No DNS servers in configuration to perform DNS lookup or DnsDiscoveryNotEnabled")

    if config_dict.get('DiscoveryPiholeDhcp', 0) > 0:
        dhcp_results = get_pihole_dhcp_clients(existing_localhosts, config_dict)

    if config_dict.get('DiscoveryNmapOsFingerprint', 0) > 0:
        nmap_results = os_fingerprint(existing_localhosts, config_dict)

    combined_results = {}

    # Process DNS results
    for result in dns_results:
        ip = result["ip"]
        combined_results[ip] = {
            "dns_hostname": result.get("dns_hostname", None),
            "mac_address": None,
            "mac_vendor": None,
            "last_seen": None,
            "first_seen": None,
            "original_flow": None,
            "dhcp_hostname": None,
            "os_fingerprint": None,
        }

    # Process DHCP results
    for result in dhcp_results:
        ip = result["ip"]
        if ip not in combined_results:
            combined_results[ip] = {}
        combined_results[ip].update({
            "dhcp_hostname": result.get("dhcp_hostname", combined_results[ip].get("dhcp_hostname")),
            "mac_address": result.get("mac_address", combined_results[ip].get("mac_address")),
            "mac_vendor": result.get("mac_vendor", combined_results[ip].get("mac_vendor")),
            "last_seen": result.get("last_seen", combined_results[ip].get("last_seen")),
        })

    # Process Nmap results
    for result in nmap_results:
        ip = result["ip"]
        if ip not in combined_results:
            combined_results[ip] = {}
        combined_results[ip].update({
            "os_fingerprint": result.get("os_fingerprint", combined_results[ip].get("os_fingerprint")),
        })

    # Update the localhosts database
    for ip, data in combined_results.items():
        update_localhosts(
            ip_address=ip,
            first_seen=data.get("first_seen"),
            original_flow=data.get("original_flow"),
            mac_address=data.get("mac_address"),
            mac_vendor=data.get("mac_vendor"),
            dhcp_hostname=data.get("dhcp_hostname"),
            dns_hostname=data.get("dns_hostname"),
            os_fingerprint=data.get("os_fingerprint"),
        )

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