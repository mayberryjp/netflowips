import sqlite3
import logging
from utils import log_info, log_error  # Assuming log_info is defined in utils
from const import CONST_SITE, CONST_ALLFLOWS_DB, CONST_CONFIG_DB, CONST_ALERTS_DB, CONST_WHITELIST_DB, IS_CONTAINER, CONST_LOCALHOSTS_DB
import ipaddress
import os
from datetime import datetime
import json
import importlib
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
        logger.error(f"[ERROR] Error deleting {db_path}: {e}")

def connect_to_db(DB_NAME):
    """Establish a connection to the specified database."""
    logger = logging.getLogger(__name__)
    try:
        conn = sqlite3.connect(DB_NAME)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database {DB_NAME}: {e}")
        return None

def create_database(db_name, create_table_sql):
    """Initializes a SQLite database with the specified schema."""
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(db_name)
        if not conn:
            logger.error(f"[ERROR] Unable to connect to {db_name}")
            return

        cursor = conn.cursor()
        cursor.execute(create_table_sql)
        conn.commit()
        log_info(logger, f"[INFO] {db_name} initialized successfully.")
        conn.close()
    except sqlite3.Error as e:
        log_error(logger,f"[ERROR] Error initializing {db_name}: {e}")

def update_allflows(rows, config_dict):
    """Update allflows.db with the rows from newflows.db."""
    logger = logging.getLogger(__name__)
    allflows_conn = connect_to_db(CONST_ALLFLOWS_DB)
    if allflows_conn:
        try:
            allflows_cursor = allflows_conn.cursor()
            for row in rows:
                src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, last_seen, times_seen = row
                now = datetime.utcnow().isoformat()
                allflows_cursor.execute("""
                    INSERT INTO allflows (
                        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes, flow_start, flow_end, times_seen, last_seen, tags
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, "")
                    ON CONFLICT(src_ip, dst_ip, src_port, dst_port, protocol)
                    DO UPDATE SET
                        packets = packets + excluded.packets,
                        bytes = bytes + excluded.bytes,
                        flow_end = excluded.flow_end,
                        times_seen = times_seen + 1,
                        last_seen = excluded.last_seen
                """, (src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, now))
            allflows_conn.commit()
            log_info(logger, f"[INFO] Updated {CONST_ALLFLOWS_DB} with {len(rows)} rows.")
        except sqlite3.Error as e:
            logger.error(f"[ERROR] Error updating {CONST_ALLFLOWS_DB}: {e}")
        finally:
            allflows_conn.close()

def delete_all_records(db_name, table_name='flows'):
    """Delete all records from the specified database and table."""
    logger = logging.getLogger(__name__)
    conn = connect_to_db(db_name)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {table_name}")
            conn.commit()
            log_info(logger, f"[INFO] All records deleted from {db_name}.{table_name}")
        except sqlite3.Error as e:
            logger.error(f"[ERROR] Error deleting records from {db_name}: {e}")
        finally:
            conn.close()

def init_configurations():
    """
    Inserts default configurations into the CONST_CONFIG_DB database and returns a configuration dictionary.

    Returns:
        dict: A dictionary containing the configuration settings.
    """
    logger = logging.getLogger(__name__)
    config_dict = {}

    try:
        conn = connect_to_db(CONST_CONFIG_DB)
        if not conn:
            logger.error("[ERROR] Unable to connect to configuration database")
            return config_dict

        if IS_CONTAINER:
            SITE = os.getenv("SITE", CONST_SITE)

        # Dynamically import the site-specific configuration module
        config = importlib.import_module(f"{SITE}")
        log_info(logger, f"[INFO] Reading configuration from /database/{SITE}.py")

        cursor = conn.cursor()

        # Insert default configurations into the database
        for key, value in config.CONST_DEFAULT_CONFIGS:
            cursor.execute("""
                INSERT OR IGNORE INTO configuration (key, value)
                VALUES (?, ?)
            """, (key, value))
        conn.commit()

        # Fetch all configurations into a dictionary
        cursor.execute("SELECT key, value FROM configuration")
        config_dict = dict(cursor.fetchall())

        log_info(logger, f"[INFO] Default configurations initialized successfully.")
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"[ERROR] Error initializing default configurations: {e}")
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    return config_dict

def get_config_settings():
    """Read configuration settings from the configuration database into a dictionary."""
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONFIG_DB)
        if not conn:
            logger.error("[ERROR] Unable to connect to configuration database")
            return None

        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM configuration")
        config_dict = dict(cursor.fetchall())
        conn.close()
        log_info(logger, f"[INFO] Successfully loaded {len(config_dict)} configuration settings")
        return config_dict
    except sqlite3.Error as e:
        logger.error(f"[ERROR] Error reading configuration database: {e}")
        return None

