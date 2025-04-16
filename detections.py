import sqlite3
import json
from datetime import datetime
from utils import log_info, is_ip_in_range  # Assuming log_info and is_ip_in_range are defined in utils
from const import CONST_LOCAL_HOSTS, IS_CONTAINER, CONST_LOCALHOSTS_DB, CONST_ALERTS_DB, CONST_ROUTER_IPADDRESS  # Assuming constants are defined in const
from database import connect_to_db, log_alert_to_db  # Import connect_to_db from database.py
from notifications import send_telegram_message  # Import notification functions
import os
import ipaddress

if (IS_CONTAINER):
    LOCAL_HOSTS = os.getenv("LOCAL_HOSTS", CONST_LOCAL_HOSTS)
    LOCAL_HOSTS = [LOCAL_HOSTS] if ',' not in LOCAL_HOSTS else LOCAL_HOSTS.split(',')
    ROUTER_IPADDRESS = os.getenv("LOCAL_HOSTS", CONST_ROUTER_IPADDRESS)
    ROUTER_IPADDRESS = [ROUTER_IPADDRESS] if ',' not in ROUTER_IPADDRESS else ROUTER_IPADDRESS.split(',')

def update_local_hosts(rows, config_dict):
    """Check for new IPs in the provided rows and add them to localhosts.db if necessary."""
    localhosts_conn = connect_to_db(CONST_LOCALHOSTS_DB)

    if localhosts_conn:
        try:
            localhosts_cursor = localhosts_conn.cursor()

            # Ensure the localhosts table exists
            localhosts_cursor.execute("""
                CREATE TABLE IF NOT EXISTS localhosts (
                    ip_address TEXT PRIMARY KEY,
                    first_seen TEXT,
                    original_flow TEXT
                )
            """)

            for row in rows:
                for range in (0, 1):
                    # Assuming the IP address is in the first two columns of the flows table
                    ip_address = row[range]  # Adjust index based on your table schema

                    # Check if the IP is within the allowed ranges
                    if is_ip_in_range(ip_address, LOCAL_HOSTS):
                        # Check if the IP already exists in localhosts.db
                        localhosts_cursor.execute("SELECT * FROM localhosts WHERE ip_address = ?", (ip_address,))
                        if not localhosts_cursor.fetchone():
                            # Add the new IP to localhosts.db
                            first_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            original_flow = json.dumps(row)  # Encode the original flow as JSON
                            localhosts_cursor.execute(
                                "INSERT INTO localhosts (ip_address, first_seen, original_flow) VALUES (?, ?, ?)",
                                (ip_address, first_seen, original_flow)
                            )

                            log_info(None, f"[INFO] Added new IP to localhosts.db: {ip_address}")

                            # Handle alerts and notifications based on NewHostsDetection config
                            if config_dict.get("NewHostsDetection") == 2:
                                # Send a Telegram message and log the alert
                                message = f"New Host Detected: {ip_address}\nFlow: {original_flow}"
                                send_telegram_message(message)
                                log_alert_to_db(ip_address, row, "New Host Detected",f"{ip_address}_NewHostsDetection",False)
                            elif config_dict.get("NewHostsDetection") == 1:
                                # Only log the alert
                                log_alert_to_db(ip_address, row, "New Host Detected",f"{ip_address}_NewHostsDetection",False)

            # Commit changes to localhosts.db
            localhosts_conn.commit()

        except sqlite3.Error as e:
            log_info(None, f"[ERROR] Error updating {CONST_LOCALHOSTS_DB}: {e}")
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

    alerts_conn = connect_to_db(CONST_ALERTS_DB)
    if not alerts_conn:
        log_info(None, "[ERROR] Unable to connect to alerts database")
        return

    try:
        alerts_cursor = alerts_conn.cursor()

        for row in rows:
            src_ip, dst_ip, src_port, dst_port, protocol = row[0:5]
            
            # Changed from LOCAL_NETWORKS to LOCAL_HOSTS
            is_src_local = is_ip_in_range(src_ip, LOCAL_HOSTS)
            
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
                    
                    log_info(None, f"[INFO] {message}")
                    # Log alert based on configuration level
                    if config_dict.get("NewOutboundDetection") == 2:
                        # Send Telegram alert and log to database
                        send_telegram_message(message)
                        log_alert_to_db(src_ip, row, "New outbound connection detected", 
                                      alert_id, False)

                    elif config_dict.get("NewOutboundDetection") == 1:
                        # Only log to database
                        log_alert_to_db(src_ip, row, "New outbound connection detected", 
                                      alert_id, False)


    except Exception as e:
        log_info(None, f"[ERROR] Error in detect_new_outbound_connections: {e}")
    finally:
        alerts_conn.close()


def router_flows_detection(rows, config_dict):
    """
    Detect and handle flows involving a router IP address.
    """
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, *_ = row

        # Determine if the flow involves a router IP address
        router_ip_seen = None
        router_port = None
        for router_ip in ROUTER_IPADDRESS:
            if ipaddress.ip_address(src_ip) in ipaddress.ip_network(router_ip):
                router_ip_seen = src_ip
                router_port = src_port
                break
            elif ipaddress.ip_address(dst_ip) in ipaddress.ip_network(router_ip):
                router_ip_seen = dst_ip
                router_port = dst_port
                break

        if router_ip_seen:
            original_flow = json.dumps(row)

            log_info(None, f"[INFO] Flow involves a router IP address: {row}")

            if config_dict.get("RouterFlowsDetection") == 2:
                message = f"Flow involves a router IP address: {router_ip_seen}\nFlow: {original_flow}"
                send_telegram_message(message)
                log_alert_to_db(router_ip_seen, row, "Flow involves a router IP address",
                                f"{router_ip_seen}_{src_ip}_{dst_ip}_{protocol}_{router_port}_RouterFlowsDetection", False)
            elif config_dict.get("RouterFlowsDetection") == 1:
                log_alert_to_db(router_ip_seen, row, "Flow involves a router IP address",
                                f"{router_ip_seen}_{src_ip}_{dst_ip}_{protocol}_{router_port}_RouterFlowsDetection", False)





