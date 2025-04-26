import sqlite3
import json
from datetime import datetime, timedelta
from utils import log_info, is_ip_in_range, log_warn, log_error, ip_to_int, calculate_broadcast  # Assuming log_info and is_ip_in_range are defined in utils
from const import CONST_LOCALHOSTS_DB, CONST_ALERTS_DB, CONST_ALLFLOWS_DB, CONST_GEOLOCATION_DB # Assuming constants are defined in const
from database import connect_to_db, log_alert_to_db, update_tag_to_allflows  # Import connect_to_db and update_tag from database.py
from notifications import send_telegram_message  # Import notification functions
import logging
import requests

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
        if len(entry) >= 5:  # Ensure entry has at least 5 elements
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
    Detect DNS traffic (port 53) that doesn't involve approved DNS servers,
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


def remove_broadcast_flows(rows, config_dict):
    """
    Remove flows where the destination IP matches broadcast addresses of LOCAL_NETWORKS.
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
        
    Returns:
        list: Filtered rows with broadcast destination addresses removed
    """
    logger = logging.getLogger(__name__)
    
    # Get local networks
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    
    # Calculate broadcast addresses for all local networks
    broadcast_addresses = set()
    for network in LOCAL_NETWORKS:
        broadcast_ip = calculate_broadcast(network)
        if broadcast_ip:
            broadcast_addresses.add(broadcast_ip)
            log_info(logger, f"[INFO] Found broadcast address {broadcast_ip} for network {network}")
    
    if not broadcast_addresses:
        log_warn(logger, "[WARN] No broadcast addresses found for LOCAL_NETWORKS")
        return rows
    
    # Filter out flows with broadcast destinations
    filtered_rows = []
    broadcast_count = 0
    
    for row in rows:
        dst_ip = row[1]  # Destination IP is second field
        if dst_ip not in broadcast_addresses:
            filtered_rows.append(row)
        else:
            broadcast_count += 1
    
    if broadcast_count > 0:
        log_info(logger, f"[INFO] Removed {broadcast_count} broadcast flows")
    
    return filtered_rows


