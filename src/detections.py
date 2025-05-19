import sqlite3
import json
from datetime import datetime, timedelta
from database.alerts import log_alert_to_db
from database.allflows import update_tag_to_allflows
from src.notifications import send_telegram_message  # Import notification functions
import logging
import requests
from src.const import CONST_CONSOLIDATED_DB
from init import *

def update_local_hosts(rows, config_dict):
    """
    Check for new IPs in the provided rows and add them to localhosts.db if necessary.
    Uses an in-memory list to avoid repeated database queries.
    """
    logger = logging.getLogger(__name__)
    log_info(logger,"[INFO] Starting to update local hosts")
    # Connect to the localhosts database
    LOCAL_NETWORKS=set(config_dict['LocalNetworks'].split(','))

    try:

        
        existing_localhosts = set(row[0] for row in get_localhosts())
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
                    insert_localhost_basic(ip_address, original_flow)

                    existing_localhosts.add(ip_address)  # Add to in-memory set
                    log_info(logger, f"[INFO] Added new IP to localhosts.db: {ip_address}")
                    
                    message = f"New Host Detected: {ip_address}"

                    handle_alert(
                        config_dict,
                        "NewHostsDetection",
                        message,
                        ip_address,
                        row,
                        "New Host Detected",
                        "",
                        "",
                        f"{ip_address}_NewHostsDetection"
                    )  

    except Exception as e:
        log_error(logger, f"[ERROR] Error in update_local_hosts: {e}")


    log_info(logger,"[INFO] Finished updating local hosts")

