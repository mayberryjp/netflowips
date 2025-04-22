import sqlite3
import json
from datetime import datetime
from utils import log_info, is_ip_in_range, log_warn, log_error, ip_to_int  # Assuming log_info and is_ip_in_range are defined in utils
from const import CONST_LOCALHOSTS_DB, CONST_ALERTS_DB # Assuming constants are defined in const
from database import connect_to_db, log_alert_to_db  # Import connect_to_db from database.py
from notifications import send_telegram_message  # Import notification functions
import os
import ipaddress
import logging
import socket
import struct
import time


def update_local_hosts(rows, config_dict):
    """
    Check for new IPs in the provided rows and add them to localhosts.db if necessary.
    Uses an in-memory list to avoid repeated database queries.
    """
    logger = logging.getLogger(__name__)

    # Connect to the localhosts database
    localhosts_conn = connect_to_db(CONST_LOCALHOSTS_DB)
    LOCAL_NETWORKS=set(config_dict['LocalNetworks'].split(','))
    if not localhosts_conn:
        log_error(logger, "[ERROR] Unable to connect to localhosts database")
        return

    try:
        localhosts_cursor = localhosts_conn.cursor()

        # Load all existing local hosts into memory
        localhosts_cursor.execute("SELECT ip_address FROM localhosts")
        existing_localhosts = set(row[0] for row in localhosts_cursor.fetchall())
        log_info(logger, f"[INFO] Loaded {len(existing_localhosts)} existing local hosts into memory")

        for row in rows:
            for range_index in (0, 1):  # Assuming the IP addresses are in the first two columns
                ip_address = row[range_index]

                # Check if the IP is within any of the allowed network ranges
                is_local = is_ip_in_range(ip_address, LOCAL_NETWORKS)

                if is_local and ip_address not in existing_localhosts:
                    # Add the new IP to localhosts.db
                    first_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    original_flow = json.dumps(row)  # Encode the original flow as JSON
                    localhosts_cursor.execute(
                        "INSERT INTO localhosts (ip_address, first_seen, original_flow) VALUES (?, ?, ?)",
                        (ip_address, first_seen, original_flow)
                    )
                    existing_localhosts.add(ip_address)  # Add to in-memory set
                    log_info(logger, f"[INFO] Added new IP to localhosts.db: {ip_address}")

                    # Handle alerts and notifications based on NewHostsDetection config
                    if config_dict.get("NewHostsDetection") == 2:
                        # Send a Telegram message and log the alert
                        message = f"New Host Detected: {ip_address}"
                        send_telegram_message(message, original_flow[0:5])
                        log_alert_to_db(ip_address, row, "New Host Detected", "", "",
                                        f"{ip_address}_NewHostsDetection", False)
                    elif config_dict.get("NewHostsDetection") == 1:
                        # Only log the alert
                        log_alert_to_db(ip_address, row, "New Host Detected", "", "",
                                        f"{ip_address}_NewHostsDetection", False)

        # Commit changes to localhosts.db
        localhosts_conn.commit()

    except Exception as e:
        log_error(logger, f"[ERROR] Error in update_local_hosts: {e}")
    finally:
        localhosts_conn.close()


