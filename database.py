import sqlite3
import logging
from utils import log_info, log_error, get_machine_unique_identifier  # Assuming log_info is defined in utils
from const import CONST_INSTALL_CONFIGS, CONST_SITE, IS_CONTAINER, CONST_CONSOLIDATED_DB
import ipaddress
import os
from datetime import datetime
import json
import traceback
import sys
import importlib
from utils import is_ip_in_range
  # Create a logger for this module

def delete_database(db_path):
    """Deletes the specified SQLite database file if it exists."""
    logger = logging.getLogger(__name__)
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
            log_info(logger, f"[INFO] Deleted: {db_path}")
        else:
            log_info(logger, f"[INFO] {db_path} does not exist, skipping deletion.")
    except Exception as e:
        log_error(logger,f"[ERROR] Error deleting {db_path}: {e}")

def connect_to_db(DB_NAME,table="unknown"):
    """Establish a connection to the specified database."""
    logger = logging.getLogger(__name__)

    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("PRAGMA busy_timeout = 5000")
        #log_info(logger, f"[INFO] Connected to database: {DB_NAME} table {table}")
        return conn
    except sqlite3.Error as e:
        log_error(logger,f"[ERROR] Error connecting to database {DB_NAME} table {table}: {e}")
        return None
    
def disconnect_from_db(conn):
    """
    Safely close the database connection.

    Args:
        conn: The SQLite connection object to close.
    """
    logger = logging.getLogger(__name__)
    try:
        if conn:
            conn.close()
            #log_info(logger, "[INFO] Database connection closed successfully.")
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error closing database connection: {e}")
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while closing database connection: {e}")

def create_table(db_name, create_table_sql, table="unknown"):
    """Initializes a SQLite database with the specified schema."""
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(db_name)
        if not conn:
            log_error(logger,f"[ERROR] Unable to connect to {db_name}")
            return

        cursor = conn.cursor()
        cursor.execute(create_table_sql)
        conn.commit()
        log_info(logger, f"[INFO] {db_name} table {table} initialized successfully.")
        disconnect_from_db(conn)
    except sqlite3.Error as e:
        log_error(logger,f"[ERROR] Error initializing {db_name}: {e}")

def update_allflows(rows, config_dict):
    """Update allflows.db with the rows from newflows.db."""
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_CONSOLIDATED_DB, "allflows")
    total_packets = 0
    total_bytes = 0

    if conn:
        try:
            allflows_cursor = conn.cursor()
            for row in rows:
                src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, last_seen, times_seen, tags = row
                total_packets += packets
                total_bytes += bytes_

                # Use datetime('now', 'localtime') for the current timestamp
                allflows_cursor.execute("""
                    INSERT INTO allflows (
                        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes, flow_start, flow_end, times_seen, last_seen, tags
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now', 'localtime'), ?)
                    ON CONFLICT(src_ip, dst_ip, src_port, dst_port, protocol)
                    DO UPDATE SET
                        packets = packets + excluded.packets,
                        bytes = bytes + excluded.bytes,
                        flow_end = excluded.flow_end,
                        times_seen = times_seen + 1,
                        last_seen = datetime('now', 'localtime'),
                        tags = excluded.tags
                """, (src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, tags))
            conn.commit()
            log_info(logger, f"[INFO] Updated {CONST_CONSOLIDATED_DB} with {len(rows)} rows.")
        except sqlite3.Error as e:
            log_error(logger, f"[ERROR] Error updating {CONST_CONSOLIDATED_DB}: {e}")
        finally:
            disconnect_from_db(conn)
        log_info(logger, f"[INFO] Latest collection results packets: {total_packets} for bytes {total_bytes}")

    disconnect_from_db(conn)