def detect_new_outbound_connections(rows, config_dict):
    """
    Detect new outbound connections from local clients to external servers.
    A server is identified by having a lower port number than the client.
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    log_info(logger,f"[INFO] Preparing to detect new outbound connections")

    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))

    try:

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
                
                count = get_alert_count_by_id(alert_id)

                exists = count > 0
                
                if not exists:
                    message = (f"New outbound connection detected:\n"
                             f"Local client: {src_ip}\n"
                             f"Remote server: {dst_ip}:{dst_port}\n"
                             f"Protocol: {protocol}")
                    
                    log_info(logger, f"[INFO] New outbound connection detected: {src_ip} -> {dst_ip}:{dst_port}")

                    handle_alert(
                        config_dict,
                        "NewOutboundDetection",
                        message,
                        src_ip,
                        row,
                        "New outbound connection detected",
                        dst_ip,
                        dst_port,
                        alert_id
                    )    

    except Exception as e:
        log_error(logger, f"[ERROR] Error in detect_new_outbound_connections: {e}")
    
    log_info(logger,f"[INFO] Finished detecting new outbound connections")


def router_flows_detection(rows, config_dict):
    """
    Detect and handle flows involving a router IP address.
    Uses exact IP matching instead of network matching.
    """
    logger = logging.getLogger(__name__)
    log_info(logger,"[INFO] Detecting flows to or from the router")

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

            message = f"Flow involves a router IP address: {router_ip_seen}"

            handle_alert(
                config_dict,
                "RouterFlowsDetection",
                message,
                router_ip_seen,
                row,
                "Flow involves a router IP address",
                src_port,
                dst_port,
                f"{router_ip_seen}_{src_ip}_{dst_ip}_{protocol}_{router_port}_RouterFlowsDetection"
            )

    log_info(logger,"[INFO] Finished detecting flows to or from the router")

def local_flows_detection(rows, config_dict):
    """
    Detect and handle flows where both src_ip and dst_ip are in LOCAL_NETWORKS,
    excluding any flows involving ROUTER_IPADDRESS.
    """
    logger = logging.getLogger(__name__)
    ROUTER_LIST = set(config_dict['RouterIpAddresses'].split(','))
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))

    log_info(logger,"[INFO] Detecting flows for the same local networks going through the router")
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
            message = f"Flow involves two local hosts: {src_ip} and {dst_ip}"

            handle_alert(
                config_dict,
                "LocalFlowsDetection",
                message,
                src_ip,
                row,
                "Flow involves two local hosts",
                dst_ip,
                dst_port,
                f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_LocalFlowsDetection"
            )

    log_info(logger,"[INFO] Finished detecting flows for the same local network going through the router")

def foreign_flows_detection(rows, config_dict):
    """
    Detect and handle flows where neither src_ip nor dst_ip is in LOCAL_NETWORKS.
    """
    logger = logging.getLogger(__name__)
    log_info(logger,"[INFO] Detecting flows that don't involve any local network")
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

            message = f"Flow involves two foreign hosts: {src_ip} and {dst_ip}"

            handle_alert(
                config_dict,
                "ForeignFlowsDetection",
                message,
                src_ip,
                row,
                "Flow involves two foreign hosts",
                dst_ip,
                dst_port,
                f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_ForeignFlowsDetection"
            )
            
    log_info(logger,"[INFO] Finished detecting flows that don't involve any local network")

def detect_geolocation_flows(rows, config_dict, geolocation_data):
    """
    Optimized version of geolocation flow detection.
    Uses set lookups and precomputed data structures for better performance.
    """
    logger = logging.getLogger(__name__)
    
    log_info(logger,"[INFO] Started detecting flows involving banned geolocations")
    
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

                handle_alert(
                    config_dict,
                    "GeolocationFlowsDetection",
                    message,
                    local_ip,
                    row,
                    "Flow involves an IP in a banned country",
                    remote_ip,
                    remote_country,
                    alert_id
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
    log_info(logger,"[INFO] Detecting unauthorized NTP destinations")
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

                handle_alert(
                    config_dict,
                    "BypassLocalNtpDetection",
                    message,
                    src_ip,
                    row,
                    "Unauthorized NTP Traffic Detected",
                    dst_ip,
                    dst_port,
                    alert_id
                )

    log_info(logger,"[INFO] Finished detecting unauthorized NTP destinations")

def detect_unauthorized_dns(rows, config_dict):
    """
    Detect DNS traffic (port 53) that doesn't involve approved DNS servers,
    but only alert if the src_ip is in local networks.

    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    log_info(logger,"[INFO] Starting detecting unauthorized NTP destinations")
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

                handle_alert(
                    config_dict,
                    "BypassLocalDnsDetection",
                    message,
                    src_ip,
                    row,
                    "Unauthorized DNS Traffic Detected",
                    dst_ip,
                    dst_port,
                    alert_id
                )

    log_info(logger,"[INFO] Finished detecting unauthorized DNS destinations")

def detect_incorrect_authoritative_dns(rows, config_dict):
    """
    Detect and alert if a flow originates from a local network (src_ip) and uses
    dst_port 53 (DNS) with a dst_ip that is not in the ApprovedAuthoritativeDnsServersList.

    Args:
        rows: List of flow records.
        config_dict: Dictionary containing configuration settings.
    """
    logger = logging.getLogger(__name__)
    log_info(logger,"[INFO] Started detecting local DNS servers using unauthorized authoritative DNS")
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

            handle_alert(
                config_dict,
                "IncorrectAuthoritativeDnsDetection",
                message,
                src_ip,
                row,
                "Incorrect Authoritative DNS Detected",
                dst_ip,
                dst_port,
                alert_id
            )

    log_info(logger,"[INFO] Finished detecting local DNS servers using unauthorized authoritative DNS")