def detect_new_outbound_connections(rows, config_dict):
    """
    Detect new outbound connections from local clients to external servers.
    A server is identified by having a lower port number than the client.
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    alerts_conn = connect_to_db(CONST_ALERTS_DB)

    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    if not alerts_conn:
        log_error(logger, "[ERROR] Unable to connect to alerts database")
        return

    try:
        alerts_cursor = alerts_conn.cursor()

        for row in rows:
            src_ip, dst_ip, src_port, dst_port, protocol = row[0:5]
            
            # Check if source IP is in any of the local networks
            is_src_local = False

            if is_ip_in_range(src_ip, LOCAL_NETWORKS):
                is_src_local = True
            
            # If source is local and destination port is lower (indicating server),
            # this might be a new outbound connection
            if is_src_local and dst_port < src_port:
                # Create a unique identifier for this connection
                alert_id = f"{src_ip}_{dst_ip}_{protocol}_{dst_port}_NewOutboundDetection"
                
                # Check if this connection has been alerted before
                alerts_cursor.execute("""
                    SELECT COUNT(*) FROM alerts 
                    WHERE id = ?
                """, (alert_id,))
                
                exists = alerts_cursor.fetchone()[0] > 0
                
                if not exists:
                    message = (f"New outbound connection detected:\n"
                             f"Local client: {src_ip}\n"
                             f"Remote server: {dst_ip}:{dst_port}\n"
                             f"Protocol: {protocol}")
                    
                    log_info(logger, f"[INFO] New outbound connection detected: {src_ip} -> {dst_ip}:{dst_port}")
                    
                    # Log alert based on configuration level
                    if config_dict.get("NewOutboundDetection") == 2:
                        # Send Telegram alert and log to database
                        send_telegram_message(message, row)
                        log_alert_to_db(src_ip, row, "New outbound connection detected", dst_ip, dst_port, 
                                      alert_id, False)
                    elif config_dict.get("NewOutboundDetection") == 1:
                        # Only log to database
                        log_alert_to_db(src_ip, row, "New outbound connection detected", dst_ip, dst_port, 
                                      alert_id, False)

    except Exception as e:
        log_error(logger, f"[ERROR] Error in detect_new_outbound_connections: {e}")
    finally:
        alerts_conn.close()


def router_flows_detection(rows, config_dict):
    """
    Detect and handle flows involving a router IP address.
    Uses exact IP matching instead of network matching.
    """
    logger = logging.getLogger(__name__)

    ROUTER_LIST = set(config_dict['RouterIpAddresses'].split(','))
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, *_ = row

        # Determine if the flow involves a router IP address using exact matching
        router_ip_seen = None
        router_port = None
        for router_ip in ROUTER_LIST:
            if src_ip == router_ip:
                router_ip_seen = src_ip
                router_port = src_port
            elif dst_ip == router_ip:
                router_ip_seen = dst_ip
                router_port = dst_port

        if router_ip_seen:
            original_flow = json.dumps(row)
            log_info(logger, f"[INFO] Flow involves a router IP address: {router_ip_seen}")

            if config_dict.get("RouterFlowsDetection") == 2:
                message = f"Flow involves a router IP address: {router_ip_seen}"
                send_telegram_message(message, original_flow[0:5])
                log_alert_to_db(
                    router_ip_seen, 
                    row, 
                    "Flow involves a router IP address",
                    src_port,
                    dst_port,
                    f"{router_ip_seen}_{src_ip}_{dst_ip}_{protocol}_{router_port}_RouterFlowsDetection", 
                    False
                )
            elif config_dict.get("RouterFlowsDetection") == 1:
                log_alert_to_db(
                    router_ip_seen, 
                    row, 
                    "Flow involves a router IP address",
                    src_port,
                    dst_port,
                    f"{router_ip_seen}_{src_ip}_{dst_ip}_{protocol}_{router_port}_RouterFlowsDetection", 
                    False
                )


def local_flows_detection(rows, config_dict):
    """
    Detect and handle flows where both src_ip and dst_ip are in LOCAL_NETWORKS,
    excluding any flows involving ROUTER_IPADDRESS.
    """

    ROUTER_LIST = set(config_dict['RouterIpAddresses'].split(','))
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))

    logger = logging.getLogger(__name__)
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, *_ = row

        # Skip if either IP is in ROUTER_IPADDRESS array
        is_router_ip = False
        for router_ip in ROUTER_LIST:
            if src_ip == router_ip or dst_ip == router_ip:
                is_router_ip = True

        if is_router_ip:
            continue

        # Determine if both IPs are in LOCAL_NETWORKS
        is_src_local = False
        is_dst_local = False
        if is_ip_in_range(src_ip, LOCAL_NETWORKS):
            is_src_local = True
        if is_ip_in_range(dst_ip, LOCAL_NETWORKS):
            is_dst_local = True

        if is_src_local and is_dst_local:
            log_info(logger, f"[INFO] Flow involves two local hosts: {src_ip} and {dst_ip}")

            if config_dict.get("LocalFlowsDetection") == 2:
                message = f"Flow involves two local hosts: {src_ip} and {dst_ip}"
                send_telegram_message(message, row)
                log_alert_to_db(
                    src_ip, 
                    row, 
                    "Flow involves two local hosts",
                    dst_ip,
                    dst_port,
                    f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_LocalFlowsDetection", 
                    False
                )
            elif config_dict.get("LocalFlowsDetection") == 1:
                log_alert_to_db(
                    src_ip, 
                    row, 
                    "Flow involves two local hosts",
                    dst_ip,
                    dst_port,
                    f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_LocalFlowsDetection", 
                    False
                )


def foreign_flows_detection(rows, config_dict):
    """
    Detect and handle flows where neither src_ip nor dst_ip is in LOCAL_NETWORKS.
    """
    logger = logging.getLogger(__name__)
    LOCAL_NETWORKS=set(config_dict['LocalNetworks'].split(','))

    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, *_ = row

        # Determine if neither src_ip nor dst_ip is in LOCAL_NETWORKS
        is_src_local = False
        is_dst_local = False
        

        if is_ip_in_range(src_ip, LOCAL_NETWORKS):
            is_src_local = True
        if is_ip_in_range(dst_ip, LOCAL_NETWORKS):
            is_dst_local = True


        if not is_src_local and not is_dst_local:
            log_info(logger, f"[INFO] Flow involves two foreign hosts: {src_ip} and {dst_ip}")

            if config_dict.get("ForeignFlowsDetection") == 2:
                message = f"Flow involves two foreign hosts: {src_ip} and {dst_ip}"
                send_telegram_message(message, row)
                log_alert_to_db(
                    src_ip, 
                    row, 
                    "Flow involves two foreign hosts",
                    dst_ip, 
                    dst_port,
                    f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_ForeignFlowsDetection", 
                    False
                )
            elif config_dict.get("ForeignFlowsDetection") == 1:
                log_alert_to_db(
                    src_ip, 
                    row, 
                    "Flow involves two foreign hosts",
                    dst_ip, 
                    dst_port,
                    f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_ForeignFlowsDetection", 
                    False
                )


def detect_geolocation_flows(rows, config_dict, geolocation_data):
    """
    Optimized version of geolocation flow detection.
    Uses set lookups and precomputed data structures for better performance.
    """
    logger = logging.getLogger(__name__)
    
    # Debug: Print sample of geolocation data
    #log_info(logger, f"[DEBUG] First few geolocation entries: {geolocation_data[:2]}")
    
    # Convert banned countries to a set for O(1) lookups
    banned_countries = set(
        country.strip() 
        for country in config_dict.get("BannedCountryList", "").split(",") 
        if country.strip()
    )

    if not banned_countries:
        log_warn(logger, "[WARN] No banned countries specified in BannedCountryList.")
        return

    # Debug: Print banned countries
    #log_info(logger, f"[DEBUG] Banned countries: {banned_countries}")

    # Pre-process geolocation data into ranges
    geo_ranges = []
    for entry in geolocation_data:
        if len(entry) >= 5:  # Changed condition to >= 4
            network, start_ip, end_ip, netmask, country = entry[:5]  # Take first 4 elements
            if country in banned_countries:
                geo_ranges.append((start_ip, end_ip, netmask, country))

    # Sort ranges by start_ip for efficient lookup
    geo_ranges.sort(key=lambda x: x[0])
    
    def find_matching_country(ip_int):
        """Find matching country for an IP using linear search with early exit"""
        if not ip_int:
            return None

        best_match = None
        best_netmask = -1

        for start_ip, end_ip, netmask, country in geo_ranges:
            if start_ip <= ip_int <= end_ip:
                if netmask > best_netmask:
                    best_match = country
                    best_netmask = netmask
            elif start_ip > ip_int:
                break  # Early exit if we've passed possible matches

        return best_match

    # Process rows
    total = len(rows)
    matches = 0
    for index, row in enumerate(rows, 1):
        if index % 1000 == 0:
            print(f"\rProcessing geolocation flows: {index}/{total} (matches: {matches})", end='', flush=True)
            
        src_ip, dst_ip, src_port, dst_port, protocol, *_ = row
        
        # Convert IPs to integers
        src_ip_int = ip_to_int(src_ip)
        dst_ip_int = ip_to_int(dst_ip)
        
        if not src_ip_int and not dst_ip_int:
            continue

        # Find matching countries
        src_country = find_matching_country(src_ip_int)
        dst_country = find_matching_country(dst_ip_int)

        #log_info(logger, f"[DEBUG] src_ip: {src_ip}, dst_ip: {dst_ip}, src_country: {src_country}, dst_country: {dst_country}")
        if src_country or dst_country:
            log_info(logger, f"[INFO] Flow involves an IP in a banned country: {src_ip} ({src_country}) and {dst_ip} ({dst_country})")

            matches += 1
            message = (f"Flow involves an IP in a banned country:\n"
                      f"Source IP: {src_ip} ({src_country or 'N/A'})\n"
                      f"Destination IP: {dst_ip} ({dst_country or 'N/A'})")

            alert_id = f"{src_ip}_{dst_ip}_{protocol}_BannedCountryDetection"

            local_ip = None
            remote_ip = None
            remote_country = None
            if dst_country != None:
                local_ip = src_ip
                remote_country = dst_country
                remote_ip = dst_ip
            elif src_country != None:
                local_ip = dst_ip
                remote_country = src_country
                remote_ip = src_ip


            if config_dict.get("GeolocationFlowsDetection") == 2:
                send_telegram_message(message, row[0:5])
                log_alert_to_db(
                    local_ip, 
                    row, 
                    "Flow involves an IP in a banned country",
                    remote_ip,
                    remote_country, 
                    alert_id,
                    False
                )
            elif config_dict.get("GeolocationFlowsDetection") == 1:
                log_alert_to_db(
                    local_ip, 
                    row, 
                    "Flow involves an IP in a banned country",
                    remote_ip,
                    remote_country, 
                    alert_id,
                    False
                )

    print()  # Final newline
    log_info(logger, f"[INFO] Completed geolocation processing. Found {matches} matches in {total} flows")


def detect_unauthorized_ntp(rows, config_dict):
    """
    Detect NTP traffic (port 123) that doesn't involve approved NTP servers,
    but only alert if the src_ip is in local networks.

    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """

    logger = logging.getLogger(__name__)
    # Get the list of approved NTP servers
    approved_ntp_servers = set(config_dict.get("ApprovedLocalNtpServersList", "").split(","))

    if not approved_ntp_servers:
        log_warn(logger, "[WARN] No approved NTP servers configured")
        return

    LOCAL_NETWORKS=set(config_dict['LocalNetworks'].split(','))

    filtered_rows = [row for row in rows if row[3] == 123]

    for row in filtered_rows:
        src_ip, dst_ip, src_port, dst_port, protocol = row[0:5]

        # Check if either IP is not in the approved NTP servers list
        if src_ip not in approved_ntp_servers:
            if is_ip_in_range(src_ip, LOCAL_NETWORKS):
            # Create a unique identifier for this alert
                alert_id = f"{src_ip}_{dst_ip}__UnauthorizedNTP"

                log_info(logger, f"[INFO] Unauthorized NTP Traffic Detected: {src_ip} -> {dst_ip}")

                message = (f"Unauthorized NTP Traffic Detected:\n"
                        f"Source: {src_ip}:{src_port}\n"
                        f"Destination: {dst_ip}:{dst_port}\n"
                        f"Protocol: {protocol}")

                # Log alert based on configuration level
                if int(config_dict.get("BypassLocalNtpDetection", 0)) == 2:
                    # Send Telegram alert and log to database
                    send_telegram_message(message, row)
                    log_alert_to_db(src_ip, row, "Unauthorized NTP Traffic Detected", dst_ip, dst_port,
                                    alert_id, False)
                elif int(config_dict.get("BypassLocalNtpDetection", 0)) == 1:
                    # Only log to database
                    log_alert_to_db(src_ip, row, "Unauthorized NTP Traffic Detected", dst_ip, dst_port,
                                    alert_id, False)


def detect_unauthorized_dns(rows, config_dict):
    """
    Detect DNS traffic (port 53) that doesn't involve approved DNS servers,
    but only alert if the src_ip is in local networks.

    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    # Get the list of approved DNS servers
    approved_dns_servers = set(config_dict.get("ApprovedLocalDnsServersList", "").split(","))
    if not approved_dns_servers:
        log_warn(logger, "[WARN] No approved DNS servers configured")
        return
    
    LOCAL_NETWORKS=set(config_dict['LocalNetworks'].split(','))
    filtered_rows = [row for row in rows if row[3] == 53]

    for row in filtered_rows:
        src_ip, dst_ip, src_port, dst_port, protocol = row[0:5]

        # Check if either IP is not in the approved DNS servers list
        if src_ip not in approved_dns_servers:
            if is_ip_in_range(src_ip, LOCAL_NETWORKS):
            # Create a unique identifier for this alert
                alert_id = f"{src_ip}_{dst_ip}__UnauthorizedDNS"

                log_info(logger, f"[INFO] Unauthorized DNS Traffic Detected: {src_ip} -> {dst_ip}")

                message = (f"Unauthorized DNS Traffic Detected:\n"
                            f"Source: {src_ip}:{src_port}\n"
                            f"Destination: {dst_ip}:{dst_port}\n"
                            f"Protocol: {protocol}")

                # Log alert based on configuration level
                if int(config_dict.get("BypassLocalDnsDetection", 0)) == 2:
                    # Send Telegram alert and log to database
                    send_telegram_message(message, row)
                    log_alert_to_db(src_ip, row, "Unauthorized DNS Traffic Detected", dst_ip, dst_port,
                                    alert_id, False)
                elif int(config_dict.get("BypassLocalDnsDetection", 0)) == 1:
                    # Only log to database
                    log_alert_to_db(src_ip, row, "Unauthorized DNS Traffic Detected", dst_ip, dst_port,
                                    alert_id, False)