def detect_dead_connections(config_dict):
    """
    Detect dead connections by finding flows with:
    - Multiple sent packets but no received packets
    - Seen multiple times
    - Not ICMP or IGMP protocols
    - Not multicast or broadcast destinations
    
    Args:
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    
    try:
        conn = connect_to_db(CONST_ALLFLOWS_DB)
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to allflows database")
            return

        cursor = conn.cursor()
        
        # Query for dead connections
        cursor.execute("""
                WITH ConnectionPairs AS (
                    SELECT 
                        a1.src_ip as initiator_ip,
                        a1.dst_ip as responder_ip,
                        a1.src_port as initiator_port,
                        a1.dst_port as responder_port,
                        a1.protocol as connection_protocol,
                        a1.packets as forward_packets,
                        a1.bytes as forward_bytes,
                        a1.times_seen as forward_seen,
                        a1.tags as row_tags,
                        COALESCE(a2.packets, 0) as reverse_packets,
                        COALESCE(a2.bytes, 0) as reverse_bytes,
                        COALESCE(a2.times_seen, 0) as reverse_seen
                    FROM allflows a1
                    LEFT JOIN allflows a2 ON 
                        a2.src_ip = a1.dst_ip 
                        AND a2.dst_ip = a1.src_ip
                        AND a2.src_port = a1.dst_port
                        AND a2.dst_port = a1.src_port
                        AND a2.protocol = a1.protocol
                )
                SELECT 
                    initiator_ip,
                    responder_ip,
                    responder_port,
                    forward_packets,
                    reverse_packets,
                    connection_protocol,
                    row_tags,
                    COUNT(*) as connection_count,
                    sum(forward_packets) as f_packets,
                    sum(reverse_packets) as r_packets
                FROM ConnectionPairs
                WHERE connection_protocol NOT IN (1, 2)  -- Exclude ICMP and IGMP
                AND row_tags not like '%DeadConnectionDetection%'
                AND responder_ip NOT LIKE '224%'  -- Exclude multicast
                AND responder_ip NOT LIKE '239%'  -- Exclude multicast
                AND responder_ip NOT LIKE '255%'  -- Exclude broadcast
                GROUP BY initiator_ip, responder_ip, responder_port, connection_protocol
                HAVING 
                    f_packets > 2
                    AND r_packets < 1
        """)
        
        dead_connections = cursor.fetchall()
        log_info(logger, f"[INFO] Found {len(dead_connections)} potential dead connections")

        for row in dead_connections:
            src_ip = row[0]
            dst_ip = row[1]
            dst_port = row[2]
            protocol = row[5]
            row_tags = row[6]  # Existing tags for the flow

            alert_id = f"{src_ip}_{dst_ip}_{protocol}_{dst_port}_DeadConnection"
            
            message = (f"Dead Connection Detected:\n"
                      f"Source: {src_ip}\n"
                      f"Destination: {dst_ip}:{dst_port}\n"
                      f"Protocol: {protocol}\n")
            
            log_info(logger, f"[INFO] Dead connection detected: {src_ip}->{dst_ip}:{dst_port} {protocol}")
            
            # Add a Tag to the matching row using update_tag
            if not update_tag_to_allflows("allflows", "DeadConnectionDetection", src_ip, dst_ip, dst_port):
                log_error(logger, f"[ERROR] Failed to add tag for flow: {src_ip} -> {dst_ip}:{dst_port}")

            # Handle alerts based on configuration
            if config_dict.get("DeadConnectionDetection") == 2:
                send_telegram_message(message, row)
                log_alert_to_db(
                    src_ip,
                    row,
                    "Dead Connection Detected",
                    dst_ip,
                    dst_port,
                    alert_id,
                    False
                )
            elif config_dict.get("DeadConnectionDetection") == 1:
                log_alert_to_db(
                    src_ip,
                    row,
                    "Dead Connection Detected",
                    dst_ip,
                    dst_port,
                    alert_id,
                    False
                )

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error in detect_dead_connections: {e}")
    finally:
        if 'conn' in locals():
            conn.close()


def detect_reputation_flows(rows, config_dict, reputation_data):
    """
    Detect flows where a local IP communicates with an IP on the reputation list.

    Args:
        rows: List of flow records.
        config_dict: Dictionary containing configuration settings.
        reputation_data: Preprocessed reputation list data.
    """
    logger = logging.getLogger(__name__)

    # Pre-process reputation data into ranges
    reputation_ranges = []
    for entry in reputation_data:
        if len(entry) >= 4:  # Ensure entry has at least 4 elements
            network, start_ip, end_ip, netmask = entry[:4]
            reputation_ranges.append((network, start_ip, end_ip, netmask))

    # Sort ranges by start_ip for efficient lookup
    reputation_ranges.sort(key=lambda x: x[0])

    def find_match(ip_int):
        """Find if an IP is in the reputation list."""
        if not ip_int:
            return None

        for network, start_ip, end_ip, netmask in reputation_ranges:
            if start_ip <= ip_int <= end_ip:
                return (True, network)
            elif start_ip > ip_int:
                break  # Early exit if we've passed possible matches

        return (False,None)

    # Get local networks from the configuration
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))

    # Process rows
    total = len(rows)
    matches = 0
    for index, row in enumerate(rows, 1):

        src_ip, dst_ip, src_port, dst_port, protocol, *_ = row

        # Convert IPs to integers
        src_ip_int = ip_to_int(src_ip)
        dst_ip_int = ip_to_int(dst_ip)

        if not src_ip_int or not dst_ip_int:
            continue

        # Check if src_ip or dst_ip is in LOCAL_NETWORKS
        is_src_local = is_ip_in_range(src_ip, LOCAL_NETWORKS)

        (reputation_match, match_network) = find_match(dst_ip_int)

        # If src_ip is local, check dst_ip against the reputation list
        if is_src_local and reputation_match:
            matches += 1
            log_info(logger, f"[INFO] Flow involves an IP on the reputation list: {src_ip} -> {dst_ip} ({match_network})")

            message = (f"Flow involves an IP on the reputation list:\n"
                       f"Source IP: {src_ip}\n"
                       f"Destination IP: {dst_ip}\n"
                       f"Match Network: {match_network}")

            alert_id = f"{src_ip}_{dst_ip}_{protocol}_ReputationListDetection"

            if config_dict.get("ReputationListDetection") == 2:
                send_telegram_message(message, row[0:5])
                log_alert_to_db(
                    src_ip,
                    row,
                    "Flow involves an IP on the reputation list",
                    dst_ip,
                    match_network,
                    alert_id,
                    False
                )
            elif config_dict.get("ReputationListDetection") == 1:
                log_alert_to_db(
                    src_ip,
                    row,
                    "Flow involves an IP on the reputation list",
                    dst_ip,
                    match_network,
                    alert_id,
                    False
                )

    log_info(logger, f"[INFO] Completed reputation flow processing. Found {matches} matches in {total} flows")


def detect_vpn_traffic(rows, config_dict):
    """
    Detect VPN traffic from local hosts by checking for common VPN protocols and ports.
    
    Common VPN protocols and ports:
    - OpenVPN: UDP 1194, TCP 443/1194
    - IPsec/IKE: UDP 500 (IKE), UDP 4500 (NAT-T)
    - L2TP: UDP 1701
    - PPTP: TCP 1723
    - WireGuard: UDP 51820
    - SoftEther: TCP 443, TCP 992, TCP 5555
    - Cisco AnyConnect: TCP/UDP 443
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    
    # Define VPN-related ports and protocols
    VPN_PORTS = {
        'TCP': {1194, 1723, 992, 5555},  # TCP ports (protocol 6)
        'UDP': {500, 4500, 1194, 1701, 51820}  # UDP ports (protocol 17)
    }

    VPN_PROTOCOLS = {
        47: 'GRE/PPTP',        # Generic Routing Encapsulation (PPTP)
        50: 'ESP',             # IPsec Encapsulating Security Payload
        51: 'AH',              # IPsec Authentication Header
        41: 'IPv6 Tunnel',     # IPv6 encapsulation
        97: 'ETHERIP',         # Ethernet-within-IP encapsulation
        115: 'L2TP'           # Layer 2 Tunneling Protocol
    }
    
    # Get local networks
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    
    # Get whitelisted VPN servers if configured
    approved_vpn_servers = set(config_dict.get("ApprovedVpnServersList", "").split(","))
    
    vpn_flows = {}  # Track potential VPN flows by source IP
    
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, *_ = row
        
        # Only check outbound connections from local networks
        if not is_ip_in_range(src_ip, LOCAL_NETWORKS):
            continue
            
        # Skip if destination is an approved VPN server
        if dst_ip in approved_vpn_servers:
            continue
        
        is_vpn = False
        proto_name = None

        # Check TCP/UDP ports
        if protocol == 6 and dst_port in VPN_PORTS['TCP']:
            is_vpn = True
            proto_name = f'TCP/{dst_port}'
        elif protocol == 17 and dst_port in VPN_PORTS['UDP']:
            is_vpn = True
            proto_name = f'UDP/{dst_port}'
        # Check VPN protocols
        elif protocol in VPN_PROTOCOLS:
            is_vpn = True
            proto_name = VPN_PROTOCOLS[protocol]

        if not is_vpn:
            continue
        
        # Create flow identifier
        alert_id = f"{src_ip}_{dst_ip}_{protocol}_{dst_port}"
        
        # Alert if this is first time seeing this flow
        alert_id = f"{alert_id}_VPNDetection"
        
        message = (f"Potential VPN Traffic Detected:\n"
                  f"Source: {src_ip}\n"
                  f"Destination: {dst_ip}:{dst_port}\n"
                  f"Protocol: {proto_name}\n")

        
        log_info(logger, f"[INFO] Potential VPN traffic detected: {src_ip} -> {dst_ip}:{dst_port} ({proto_name})")
        
        if config_dict.get("VpnTrafficDetection") == 2:
            send_telegram_message(message, row)
            log_alert_to_db(
                src_ip,
                row,
                "Potential VPN Traffic Detected",
                dst_ip,
                f"Port:{dst_port} Proto:{proto_name}",
                alert_id,
                False
            )
        elif config_dict.get("VpnTrafficDetection") == 1:
            log_alert_to_db(
                src_ip,
                row,
                "Potential VPN Traffic Detected",
                dst_ip,
                f"Port:{dst_port} Proto:{proto_name}",
                alert_id,
                False
            )