def update_traffic_stats(rows, config_dict):
    """
    Update the trafficstats table with hourly traffic statistics for each source IP address.

    Args:
        rows (list): List of tuples containing flow data:
                     (src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, last_seen, times_seen, tags)
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_CONSOLIDATED_DB, "trafficstats")

    if not conn:
        log_error(logger, "[ERROR] Unable to connect to allflows database.")
        return

    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))

    try:
        cursor = conn.cursor()

        # Process each row and update the trafficstats table
        for row in rows:
            src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, last_seen, times_seen, tags = row

            if not is_ip_in_range(src_ip, LOCAL_NETWORKS):
                continue

            # Format the timestamp as yyyy-mm-dd-hh
            timestamp = datetime.now().strftime('%Y-%m-%d:%H')

            # Insert or update the traffic statistics for the source IP and timestamp
            cursor.execute("""
                INSERT INTO trafficstats (ip_address, timestamp, total_packets, total_bytes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ip_address, timestamp)
                DO UPDATE SET
                    total_packets = total_packets + excluded.total_packets,
                    total_bytes = total_bytes + excluded.total_bytes
            """, (src_ip, timestamp, packets, bytes_))

        conn.commit()
        log_info(logger, f"[INFO] Updated traffic statistics for {len(rows)} rows.")
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error updating traffic statistics: {e}")
    finally:
        disconnect_from_db(conn)
    disconnect_from_db(conn)

def delete_all_records(db_name, table_name='flows'):
    """Delete all records from the specified database and table."""
    logger = logging.getLogger(__name__)
    conn = connect_to_db(db_name, table_name)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {table_name}")
            conn.commit()
            log_info(logger, f"[INFO] All records deleted from {db_name}.{table_name}")
        except sqlite3.Error as e:
            log_error(logger,f"[ERROR] Error deleting records from {db_name}: {e}")
        finally:
            disconnect_from_db(conn)
    disconnect_from_db(conn)

def init_configurations_from_sitepy():
    """
    Inserts default configurations from file in /database into the CONST_CONSOLIDATED_DB database and returns a configuration dictionary.

    Returns:
        dict: A dictionary containing the configuration settings.
    """
    logger = logging.getLogger(__name__)
    config_dict = {}

    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "configuration")
        if not conn:
            log_error(logger,"[ERROR] Unable to connect to configuration database")
            return config_dict

        if IS_CONTAINER:
            SITE = os.getenv("SITE", CONST_SITE)

        # Dynamically import the site-specific configuration module
        config = importlib.import_module(f"{SITE}")
        log_info(logger, f"[INFO] Reading configuration from /database/{SITE}.py")

        cursor = conn.cursor()

        # Insert default configurations into the database
        for key, value in config.CONST_DEFAULT_CONFIGS:
            log_info(logger, f"[INFO] Inserting configuration: {key} = {value}")
            cursor.execute("""
                INSERT OR IGNORE INTO configuration (key, value)
                VALUES (?, ?)
            """, (key, value))
        conn.commit()

        # Fetch all configurations into a dictionary
        cursor.execute("SELECT key, value FROM configuration")
        config_dict = dict(cursor.fetchall())

        log_info(logger, f"[INFO] Default configurations initialized successfully.")
        disconnect_from_db(conn)
    except sqlite3.Error as e:
        log_error(logger,f"[ERROR] Error initializing default configurations: {e}")
    except Exception as e:
        log_error(logger,f"[ERROR] Unexpected error: {e}")
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)
    
    disconnect_from_db(conn)
    return config_dict


def init_configurations_from_variable():
    """
    Inserts default configurations into the CONST_CONSOLIDATED_DB database and returns a configuration dictionary.

    Returns:
        dict: A dictionary containing the configuration settings.
    """
    logger = logging.getLogger(__name__)
    config_dict = {}

    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "configuration")
        if not conn:
            log_error(logger,"[ERROR] Unable to connect to configuration database")
            return config_dict

        cursor = conn.cursor()

        # Insert default configurations into the database
        for key, value in CONST_INSTALL_CONFIGS:
            cursor.execute("""
                INSERT OR IGNORE INTO configuration (key, value)
                VALUES (?, ?)
            """, (key, value))
        conn.commit()

        # Fetch all configurations into a dictionary
        cursor.execute("SELECT key, value FROM configuration")
        config_dict = dict(cursor.fetchall())

        log_info(logger, f"[INFO] Default configurations initialized successfully.")
        disconnect_from_db(conn)
    except sqlite3.Error as e:
        log_error(logger,f"[ERROR] Error initializing default configurations: {e}")
    except Exception as e:
        log_error(logger,f"[ERROR] Unexpected error: {e}")
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)
    disconnect_from_db(conn)
    return config_dict

def get_config_settings():
    """Read configuration settings from the configuration database into a dictionary."""
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "configuration")
        if not conn:
            log_error(logger,"[ERROR] Unable to connect to configuration database")
            return None

        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM configuration")
        config_dict = dict(cursor.fetchall())
        log_info(logger, f"[INFO] Successfully loaded {len(config_dict)} configuration settings")
        return config_dict
    except sqlite3.Error as e:
        log_error(logger,f"[ERROR] Error reading configuration database: {e}")
        disconnect_from_db(conn)
        return None
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)


def log_alert_to_db(ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, alert_id_hash, realert=False):
    """Logs an alert to the alerts.db SQLite database."""
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alerts (id, ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, times_seen, first_seen, last_seen, acknowledged)
            VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now', 'localtime'), datetime('now', 'localtime'), 0)
            ON CONFLICT(id)
            DO UPDATE SET
                times_seen = times_seen + 1,
                last_seen = datetime('now', 'localtime')
        """, (alert_id_hash, ip_address, json.dumps(flow), category, alert_enrichment_1, alert_enrichment_2))
        conn.commit()
        log_info(logger, f"[INFO] Alert logged to database for IP: {ip_address}, Category: {category}")
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error logging alert to database: {e}")
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_custom_tags():
    """
    Retrieve active entries from the customtags table in the whitelist database.

    Returns:
        list: List of tuples containing (tag_id, src_ip, dst_ip, dst_port, protocol, tag_name)
              Returns None if there's an error.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "customtags")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to whitelist database")
            return None

        cursor = conn.cursor()
        cursor.execute("""
            SELECT tag_id, src_ip, dst_ip, dst_port, protocol
            FROM customtags
            WHERE enabled = 1
        """)
        customtags = cursor.fetchall()

        log_info(logger, f"[INFO] Retrieved {len(customtags)} active custom tag entries")

        return customtags

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error retrieving custom tag entries: {e}")
        return None
    finally:
        if conn:
            disconnect_from_db(conn)


def get_whitelist():
    """
    Retrieve active entries from the whitelist database.
    
    Returns:
        list: List of tuples containing (alert_id, category, insert_date)
              Returns None if there's an error
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "whitelist")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to whitelist database")
            return None

        cursor = conn.cursor()
        cursor.execute("""
            SELECT whitelist_id, whitelist_src_ip, whitelist_dst_ip, whitelist_dst_port, whitelist_protocol
            FROM whitelist 
            WHERE whitelist_enabled = 1
        """)
        whitelist = cursor.fetchall()

        log_info(logger, f"[INFO] Retrieved {len(whitelist)} active whitelist entries")
        
        return whitelist

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error retrieving whitelist entries: {e}")
        return None
    finally:
        if conn:
            disconnect_from_db(conn)