def detect_incorrect_ntp_stratum(rows, config_dict):
    """
    Detect and alert if a flow originates from a local network (src_ip) and uses
    dst_port 123 (NTP) with a dst_ip that is not in the ApprovedNtpStratumServersList.

    Args:
        rows: List of flow records.
        config_dict: Dictionary containing configuration settings.
    """
    logger = logging.getLogger(__name__)
    log_info(logger,"[INFO] Started detecting local NTP servers using unauthorized stratum NTP destinations")
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

            handle_alert(
                config_dict,
                "IncorrectNtpStratrumDetection",
                message,
                src_ip,
                row,
                "Incorrect NTP Stratum Detected",
                dst_ip,
                dst_port,
                alert_id
            )

    log_info(logger,"[INFO] Finished detecting local NTP servers using unauthorized stratum NTP destinations")

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
    log_info(logger, f"[INFO] Started detecting unresponsive destinations")

    # Get local networks from the configuration
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    dead_connections = get_dead_connections_from_database()

    log_info(logger, f"[INFO] Found {len(dead_connections)} potential dead connections")

    for row in dead_connections:
        src_ip = row[0]
        dst_ip = row[1]
        dst_port = row[2]
        protocol = row[5]
        row_tags = row[6]  # Existing tags for the flow

        # Skip if src_ip is not in LOCAL_NETWORKS
        if not is_ip_in_range(src_ip, LOCAL_NETWORKS):
            continue

        alert_id = f"{src_ip}_{dst_ip}_{protocol}_{dst_port}_DeadConnection"
        
        message = (f"Dead Connection Detected:\n"
                    f"Source: {src_ip}\n"
                    f"Destination: {dst_ip}:{dst_port}\n"
                    f"Protocol: {protocol}\n")
        
        log_info(logger, f"[INFO] Dead connection detected: {src_ip}->{dst_ip}:{dst_port} {protocol}")
        
        # Add a Tag to the matching row using update_tag
        if not update_tag_to_allflows("allflows", "DeadConnectionDetection;", src_ip, dst_ip, dst_port):
            log_error(logger, f"[ERROR] Failed to add tag for flow: {src_ip} -> {dst_ip}:{dst_port}")


        handle_alert(
            config_dict,
            "DeadConnectionDetection",
            message,
            src_ip,
            row,
            "Dead Connection Detected",
            dst_ip,
            dst_port,
            alert_id
        )

    log_info(logger, f"[INFO] Finished detecting unresponsive destinations")