def update_tor_nodes():
    """
    Download and update Tor node list from dan.me.uk.
    Only updates if the last update was more than 1 hour ago.
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_GEOLOCATION_DB)
    
    try:
        cursor = conn.cursor()
        
        # Check last update time
        cursor.execute("""
            SELECT MAX(last_seen) FROM tornodes
        """)
        last_update = cursor.fetchone()[0]
        
        if last_update:
            last_update = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
            if datetime.now() - last_update < timedelta(hours=1):
                return  # Skip update if less than 1 hour has passed
        
        # Download new list
        response = requests.get('https://www.dan.me.uk/torlist/?full', 
                              headers={'User-Agent': 'NetFlowIPS TorNode Checker'})
        if response.status_code != 200:
            log_error(logger, f"[ERROR] Failed to download Tor node list: {response.status_code}")
            return
            
        # Parse IPs (one per line)
        tor_nodes = set(ip.strip() for ip in response.text.split('\n') if ip.strip())
        
        # Update database
        cursor.executemany("""
            INSERT INTO tornodes (ip_address) 
            VALUES (?) 
            ON CONFLICT(ip_address) 
            DO UPDATE SET 
                last_seen=CURRENT_TIMESTAMP,
                times_seen=times_seen + 1
        """, [(ip,) for ip in tor_nodes])
        
        conn.commit()
        log_info(logger, f"[INFO] Updated Tor node list with {len(tor_nodes)} nodes")
        
    except Exception as e:
        log_error(logger, f"[ERROR] Error updating Tor nodes: {e}")
    finally:
        if conn:
            conn.close()

def detect_tor_traffic(rows, config_dict):
    """
    Detect traffic to/from known Tor nodes.
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    
    # Update Tor node list if needed
    update_tor_nodes()
    
    # Get local networks
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    
    try:
        # Get current Tor nodes
        conn = connect_to_db(CONST_GEOLOCATION_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT ip_address FROM tornodes")
        tor_nodes = set(row[0] for row in cursor.fetchall())
        
        for row in rows:
            src_ip, dst_ip, src_port, dst_port, protocol, *_ = row
            
            # Check if source is local and destination is Tor node
            is_src_local = is_ip_in_range(src_ip, LOCAL_NETWORKS)
            
            if is_src_local and dst_ip in tor_nodes:
                alert_id = f"{src_ip}_{dst_ip}_{protocol}_{dst_port}_TorTraffic"
                message = (f"Tor Traffic Detected:\n"
                          f"Local IP: {src_ip}\n"
                          f"Tor Node: {dst_ip}:{dst_port}\n"
                          f"Protocol: {protocol}")
                
                log_info(logger, f"[INFO] Tor traffic detected: {src_ip} -> {dst_ip}:{dst_port}")
                
                if config_dict.get("TorTrafficDetection") == 2:
                    send_telegram_message(message, row)
                    log_alert_to_db(
                        src_ip,
                        row,
                        "Tor Traffic Detected",
                        dst_ip,
                        "Tor Exit Node",
                        alert_id,
                        False
                    )
                elif config_dict.get("TorTrafficDetection") == 1:
                    log_alert_to_db(
                        src_ip,
                        row,
                        "Tor Traffic Detected",
                        dst_ip,
                        "Tor Exit Node",
                        alert_id,
                        False
                    )
                    
    except Exception as e:
        log_error(logger, f"[ERROR] Error in detect_tor_traffic: {e}")
    finally:
        if 'conn' in locals():
            conn.close()


def detect_high_risk_ports(rows, config_dict):
    """
    Detect traffic from local networks to high-risk destination ports.
    Common high-risk ports include:
    - 135: MSRPC
    - 137-139: NetBIOS
    - 445: SMB
    - 25/587: SMTP
    - 22: SSH
    - 23: Telnet
    - 3389: RDP
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    
    # Get high-risk ports from config
    high_risk_ports = set(
        int(port.strip()) 
        for port in config_dict.get("HighRiskPorts", "135,137,138,139,445,25,587,22,23,3389").split(",")
        if port.strip()
    )
    
    # Get local networks
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    
    # Get whitelisted destinations if configured
    approved_destinations = set(config_dict.get("ApprovedHighRiskDestinations", "").split(","))
    
    total = len(rows)
    matches = 0
    
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, *_ = row
        
        # Only check outbound connections from local networks
        if not is_ip_in_range(src_ip, LOCAL_NETWORKS):
            continue
            
        # Skip if destination is approved
        if dst_ip in approved_destinations:
            continue
        
        # Check if destination port is in high-risk list
        if dst_port in high_risk_ports:
            matches += 1
            
            service_name = {
                135: "MSRPC",
                137: "NetBIOS",
                138: "NetBIOS",
                139: "NetBIOS",
                445: "SMB",
                25: "SMTP",
                587: "SMTP",
                22: "SSH",
                23: "Telnet",
                3389: "RDP"
            }.get(dst_port, "Unknown")
            
            alert_id = f"{src_ip}_{dst_ip}_{protocol}_{dst_port}_HighRiskPort"
            
            message = (f"High-Risk Port Traffic Detected:\n"
                      f"Source: {src_ip}\n"
                      f"Destination: {dst_ip}:{dst_port}\n"
                      f"Service: {service_name}\n"
                      f"Protocol: {protocol}\n"
                      f"Packets: {packets}")
            
            log_info(logger, f"[INFO] High-risk port traffic detected: {src_ip} -> {dst_ip}:{dst_port} ({service_name})")
            
            if config_dict.get("HighRiskPortDetection") == 2:
                send_telegram_message(message, row)
                log_alert_to_db(
                    src_ip,
                    row,
                    "High-Risk Port Traffic Detected",
                    dst_ip,
                    f"Port:{dst_port} ({service_name})",
                    alert_id,
                    False
                )
            elif config_dict.get("HighRiskPortDetection") == 1:
                log_alert_to_db(
                    src_ip,
                    row,
                    "High-Risk Port Traffic Detected",
                    dst_ip,
                    f"Port:{dst_port} ({service_name})",
                    alert_id,
                    False
                )
    
    log_info(logger, f"[INFO] Completed high-risk port detection. Found {matches} matches in {total} flows")


def detect_many_destinations(rows, config_dict):
    """
    Detect hosts from local networks that are communicating with an unusually high
    number of different destination IPs, which could indicate scanning or malware.
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    
    # Get configuration parameters
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    dest_threshold = int(config_dict.get("MaxUniqueDestinations", "100"))
    time_window = int(config_dict.get("DestinationTimeWindowMinutes", "5"))
    
    # Track destinations per source IP
    source_stats = {}
    
    # Current time for time window calculations
    current_time = datetime.now()
    
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, *_, flow_start = row
        
        # Only check sources from local networks
        if not is_ip_in_range(src_ip, LOCAL_NETWORKS):
            continue
            
        # Convert flow_start to datetime
        try:
            flow_time = datetime.fromisoformat(flow_start.replace('Z', '+00:00'))
            if (current_time - flow_time).total_seconds() > time_window * 60:
                continue
        except (ValueError, AttributeError):
            continue
        
        # Initialize source IP tracking
        if src_ip not in source_stats:
            source_stats[src_ip] = {
                'destinations': set(),
                'ports': set(),
                'first_seen': flow_start
            }
        
        # Track unique destinations and ports
        source_stats[src_ip]['destinations'].add(dst_ip)
        source_stats[src_ip]['ports'].add(dst_port)
        
        # Check if threshold is exceeded
        if len(source_stats[src_ip]['destinations']) > dest_threshold:
            unique_dests = len(source_stats[src_ip]['destinations'])
            unique_ports = len(source_stats[src_ip]['ports'])
            
            alert_id = f"{src_ip}_ManyDestinations_{int(time.time())}"
            
            message = (f"Host Connecting to Many Destinations:\n"
                      f"Source IP: {src_ip}\n"
                      f"Unique Destinations: {unique_dests}\n"
                      f"Unique Ports: {unique_ports}\n"
                      f"Time Window: {time_window} minutes\n"
                      f"First Seen: {source_stats[src_ip]['first_seen']}")
            
            log_info(logger, f"[INFO] Excessive destinations detected from {src_ip}: "
                            f"{unique_dests} destinations, {unique_ports} ports")
            
            if config_dict.get("ManyDestinationsDetection") == 2:
                send_telegram_message(message, row)
                log_alert_to_db(
                    src_ip,
                    row,
                    "Excessive Unique Destinations",
                    f"{unique_dests} destinations",
                    f"{unique_ports} ports",
                    alert_id,
                    False
                )
            elif config_dict.get("ManyDestinationsDetection") == 1:
                log_alert_to_db(
                    src_ip,
                    row,
                    "Excessive Unique Destinations",
                    f"{unique_dests} destinations",
                    f"{unique_ports} ports",
                    alert_id,
                    False
                )
            
            # Remove this source from tracking to prevent repeated alerts
            del source_stats[src_ip]
    
    # Log summary
    if source_stats:
        top_sources = sorted(
            source_stats.items(),
            key=lambda x: len(x[1]['destinations']),
            reverse=True
        )[:5]
        
        log_info(logger, "[INFO] Top sources by unique destinations:")
        for src_ip, stats in top_sources:
            log_info(logger, f"  {src_ip}: {len(stats['destinations'])} destinations, "
                            f"{len(stats['ports'])} ports")


def detect_port_scanning(rows, config_dict):
    """
    Detect local hosts that are connecting to many different ports on the same destination IP,
    which could indicate port scanning activity.
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    
    # Get configuration parameters
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    port_threshold = int(config_dict.get("MaxPortsPerDestination", "15"))
    time_window = int(config_dict.get("PortScanTimeWindowMinutes", "5"))
    
    # Dictionary to track {(src_ip, dst_ip): {ports, first_seen}}
    scan_tracking = {}
    
    # Current time for time window calculations
    current_time = datetime.now()
    
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, *_, flow_start = row
        
        # Only check sources from local networks
        if not is_ip_in_range(src_ip, LOCAL_NETWORKS):
            continue
            
        # Convert flow_start to datetime
        try:
            flow_time = datetime.fromisoformat(flow_start.replace('Z', '+00:00'))
            if (current_time - flow_time).total_seconds() > time_window * 60:
                continue
        except (ValueError, AttributeError):
            continue
        
        # Create key for tracking
        flow_key = (src_ip, dst_ip)
        
        # Initialize tracking for new source-destination pair
        if flow_key not in scan_tracking:
            scan_tracking[flow_key] = {
                'ports': set(),
                'first_seen': flow_start,
                'protocols': set()
            }
        
        # Track unique destination ports and protocols
        scan_tracking[flow_key]['ports'].add(dst_port)
        scan_tracking[flow_key]['protocols'].add(protocol)
        
        # Check if port threshold is exceeded
        if len(scan_tracking[flow_key]['ports']) > port_threshold:
            unique_ports = len(scan_tracking[flow_key]['ports'])
            protocols = len(scan_tracking[flow_key]['protocols'])
            
            alert_id = f"{src_ip}_{dst_ip}_PortScan_{int(time.time())}"
            
            message = (f"Potential Port Scan Detected:\n"
                      f"Source IP: {src_ip}\n"
                      f"Target IP: {dst_ip}\n"
                      f"Unique Ports: {unique_ports}\n"
                      f"Protocols: {sorted(scan_tracking[flow_key]['protocols'])}\n"
                      f"Time Window: {time_window} minutes\n"
                      f"First Seen: {scan_tracking[flow_key]['first_seen']}")
            
            log_info(logger, f"[INFO] Port scan detected from {src_ip} to {dst_ip}: "
                            f"{unique_ports} ports across {protocols} protocols")
            
            if config_dict.get("PortScanDetection") == 2:
                send_telegram_message(message, row)
                log_alert_to_db(
                    src_ip,
                    row,
                    "Port Scan Detected",
                    dst_ip,
                    f"Ports:{unique_ports} Protocols:{protocols}",
                    alert_id,
                    False
                )
            elif config_dict.get("PortScanDetection") == 1:
                log_alert_to_db(
                    src_ip,
                    row,
                    "Port Scan Detected",
                    dst_ip,
                    f"Ports:{unique_ports} Protocols:{protocols}",
                    alert_id,
                    False
                )
            
            # Remove this pair from tracking to prevent repeated alerts
            del scan_tracking[flow_key]
    
    # Log summary of top scanners
    if scan_tracking:
        top_scanners = sorted(
            scan_tracking.items(),
            key=lambda x: len(x[1]['ports']),
            reverse=True
        )[:5]
        
        log_info(logger, "[INFO] Top potential port scanners:")
        for (src_ip, dst_ip), stats in top_scanners:
            log_info(logger, f"  {src_ip} -> {dst_ip}: {len(stats['ports'])} ports, "
                            f"{len(stats['protocols'])} protocols")