def local_flows_detection(rows, config_dict):
    """
    Detect and handle flows where both src_ip and dst_ip are in LOCAL_HOSTS,
    excluding any flows involving the ROUTER_IPADDRESS array.
    """
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, *_ = row

        # Determine if both src_ip and dst_ip are in LOCAL_HOSTS
        is_src_local = any(ipaddress.ip_address(src_ip) in ipaddress.ip_network(net) for net in LOCAL_HOSTS)
        is_dst_local = any(ipaddress.ip_address(dst_ip) in ipaddress.ip_network(net) for net in LOCAL_HOSTS)

        # Exclude flows involving the ROUTER_IPADDRESS array
        involves_router = any(
            ipaddress.ip_address(src_ip) in ipaddress.ip_network(router_ip) or
            ipaddress.ip_address(dst_ip) in ipaddress.ip_network(router_ip)
            for router_ip in ROUTER_IPADDRESS
        )

        if is_src_local and is_dst_local and not involves_router:
            original_flow = json.dumps(row)

            log_info(None, f"[INFO] Flow involves two local hosts (excluding router): {row}")

            if config_dict.get("LocalFlowsDetection") == 2:
                message = f"Flow involves two local hosts: {src_ip} and {dst_ip}\nFlow: {original_flow}"
                send_telegram_message(message)
                log_alert_to_db(src_ip, row, "Flow involves two local hosts",
                                f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_LocalFlowsDetection", False)
            elif config_dict.get("LocalFlowsDetection") == 1:
                log_alert_to_db(src_ip, row, "Flow involves two local hosts",
                                f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_LocalFlowsDetection", False)


def foreign_flows_detection(rows, config_dict):
    """
    Detect and handle flows where neither src_ip nor dst_ip is in LOCAL_HOSTS.
    """
    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, *_ = row

        # Determine if neither src_ip nor dst_ip is in LOCAL_HOSTS
        is_src_local = any(ipaddress.ip_address(src_ip) in ipaddress.ip_network(net) for net in LOCAL_HOSTS)
        is_dst_local = any(ipaddress.ip_address(dst_ip) in ipaddress.ip_network(net) for net in LOCAL_HOSTS)

        if not is_src_local and not is_dst_local:
            original_flow = json.dumps(row)

            log_info(None, f"[INFO] Flow involves two foreign hosts: {row}")

            if config_dict.get("ForeignFlowsDetection") == 2:
                message = f"Flow involves two foreign hosts: {src_ip} and {dst_ip}\nFlow: {original_flow}"
                send_telegram_message(message)
                log_alert_to_db(src_ip, row, "Flow involves two foreign hosts",
                                f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_ForeignFlowsDetection", False)
            elif config_dict.get("ForeignFlowsDetection") == 1:
                log_alert_to_db(src_ip, row, "Flow involves two foreign hosts",
                                f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_ForeignFlowsDetection", False)


def detect_geolocation_flows(rows, config_dict, geolocation_data):
    """
    Detect and handle flows where either src_ip or dst_ip is located in a banned country
    using in-memory geolocation data.

    Args:
        rows: List of flow records.
        config_dict: Dictionary containing configuration settings, including BannedCountryList.
        geolocation_data: List of tuples containing (network, country_name).
    """
    # Get the list of banned countries from the config_dict
    banned_countries = config_dict.get("BannedCountryList", "")
    banned_countries = [country.strip() for country in banned_countries.split(",") if country.strip()]

    if not banned_countries:
        log_info(None, "[INFO] No banned countries specified in BannedCountryList. Skipping geolocation detection.")
        return

    for row in rows:
        src_ip, dst_ip, src_port, dst_port, protocol, *_ = row

        # Check if src_ip or dst_ip is in a banned country
        src_country = None
        dst_country = None

        for network, country_name in geolocation_data:
            if country_name in banned_countries:
                if ipaddress.ip_address(src_ip) in ipaddress.ip_network(network):
                    src_country = country_name
                if ipaddress.ip_address(dst_ip) in ipaddress.ip_network(network):
                    dst_country = country_name

            # Break early if both IPs are already matched
            if src_country or dst_country:
                break

        if src_country or dst_country:
            original_flow = json.dumps(row)
            log_info(None, f"[INFO] Flow involves an IP located in a banned country: {row}")

            # Prepare alert message
            message = f"Flow involves an IP located in a banned country:\n" \
                      f"Source IP: {src_ip} ({src_country or 'N/A'})\n" \
                      f"Destination IP: {dst_ip} ({dst_country or 'N/A'})\n" \
                      f"Flow: {original_flow}"

            # Send alert based on configuration
            if config_dict.get("GeolocationFlowsDetection") == 2:
                # Send Telegram alert and log to database
                send_telegram_message(message)
                log_alert_to_db(src_ip, row, "Flow involves an IP in a banned country",
                                f"{src_ip}_{dst_ip}_{protocol}_BannedCountryDetection", False)
            elif config_dict.get("GeolocationFlowsDetection") == 1:
                # Only log to database
                log_alert_to_db(src_ip, row, "Flow involves an IP in a banned country",
                                f"{src_ip}_{dst_ip}_{protocol}_BannedCountryDetection", False)