def detect_reputation_flows(rows, config_dict, reputation_data):
    """
    Detect flows where a local IP communicates with an IP on the reputation list.

    Args:
        rows: List of flow records.
        config_dict: Dictionary containing configuration settings.
        reputation_data: Preprocessed reputation list data.
    """
    logger = logging.getLogger(__name__)
    log_info(logger, f"[INFO] Started detecting reputationlist destinations")
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

            handle_alert(
                config_dict,
                "ReputationListDetection",
                message,
                src_ip,
                row,
                "Flow involves an IP on the reputation list",
                dst_ip,
                match_network,
                alert_id
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
    log_info(logger, f"[INFO] Started detecting VPN protocol usage")
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
    
    # Get ignorelisted VPN servers if configured
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

        handle_alert(
            config_dict,
            "VpnTrafficDetection",
            message,
            src_ip,
            row,
            "Potential VPN Traffic Detected",
            dst_ip,
            f"Port:{dst_port} Proto:{proto_name}",
            alert_id
        )

    log_info(logger, f"[INFO] Finished detecting VPN protocol usage")


def detect_tor_traffic(rows, config_dict):
    """
    Detect traffic to/from known Tor nodes.
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    log_info(logger,"[INFO] Started detecting traffic to tor nodes")

    # Get local networks
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    
    try:
        rows = get_all_tor_nodes()

        tor_nodes = set(row[0] for row in rows)
        
        for row in rows:
            src_ip, dst_ip, src_port, dst_port, protocol, *_ = row
            
            # Check if source is local and destination is Tor node
            is_src_local = is_ip_in_range(src_ip, LOCAL_NETWORKS)
            
            if is_src_local and dst_ip in tor_nodes:
                alert_id = f"{src_ip}_{dst_ip}_{protocol}_{dst_port}_TorTraffic"
                message = (f"Tor Traffic Detected:\n"
                          f"Local IP: {src_ip}\n"
                          f"Tor Node: {dst_ip}:{dst_port}\n")
                
                log_info(logger, f"[INFO] Tor traffic detected: {src_ip} -> {dst_ip}:{dst_port}")

                handle_alert(
                    config_dict,
                    "TorFlowDetection",
                    message,
                    src_ip,
                    row,
                    "Tor Traffic Detected",
                    dst_ip,
                    f"Tor Exit Node",
                    alert_id
                )
                    
    except Exception as e:
        log_error(logger, f"[ERROR] Error in detect_tor_traffic: {e}")

    log_info(logger,"[INFO] Finished detecting traffic to tor nodes")



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
    log_info(logger,"[INFO] Started detecting high risk ports")
    # Get high-risk ports from config
    high_risk_ports = set(
        int(port.strip()) 
        for port in config_dict.get("HighRiskPorts", "135,137,138,139,445,25,587,22,23,3389").split(",")
        if port.strip()
    )
    
    # Get local networks
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    
    # Get ignorelisted destinations if configured
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
            
            handle_alert(
                config_dict,
                "HighRiskPortDetection",
                message,
                src_ip,
                row,
                "High-Risk Port Traffic Detected",
                dst_ip,
                f"Port:{dst_port} ({service_name})",
                alert_id
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
    log_info(logger, "[INFO] Started one source to many destinations detection")

    # Get configuration parameters
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    dest_threshold = int(config_dict.get("MaxUniqueDestinations", "30"))

    # Track destinations per source IP
    source_stats = {}

    # First pass: Count unique destinations for each source IP
    for row in rows:
        src_ip, dst_ip, *_ = row

        # Only check sources from local networks
        if not is_ip_in_range(src_ip, LOCAL_NETWORKS):
            continue

        # Initialize source IP tracking if not already present
        if src_ip not in source_stats:
            source_stats[src_ip] = {
                'destinations': set(),
                'ports': set(),
                'flow': row
            }

        # Track unique destinations
        source_stats[src_ip]['destinations'].add(dst_ip)

    # Second pass: Check for threshold violations and alert
    for src_ip, stats in source_stats.items():
        unique_dests = len(stats['destinations'])
        flow = stats['flow']

        # Check if the threshold is exceeded
        if unique_dests > dest_threshold:
            alert_id = f"{src_ip}_ManyDestinations"

            message = (f"Host Connecting to Many Destinations:\n"
                       f"Source IP: {src_ip}\n"
                       f"Unique Destinations: {unique_dests}\n")

            log_info(logger, f"[INFO] Excessive destinations detected from {src_ip}: {unique_dests} destinations")

            handle_alert(
                config_dict,
                "ManyDestinationsDetection",
                message,
                src_ip,
                flow,
                "Excessive Unique Destinations",
                "",
                f"{unique_dests} destinations",
                alert_id
            )

    log_info(logger, "[INFO] Finished one source to many destinations detection")



def detect_port_scanning(rows, config_dict):
    """
    Detect local hosts that are connecting to many different ports on the same destination IP,
    which could indicate port scanning activity. Only considers TCP flows (protocol 6).

    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
    """
    logger = logging.getLogger(__name__)
    log_info(logger, "[INFO] Started detecting port scanning activity")

    # Get configuration parameters
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
    port_threshold = int(config_dict.get("MaxPortsPerDestination", "15"))

    # Dictionary to track {(src_ip, dst_ip): {ports}}
    scan_tracking = {}

    # First pass: Iterate through all rows to collect data
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, *_ = row

        # Only process TCP flows (protocol 6)
        if protocol != 6:
            continue

        # Only check flows where src_port > dst_port
        if src_port <= dst_port:
            continue

        # Only check sources from local networks
        if not is_ip_in_range(src_ip, LOCAL_NETWORKS):
            continue

        # Create key for tracking
        flow_key = (src_ip, dst_ip)

        # Initialize tracking for new source-destination pair
        if flow_key not in scan_tracking:
            scan_tracking[flow_key] = {
                'ports': set(),
                'flow': row
            }

        # Track unique destination ports
        scan_tracking[flow_key]['ports'].add(dst_port)

    # Second pass: Iterate through all tracked source-destination pairs
    for (src_ip, dst_ip), stats in scan_tracking.items():
        unique_ports = len(stats['ports'])

        # Check if the port threshold is exceeded
        if unique_ports > port_threshold:
            alert_id = f"{src_ip}_{dst_ip}_PortScan"

            message = (f"Potential Port Scan Detected:\n"
                       f"Source IP: {src_ip}\n"
                       f"Target IP: {dst_ip}\n"
                       f"Unique Ports: {unique_ports}\n")

            log_info(logger, f"[INFO] Port scan detected from {src_ip} to {dst_ip}: {unique_ports} ports")

            handle_alert(
                config_dict,
                "PortScanDetection",
                message,
                src_ip,
                row,
                "Port Scan Detected",
                dst_ip,
                f"Ports:{unique_ports}",
                alert_id
            )

    log_info(logger, "[INFO] Finished detecting port scanning activity")

def detect_high_bandwidth_flows(rows, config_dict):
    """
    Detect flows where the total packet or byte rates for a single src_ip or dst_ip exceed thresholds.

    Args:
        rows: List of flow records.
        config_dict: Dictionary containing configuration settings.
    """
    logger = logging.getLogger(__name__)
    log_info(logger, "[INFO] Started detecting high bandwidth flows")

    # Get thresholds from config_dict
    packet_rate_threshold = int(config_dict.get("MaxPackets", "1000"))  # Default: 1000 packets/sec
    byte_rate_threshold = int(config_dict.get("MaxBytes", "1000000"))  # Default: 1 MB/sec

    # Dictionary to track totals for each src_ip and dst_ip
    traffic_stats = {}
    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))

    # First pass: Aggregate traffic by src_ip and dst_ip
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, *_ = row

        # Initialize stats for src_ip
        if src_ip not in traffic_stats:
            traffic_stats[src_ip] = {"packets": 0, "bytes": 0, "flows": []}
        traffic_stats[src_ip]["packets"] += packets
        traffic_stats[src_ip]["bytes"] += bytes_
        traffic_stats[src_ip]["flows"].append(row)

        # Initialize stats for dst_ip
        if dst_ip not in traffic_stats:
            traffic_stats[dst_ip] = {"packets": 0, "bytes": 0, "flows": []}
        traffic_stats[dst_ip]["packets"] += packets
        traffic_stats[dst_ip]["bytes"] += bytes_
        traffic_stats[dst_ip]["flows"].append(row)

    # Second pass: Check for threshold violations
    for ip, stats in traffic_stats.items():

        if not is_ip_in_range(ip, LOCAL_NETWORKS):
            continue

        total_packets = stats["packets"]
        total_bytes = stats["bytes"]

        # Check if the thresholds are exceeded
        if total_packets > packet_rate_threshold or total_bytes > byte_rate_threshold:
            alert_id = f"{ip}_HighBandwidthFlow"

            message = (f"High Bandwidth Flow Detected:\n"
                       f"IP Address: {ip}\n"
                       f"Total Packets: {total_packets}\n"
                       f"Total Bytes: {total_bytes}\n")

            log_info(logger, f"[INFO] High bandwidth flow detected for {ip}: "
                             f"Packets: {total_packets}, Bytes: {total_bytes}")


            handle_alert(
                config_dict,
                "HighBandwidthFlowDetection",
                message,
                ip,
                row,
                "High Bandwidth Flow Detected",
                "Aggregate",
                f"Packets: {total_packets}, Bytes: {total_bytes}",
                alert_id
            )

    log_info(logger, "[INFO] Finished detecting high bandwidth flows")

def detect_custom_tag(rows, config_dict):
    """
    Detect and alert on rows with tags matching the AlertOnCustomTag configuration.

    Args:
        rows: List of flow records.
        config_dict: Dictionary containing configuration settings.
    """
    logger = logging.getLogger(__name__)
    log_info(logger, "[INFO] Started detecting custom tag alerts")

    # Get the list of tags to alert on
    alert_tags = set(tag.strip() for tag in config_dict.get("AlertOnCustomTagList", "").split(",") if tag.strip())

    if not alert_tags:
        log_warn(logger, "[WARN] No tags specified in AlertOnCustomTag.")
        return

    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))

    log_info(logger, f"[INFO] Alerting on the following tags: {alert_tags}")

    # Iterate through rows to check for matching tags
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes, flow_start, flow_end, times_seen, last_seen, tags = row
        # Ensure the row has a 'tags' column

        if not is_ip_in_range(src_ip, LOCAL_NETWORKS):
            continue

        # Check if any tag in the row matches the alert tags
        row_tags = set(tags.split(";")) if tags else set()
        matching_tags = row_tags.intersection(alert_tags)

        if matching_tags:
            # Generate an alert for the matching tags

            alert_id = f"{src_ip}_{dst_ip}_{protocol}_{dst_port}_CustomTagAlert_{matching_tags}"

            message = (f"Custom Tag Alert Detected:\n"
                       f"Source IP: {src_ip}\n"
                       f"Destination IP: {dst_ip}:{dst_port}\n"
                       f"Protocol: {protocol}\n"
                       f"Matching Tags: {', '.join(matching_tags)}")

            log_info(logger, f"[INFO] Custom tag alert detected: {src_ip} -> {dst_ip}:{dst_port} Tags: {', '.join(matching_tags)} ")

            # Call the reusable function
            handle_alert(
                config_dict,
                "CustomTagAlertDetection",
                message,
                src_ip,
                row,
                "Custom Tag Alert Detected",
                dst_ip,
                f"Tags: {', '.join(matching_tags)}",
                alert_id
            )

    log_info(logger, "[INFO] Finished detecting custom tag alerts")


def handle_alert(config_dict, detection_key, telegram_message, local_ip, original_flow, alert_category, enrichment_1, enrichment_2, alert_id_hash):
    """
    Handle alerting logic based on the configuration level.

    Args:
        config_dict (dict): Configuration dictionary.
        detection_key (str): The key in the configuration dict for the detection type (e.g., "NewOutboundDetection").
        src_ip (str): Source IP address.
        row (list): The flow data row.
        alert_message (str): The alert message to send.
        dst_ip (str): Destination IP address.
        dst_port (int): Destination port.
        alert_id (str): Unique identifier for the alert.

    Returns:
        str: "insert", "update", or None based on the operation performed.
    """
    logger = logging.getLogger(__name__)

    # Get the detection level from the configuration
    detection_level = config_dict.get(detection_key, 0)

    if detection_level >= 2:
        # Send Telegram alert and log to database
        insert_or_update = log_alert_to_db(local_ip, original_flow, alert_category, enrichment_1, enrichment_2, alert_id_hash, False)
                #insert_or_update = log_alert_to_db(local_ip, original_flow, category, enrichment_1, enrichment_2, alert_id, False)
#                           def log_alert_to_db(ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, alert_id_hash, realert=False):
 
        if insert_or_update == "insert":
            send_telegram_message(telegram_message, original_flow)
        elif insert_or_update == "update" and detection_level == 3:
            send_telegram_message(telegram_message, original_flow)

        return insert_or_update

    elif detection_level == 1:
        # Only log to database
        return log_alert_to_db(local_ip, original_flow, alert_category, enrichment_1, enrichment_2, alert_id_hash, False)

    return None