def get_row_count(db_name, table_name):
    """
    Get the total number of rows in a specified database table.
    
    Args:
        db_name (str): The database file path
        table_name (str): The table name to count rows from
        
    Returns:
        int: Number of rows in the table, or -1 if there's an error
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(db_name, table_name)
        if not conn:
            log_error(logger, f"[ERROR] Unable to connect to database {db_name}")
            return -1

        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
    
        return count

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error counting rows in {db_name}.{table_name}: {e}")
        return -1
    finally:
        if 'conn' in locals():
            disconnect_from_db(conn)

def get_alerts_summary():
    """
    Get a summary of alerts by category from alerts.db.
    Prints total count and breakdown by category.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database")
            return

        cursor = conn.cursor()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM alerts")
        total_count = cursor.fetchone()[0]
        
        # Get counts by category
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM alerts 
            GROUP BY category 
            ORDER BY count DESC
        """)
        categories = cursor.fetchall()
        
        # Log the summary
        log_info(logger, f"[INFO] Total alerts: {total_count}")
        log_info(logger, "[INFO] Breakdown by category:")
        for category, count in categories:
            percentage = (count / total_count * 100) if total_count > 0 else 0
            log_info(logger, f"[INFO]   {category}: {count} ({percentage:.1f}%)")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error getting alerts summary: {e}")
    finally:
        if 'conn' in locals():
            disconnect_from_db(conn)

def import_custom_tags(config_dict):
    """
    Import custom tag entries into the customtags table in the whitelist database.

    Args:
        config_dict (dict): Configuration dictionary containing tag entries.
                            Expected format: "TagEntries" -> JSON string of list of tuples
                            Each tuple: (tag_id, src_ip, dst_ip, dst_port, protocol, tag_name)
    """
    logger = logging.getLogger(__name__)
    tag_entries_json = config_dict.get("TagEntries", "[]")
    tag_entries = json.loads(tag_entries_json)

    if not tag_entries:
        log_info(logger, "[INFO] No custom tag entries found in config_dict.")
        return

    conn = connect_to_db(CONST_CONSOLIDATED_DB, "customtags")
    if not conn:
        log_error(logger, "[ERROR] Unable to connect to whitelist database.")
        return

    try:
        cursor = conn.cursor()

        # Insert custom tag entries into the database if they don't already exist
        for entry in tag_entries:
            tag_id, src_ip, dst_ip, dst_port, protocol = entry

            # Check if the custom tag entry already exists
            cursor.execute("""
                SELECT COUNT(*) FROM customtags
                WHERE tag_id = ? AND src_ip = ? AND dst_ip = ? AND dst_port = ? AND protocol = ?
            """, (tag_id, src_ip, dst_ip, dst_port, protocol))
            exists = cursor.fetchone()[0]

            if exists:
                log_info(logger, f"[INFO] Custom tag entry already exists: {entry}")
                continue

            # Insert the new custom tag entry
            cursor.execute("""
                INSERT INTO customtags (
                    tag_id, src_ip, dst_ip, dst_port, protocol, tag_name, enabled, added, insert_date
                ) VALUES (?, ?, ?, ?, ?, "", 1, datetime('now', 'localtime'), datetime('now', 'localtime'))
            """, (tag_id, src_ip, dst_ip, dst_port, protocol))

        conn.commit()
        log_info(logger, f"[INFO] Imported {len(tag_entries)} custom tag entries into the database.")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error importing custom tag entries: {e}")
    finally:
        disconnect_from_db(conn)

def import_whitelists(config_dict):
    """
    Import whitelist entries into the whitelist database from a config_dict entry.

    Args:
        config_dict (dict): Configuration dictionary containing whitelist entries.
                            Expected format: "WhitelistEntries" -> JSON string of list of tuples
                            Each tuple: (src_ip, dst_ip, dst_port, protocol)
    """
    logger = logging.getLogger(__name__)
    whitelist_entries_json = config_dict.get("WhitelistEntries", "[]")
    if not whitelist_entries_json:
        log_info(logger, "[INFO] No whitelist entries found in config_dict.")
        return
    #print(f"[INFO] whitelist_entries_json: {whitelist_entries_json}")
    whitelist_entries = json.loads(whitelist_entries_json)

    if not whitelist_entries:
        log_info(logger, "[INFO] No whitelist entries found in config_dict.")
        return

    conn = connect_to_db(CONST_CONSOLIDATED_DB, "whitelist")
    if not conn:
        log_error(logger, "[ERROR] Unable to connect to whitelist database.")
        return

    try:
        cursor = conn.cursor()

        # Insert whitelist entries into the database if they don't already exist
        for entry in whitelist_entries:
            whitelist_id, src_ip, dst_ip, dst_port, protocol = entry

            # Check if the whitelist entry already exists
            cursor.execute("""
                SELECT COUNT(*) FROM whitelist
                WHERE whitelist_id = ? AND whitelist_src_ip = ? AND whitelist_dst_ip = ? AND whitelist_dst_port = ? AND whitelist_protocol = ?
            """, (whitelist_id, src_ip, dst_ip, dst_port, protocol))
            exists = cursor.fetchone()[0]

            if exists:
                log_info(logger, f"[INFO] Whitelist entry already exists: {entry}")
                continue

            # Insert the new whitelist entry
            cursor.execute("""
                INSERT INTO whitelist (
                    whitelist_id, whitelist_src_ip, whitelist_dst_ip, whitelist_dst_port, whitelist_protocol, whitelist_enabled, whitelist_added, whitelist_insert_date
                ) VALUES (?, ?, ?, ?, ?, 1, datetime('now', 'localtime'), datetime('now', 'localtime'))
            """, (whitelist_id, src_ip, dst_ip, dst_port, protocol))

        conn.commit()
        log_info(logger, f"[INFO] Imported {len(whitelist_entries)} whitelist entries into the database.")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error importing whitelist entries: {e}")
    finally:
        disconnect_from_db(conn)

def update_tag_to_allflows(table_name, tag, src_ip, dst_ip, dst_port):
    """
    Update the tag for a specific row in the database.

    Args:
        db_name (str): The database name.
        table_name (str): The table name.
        tag (str): The tag to add.
        src_ip (str): The source IP address.
        dst_ip (str): The destination IP address.
        dst_port (int): The destination port.

    Returns:
        bool: True if the update was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_CONSOLIDATED_DB, table_name)
    if not conn:
        log_error(logger, f"[ERROR] Unable to connect to database: {CONST_CONSOLIDATED_DB}")
        return False

    try:
        cursor = conn.cursor()

        # Retrieve the existing tag
        cursor.execute(f"""
            SELECT tags FROM {table_name}
            WHERE src_ip = ? AND dst_ip = ? AND dst_port = ?
            AND tags not like '%DeadConnectionDetection%'
        """, (src_ip, dst_ip, dst_port))
        result = cursor.fetchone()

        existing_tag = result[0] if result and result[0] else ""  # Get the existing tag or default to an empty string

        # Append the new tag to the existing tag
        updated_tag = f"{existing_tag}{tag}" if existing_tag else tag

        # Update the tag in the database
        cursor.execute(f"""
            UPDATE {table_name}
            SET tags = ?
            WHERE src_ip = ? AND dst_ip = ? AND dst_port = ?
        """, (updated_tag, src_ip, dst_ip, dst_port))
        conn.commit()

        log_info(logger, f"[INFO] Tag '{tag}' added to flow: {src_ip} -> {dst_ip}:{dst_port}. Updated tag: '{updated_tag}'")
        return True
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Failed to add tag to flow: {e}")
        return False
    finally:
        disconnect_from_db(conn)

