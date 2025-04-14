import sqlite3
import json
from datetime import datetime
from utils import log_info  # Assuming log_info is defined in utils
from const import CONST_LOCAL_HOSTS, IS_CONTAINER  # Assuming LOCAL_HOSTS is defined in const
from database import connect_to_db  # Import connect_to_db from database.py
from utils import is_ip_in_range
import os


if (IS_CONTAINER):
   LOCAL_HOSTS=os.getenv("LOCAL_HOSTS".split(','), CONST_LOCAL_HOSTS)


def update_local_hosts(rows):
    """Check for new IPs in the provided rows and add them to localhosts.db if necessary."""
    localhosts_conn = connect_to_db("/database/localhosts.db")

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
                            log_info(None, f"Added new IP to localhosts.db: {ip_address}")

            # Commit changes to localhosts.db
            localhosts_conn.commit()

        except sqlite3.Error as e:
            log_info(None, f"Error updating localhosts.db: {e}")
        finally:
            localhosts_conn.close()