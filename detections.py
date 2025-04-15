import sqlite3
import json
from datetime import datetime
from utils import log_info  # Assuming log_info is defined in utils
from const import CONST_LOCAL_HOSTS, IS_CONTAINER, CONST_LOCALHOSTS_DB  # Assuming LOCAL_HOSTS is defined in const
from database import connect_to_db, log_alert_to_db  # Import connect_to_db from database.py
from utils import is_ip_in_range
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
                                log_info(None, f"[INFO] Alert sent and logged for IP: {ip_address}")
                            elif config_dict.get("NewHostsDetection") == 1:
                                # Only log the alert
                                log_alert_to_db(ip_address, row, "New Host Detected",f"{ip_address}_NewHostsDetection",False)
                                log_info(None, f"[INFO] Alert logged for IP: {ip_address}")

            # Commit changes to localhosts.db
            localhosts_conn.commit()

        except sqlite3.Error as e:
            log_info(None, f"[ERROR] Error updating {CONST_LOCALHOSTS_DB}: {e}")
        finally:
            localhosts_conn.close()