def get_localhosts():
    """
    Retrieve all local hosts from the localhosts database.

    Returns:
        set: A set of IP addresses from the localhosts database, or an empty set if an error occurs.
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")

    if not conn:
        log_error(logger, "[ERROR] Unable to connect to localhosts database")
        return set()

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ip_address FROM localhosts")
        localhosts = set(row[0] for row in cursor.fetchall())
        log_info(logger, f"[INFO] Retrieved {len(localhosts)} local hosts from the database")
        return localhosts
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Failed to retrieve local hosts: {e}")
        return set()
    finally:
        disconnect_from_db(conn)

def update_localhosts(ip_address, mac_address=None, mac_vendor=None, dhcp_hostname=None, dns_hostname=None, os_fingerprint=None, lease_hostname=None, lease_hwaddr=None, lease_clientid=None):
    """
    Update or insert a record in the localhosts database for a given IP address.

    Args:
        ip_address (str): The IP address to update or insert.
        first_seen (str): The first seen timestamp in ISO format (optional).
        original_flow (str): The original flow information as a JSON string (optional).
        mac_address (str): The MAC address associated with the IP address (optional).
        mac_vendor (str): The vendor of the MAC address (optional).
        dhcp_hostname (str): The hostname from DHCP (optional).
        dns_hostname (str): The hostname from DNS (optional).
        os_fingerprint (str): The operating system fingerprint (optional).

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")

    if not conn:
        log_error(logger, "[ERROR] Unable to connect to localhosts database")
        return False

    try:
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE localhosts
            SET mac_address = COALESCE(?, mac_address),
                mac_vendor = COALESCE(?, mac_vendor),
                dhcp_hostname = COALESCE(?, dhcp_hostname),
                dns_hostname = COALESCE(?, dns_hostname),
                os_fingerprint = COALESCE(?, os_fingerprint),
                lease_hwaddr = COALESCE(?, lease_hwaddr),
                lease_clientid = COALESCE(?, lease_clientid),
                lease_hostname = COALESCE(?, lease_hostname)
            WHERE ip_address = ?
        """, (mac_address, mac_vendor, dhcp_hostname, dns_hostname, os_fingerprint, lease_hwaddr, lease_clientid, lease_hostname, ip_address))
        log_info(logger, f"[INFO] Discovery updated record for IP: {ip_address}")

        conn.commit()
        return True
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Failed to update localhosts database: {e}")
        return False
    finally:
        disconnect_from_db(conn)


def collect_database_counts():
    """
    Collects counts from the alerts, localhosts, and whitelist tables.

    Returns:
        dict: A dictionary containing the counts for acknowledged alerts, unacknowledged alerts,
              total alerts, localhosts entries, and whitelist entries.
    """
    logger = logging.getLogger(__name__)
    counts = {
        "acknowledged_alerts": 0,
        "unacknowledged_alerts": 0,
        "total_alerts": 0,
        "unacknowledged_localhosts_count": 0,
        "acknowledged_localhosts_count": 0,
        "total_localhosts_count": 0,
        "whitelist_count": 0,

    }

    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if conn:
            cursor = conn.cursor()
            # Count acknowledged alerts
            cursor.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 1")
            counts["acknowledged_alerts"] = cursor.fetchone()[0]

            # Count unacknowledged alerts
            cursor.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 0")
            counts["unacknowledged_alerts"] = cursor.fetchone()[0]

            # Count total alerts
            cursor.execute("SELECT COUNT(*) FROM alerts")
            counts["total_alerts"] = cursor.fetchone()[0]

            conn.close()
        else:
            log_error(logger, "[ERROR] Unable to connect to alerts database")

        # Connect to the localhosts database
        conn_localhosts = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")
        if conn_localhosts:
            cursor = conn_localhosts.cursor()
            # Count entries in localhosts
            cursor.execute("SELECT COUNT(*) FROM localhosts")
            counts["total_localhosts_count"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM localhosts where acknowledged = 1")
            counts["acknowledged_localhosts_count"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM localhosts WHERE acknowledged = 0")
            counts["unacknowledged_localhosts_count"] = cursor.fetchone()[0]

            conn_localhosts.close()
        else:
            log_error(logger, "[ERROR] Unable to connect to localhosts database")

        # Connect to the whitelist database
        conn_whitelist = connect_to_db(CONST_CONSOLIDATED_DB, "whitelist")
        if conn_whitelist:
            cursor = conn_whitelist.cursor()
            # Count entries in whitelist
            cursor.execute("SELECT COUNT(*) FROM whitelist")
            counts["whitelist_count"] = cursor.fetchone()[0]

            conn_whitelist.close()
        else:
            log_error(logger, "[ERROR] Unable to connect to whitelist database")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error: {e}")
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error: {e}")

    conn_whitelist.close()
    return counts

def store_machine_unique_identifier():
    """
    Generate a unique identifier for the machine and store it in the configuration database
    with the key 'MachineUniqueIdentifier'.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    try:
        # Generate the unique identifier
        unique_id = get_machine_unique_identifier()
        if not unique_id:
            log_error(logger, "[ERROR] Failed to generate machine unique identifier.")
            return False

        # Connect to the configuration database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "configuration")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to configuration database.")
            return False

        cursor = conn.cursor()

        # Insert or update the MachineUniqueIdentifier in the configuration table
        cursor.execute("""
            INSERT INTO configuration (key, value)
            VALUES ('MachineUniqueIdentifier', ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
        """, (unique_id,))

        conn.commit()
        disconnect_from_db(conn)

        log_info(logger, f"[INFO] Machine unique identifier stored successfully: {unique_id}")
        return True

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while storing machine unique identifier: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while storing machine unique identifier: {e}")
        return False