def detect_incorrect_authoritative_dns(rows, config_dict):
    """
    Detect and alert if a flow originates from a local network (src_ip) and uses
    dst_port 53 (DNS) with a dst_ip that is not in the ApprovedAuthoritativeDnsServersList.

    Args:
        rows: List of flow records.
        config_dict: Dictionary containing configuration settings.
    """
    logger = logging.getLogger(__name__)
    # Get the list of approved authoritative DNS servers
    approved_authoritative_dns_servers = set(config_dict.get("ApprovedAuthoritativeDnsServersList", "").split(","))
    if not approved_authoritative_dns_servers:
        log_warn(logger, "[WARN] No approved authoritative DNS servers configured")
        return

    APPROVED_LOCAL_DNS_SERVERS_LIST = set(config_dict.get("ApprovedLocalDnsServersList", "").split(","))
    filtered_rows = [row for row in rows if row[3] == 53]
    
    for row in filtered_rows:
        src_ip, dst_ip, src_port, dst_port, protocol = row[0:5]

        # Check if src_ip is in local networks
        if src_ip in APPROVED_LOCAL_DNS_SERVERS_LIST and dst_ip not in approved_authoritative_dns_servers:
            # Check if dst_ip is not in the approved authoritative DNS servers list
            alert_id = f"{src_ip}_{dst_ip}__IncorrectAuthoritativeDNS"

            log_info(logger, f"[INFO] Incorrect Authoritative DNS Detected: {src_ip} -> {dst_ip}")

            message = (f"Incorrect Authoritative DNS Detected:\n"
                        f"Source: {src_ip}:{src_port}\n"
                        f"Destination: {dst_ip}:{dst_port}\n"
                        f"Protocol: {protocol}")

            # Log alert based on configuration level
            if int(config_dict.get("IncorrectAuthoritativeDnsDetection", 0)) == 2:
                # Send Telegram alert and log to database
                send_telegram_message(message, row)
                log_alert_to_db(src_ip, row, "Incorrect Authoritative DNS Detected", dst_ip, dst_port,
                                alert_id, False)
            elif int(config_dict.get("IncorrectAuthoritativeDnsDetection", 0)) == 1:
                # Only log to database
                log_alert_to_db(src_ip, row, "Incorrect Authoritative DNS Detected", dst_ip, dst_port,
                                alert_id, False)


