import sqlite3
import json
from datetime import datetime
from utils import log_info, is_ip_in_range  # Assuming log_info and is_ip_in_range are defined in utils
from const import CONST_LOCAL_HOSTS, IS_CONTAINER, CONST_LOCALHOSTS_DB, CONST_ALERTS_DB  # Assuming constants are defined in const
from database import connect_to_db, log_alert_to_db  # Import connect_to_db from database.py
from notifications import send_telegram_message  # Import notification functions
import os

if (IS_CONTAINER):
    LOCAL_HOSTS = os.getenv("LOCAL_HOSTS", CONST_LOCAL_HOSTS)
    LOCAL_HOSTS = [LOCAL_HOSTS] if ',' not in LOCAL_HOSTS else LOCAL_HOSTS.split(',')


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
                    WHERE alert_id = ?
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
                        log_alert_to_db(None, row, "New outbound connection detected", 
                                      alert_id, False)

                    elif config_dict.get("NewOutboundDetection") == 1:
                        # Only log to database
                        log_alert_to_db(None, row, "New outbound connection detected", 
                                      alert_id, False)


    except Exception as e:
        log_info(None, f"[ERROR] Error in detect_new_outbound_connections: {e}")
    finally:
        alerts_conn.close()