def get_machine_unique_identifier_from_db():
    """
    Retrieve the machine unique identifier from the configuration database.

    Returns:
        str: The machine unique identifier if found, None otherwise.
    """
    logger = logging.getLogger(__name__)
    try:
        # Connect to the configuration database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "configuration")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to configuration database.")
            return None

        cursor = conn.cursor()

        # Query the MachineUniqueIdentifier from the configuration table
        cursor.execute("""
            SELECT value FROM configuration WHERE key = 'MachineUniqueIdentifier'
        """)
        result = cursor.fetchone()

        disconnect_from_db(conn)

        if result:
            #log_info(logger, f"[INFO] Retrieved MachineUniqueIdentifier: {result[0]}")
            return result[0]
        else:
            log_error(logger, "[ERROR] MachineUniqueIdentifier not found in the configuration database.")
            return None

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving machine unique identifier: {e}")
        return None
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving machine unique identifier: {e}")
        return None
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_traffic_stats_for_ip(ip_address):
    """
    Retrieve all traffic statistics for a specific IP address from the trafficstats table.

    Args:
        ip_address (str): The IP address to filter data by.

    Returns:
        list: A list of dictionaries containing all traffic statistics for the specified IP address.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    try:
        # Connect to the consolidated database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "trafficstats")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to trafficstats database.")
            return []

        cursor = conn.cursor()

        # Query to retrieve all data for the specified IP address
        cursor.execute("""
            SELECT ip_address, timestamp, total_packets, total_bytes
            FROM trafficstats
            WHERE ip_address = ?
            ORDER BY timestamp DESC
        """, (ip_address,))

        rows = cursor.fetchall()
        disconnect_from_db(conn)

        # Format the results as a list of dictionaries
        traffic_stats = [{
            "ip_address": row[0],
            "timestamp": row[1],
            "total_packets": row[2],
            "total_bytes": row[3]
        } for row in rows]

        log_info(logger, f"[INFO] Retrieved {len(traffic_stats)} traffic stats entries for IP address {ip_address}.")
        return traffic_stats

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving traffic stats for IP {ip_address}: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving traffic stats for IP {ip_address}: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)