def detect_incorrect_ntp_stratum(rows, config_dict):
    """
    Detect and alert if a flow originates from a local network (src_ip) and uses
    dst_port 123 (NTP) with a dst_ip that is not in the ApprovedNtpStratumServersList.

    Args:
        rows: List of flow records.
        config_dict: Dictionary containing configuration settings.
    """
    logger = logging.getLogger(__name__)
    # Get the list of approved NTP stratum servers
    approved_ntp_stratum_servers = set(config_dict.get("ApprovedNtpStratumServersList", "").split(","))
    if not approved_ntp_stratum_servers:
        log_warn(logger, "[WARN] No approved NTP stratum servers configured")
        return
    
    APPROVED_LOCAL_NTP_SERVERS_LIST = set(config_dict.get("ApprovedLocalNtpServersList", "").split(","))
    filtered_rows = [row for row in rows if row[3] == 123]

    for row in filtered_rows:
        src_ip, dst_ip, src_port, dst_port, protocol = row[0:5]

        # Check if src_ip is in local networks
        if src_ip in APPROVED_LOCAL_NTP_SERVERS_LIST and dst_ip not in approved_ntp_stratum_servers:
            # Check if dst_ip is not in the approved NTP stratum servers list
            alert_id = f"{src_ip}_{dst_ip}__IncorrectNTPStratum"

            log_info(logger, f"[INFO] Incorrect NTP Stratum Detected: {src_ip} -> {dst_ip}")

            message = (f"Incorrect NTP Stratum Detected:\n"
                        f"Source: {src_ip}:{src_port}\n"
                        f"Destination: {dst_ip}:{dst_port}\n"
                        f"Protocol: {protocol}")

            # Log alert based on configuration level
            if int(config_dict.get("IncorrectNtpStratrumDetection", 0)) == 2:
                # Send Telegram alert and log to database
                send_telegram_message(message, row)
                log_alert_to_db(src_ip, row, "Incorrect NTP Stratum Detected", dst_ip, dst_port,
                                alert_id, False)
            elif int(config_dict.get("IncorrectNtpStratrumDetection", 0)) == 1:
                # Only log to database
                log_alert_to_db(src_ip, row, "Incorrect NTP Stratum Detected", dst_ip, dst_port,
                                alert_id, False)


def remove_whitelist(rows, whitelist_entries):
    """
    Remove rows that match whitelist entries.
    
    Args:
        rows: List of flow records
        whitelist_entries: List of whitelist entries from database
        
    Returns:
        list: Filtered rows with whitelisted entries removed
    """
    logger = logging.getLogger(__name__)

    if not whitelist_entries:
        return rows

    filtered_rows = []
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol = row[0:5]
        is_whitelisted = False
        
        for whitelist_id, whitelist_src_ip, whitelist_dst_ip, whitelist_dst_port, whitelist_protocol in whitelist_entries:
            # Check if the flow matches any whitelist entry
            src_match = (whitelist_src_ip == src_ip or whitelist_src_ip == dst_ip)
            dst_match = (whitelist_dst_ip == dst_ip or whitelist_dst_ip == src_ip)
            port_match = (int(whitelist_dst_port) in (src_port, dst_port))
            protocol_match = (int(whitelist_protocol) == protocol)
            
            if src_match and dst_match and port_match and protocol_match:
                is_whitelisted = True
    
        if not is_whitelisted:
            filtered_rows.append(row)
    
    log_info(logger, f"[INFO] Removed {len(rows) - len(filtered_rows)} whitelisted flows")
    return filtered_rows