def log_alert_to_db(ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, alert_id_hash, realert=False):
    """Logs an alert to the alerts.db SQLite database."""
    logger = logging.getLogger(__name__)
    try:
        conn = sqlite3.connect(CONST_ALERTS_DB)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alerts (id, ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, times_seen, first_seen, last_seen, acknowledged)
            VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)
            ON CONFLICT(id)
            DO UPDATE SET
                times_seen = times_seen + 1,
                last_seen = CURRENT_TIMESTAMP
        """, (alert_id_hash, ip_address, json.dumps(flow), category, alert_enrichment_1, alert_enrichment_2))
        conn.commit()
        conn.close()
        log_info(logger, f"[INFO] Alert logged to database for IP: {ip_address}, Category: {category}")
    except sqlite3.Error as e:
        logger.error(f"[ERROR] Error logging alert to database: {e}")

def get_whitelist():
    """
    Retrieve active entries from the whitelist database.
    
    Returns:
        list: List of tuples containing (alert_id, category, insert_date)
              Returns None if there's an error
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_WHITELIST_DB)
        if not conn:
            log_info(logger, "[ERROR] Unable to connect to whitelist database")
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
            conn.close()

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
        conn = connect_to_db(db_name)
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
            conn.close()

def get_alerts_summary():
    """
    Get a summary of alerts by category from alerts.db.
    Prints total count and breakdown by category.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_ALERTS_DB)
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
            conn.close()

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
    whitelist_entries = json.loads(whitelist_entries_json)

    if not whitelist_entries:
        log_info(logger, "[INFO] No whitelist entries found in config_dict.")
        return

    conn = connect_to_db(CONST_WHITELIST_DB)
    if not conn:
        log_error(logger, "[ERROR] Unable to connect to whitelist database.")
        return

    try:
        cursor = conn.cursor()

        # Insert whitelist entries into the database
        for entry in whitelist_entries:
            src_ip, dst_ip, dst_port, protocol = entry
            cursor.execute("""
                INSERT OR IGNORE INTO whitelist (
                    whitelist_src_ip, whitelist_dst_ip, whitelist_dst_port, whitelist_protocol, whitelist_enabled
                ) VALUES (?, ?, ?, ?, 1)
            """, (src_ip, dst_ip, dst_port, protocol))

        conn.commit()
        log_info(logger, f"[INFO] Imported {len(whitelist_entries)} whitelist entries into the database.")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error importing whitelist entries: {e}")
    finally:
        conn.close()

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
    conn = connect_to_db(CONST_ALLFLOWS_DB)
    if not conn:
        log_error(logger, f"[ERROR] Unable to connect to database: {CONST_ALLFLOWS_DB}")
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
        updated_tag = f"{existing_tag};{tag}" if existing_tag else tag

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
        conn.close()

def get_localhosts():
    """
    Retrieve all local hosts from the localhosts database.

    Returns:
        set: A set of IP addresses from the localhosts database, or an empty set if an error occurs.
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_LOCALHOSTS_DB)

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
        conn.close()

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
    conn = connect_to_db(CONST_LOCALHOSTS_DB)

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
        conn.close()


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
        "localhosts_count": 0,
        "whitelist_count": 0
    }

    try:
        # Connect to the alerts database
        conn_alerts = connect_to_db(CONST_ALERTS_DB)
        if conn_alerts:
            cursor = conn_alerts.cursor()
            # Count acknowledged alerts
            cursor.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 1")
            counts["acknowledged_alerts"] = cursor.fetchone()[0]

            # Count unacknowledged alerts
            cursor.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 0")
            counts["unacknowledged_alerts"] = cursor.fetchone()[0]

            # Count total alerts
            cursor.execute("SELECT COUNT(*) FROM alerts")
            counts["total_alerts"] = cursor.fetchone()[0]

            conn_alerts.close()
        else:
            log_error(logger, "[ERROR] Unable to connect to alerts database")

        # Connect to the localhosts database
        conn_localhosts = connect_to_db(CONST_LOCALHOSTS_DB)
        if conn_localhosts:
            cursor = conn_localhosts.cursor()
            # Count entries in localhosts
            cursor.execute("SELECT COUNT(*) FROM localhosts")
            counts["localhosts_count"] = cursor.fetchone()[0]

            conn_localhosts.close()
        else:
            log_error(logger, "[ERROR] Unable to connect to localhosts database")

        # Connect to the whitelist database
        conn_whitelist = connect_to_db(CONST_WHITELIST_DB)
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

    return counts



