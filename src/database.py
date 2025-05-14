import sqlite3
import logging
from src.utils import log_info, log_error, get_machine_unique_identifier  # Assuming log_info is defined in utils
from src.const import CONST_INSTALL_CONFIGS, CONST_SITE, IS_CONTAINER, CONST_CONSOLIDATED_DB, VERSION
import ipaddress
import os
from datetime import datetime, timedelta
import json
import traceback
import sys
import importlib
from src.utils import is_ip_in_range
  # Create a logger for this module

def store_site_name(site_name):
    """
    Store the site name in the configuration database with the key 'SiteName'.
    
    Args:
        site_name (str): The site name to store
        
    Returns:
        bool: True if the operation was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    try:
        # Validate input
        if not site_name or not isinstance(site_name, str):
            log_error(logger, "[ERROR] Invalid site name provided")
            return False
            
        # Connect to the configuration database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "configuration")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to configuration database")
            return False

        cursor = conn.cursor()

        # Insert or update the SiteName in the configuration table
        cursor.execute("""
            INSERT INTO configuration (key, value)
            VALUES ('SiteName', ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
        """, (site_name,))

        conn.commit()
        log_info(logger, f"[INFO] Site name stored successfully: {site_name}")
        return True

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while storing site name: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while storing site name: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

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
        conn.execute("PRAGMA busy_timeout = 10000")
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

def create_table(db_name, create_table_sql, table):
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


def delete_old_traffic_stats():
    """
    Delete all records from the trafficstats table with a timestamp of 2 days ago or older.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    try:
        # Connect to the consolidated database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "trafficstats")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to trafficstats database.")
            return False

        cursor = conn.cursor()

        # Calculate the cutoff timestamp (2 days ago)
        cutoff_date = (datetime.now() - timedelta(days=31)).strftime('%Y-%m-%d')

        # Delete records older than the cutoff timestamp
        cursor.execute(f"""
            DELETE FROM trafficstats
            WHERE timestamp LIKE '{cutoff_date}:%'
        """, )

        conn.commit()
        log_info(logger, f"[INFO] Deleted records older than {cutoff_date} from trafficstats table.")
        return True

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while deleting old traffic stats: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while deleting old traffic stats: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
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

def delete_all_records(db_name, table_name):
    """Delete all records from the specified database and table."""
    logger = logging.getLogger(__name__)
    conn = connect_to_db(db_name, table_name)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {table_name}")
            conn.commit()
            log_info(logger, f"[INFO] All records deleted from {db_name} {table_name}")
        except sqlite3.Error as e:
            log_error(logger,f"[ERROR] Error deleting records from {db_name} {table_name}: {e}")
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
    """
    Logs an alert to the alerts.db SQLite database and indicates whether it was an insert or an update.

    Args:
        ip_address (str): The IP address associated with the alert.
        flow (dict): The flow data as a dictionary.
        category (str): The category of the alert.
        alert_enrichment_1 (str): Additional enrichment data for the alert.
        alert_enrichment_2 (str): Additional enrichment data for the alert.
        alert_id_hash (str): A unique hash for the alert.
        realert (bool): Whether this is a re-alert.

    Returns:
        str: "insert" if a new row was inserted, "update" if an existing row was updated, or "error" if an error occurred.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return "error"

        cursor = conn.cursor()

        # Execute the insert or update query
        cursor.execute("""
            INSERT INTO alerts (id, ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, times_seen, first_seen, last_seen, acknowledged)
            VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now', 'localtime'), datetime('now', 'localtime'), 0)
            ON CONFLICT(id)
            DO UPDATE SET
                times_seen = times_seen + 1,
                last_seen = datetime('now', 'localtime')
        """, (alert_id_hash, ip_address, json.dumps(flow), category, alert_enrichment_1, alert_enrichment_2))

        # Check the number of rows affected
        if conn.total_changes == 1:
            operation = "insert"
        else:
            operation = "update"

        conn.commit()
        log_info(logger, f"[INFO] Alert logged to database for IP: {ip_address}, Category: {category} ({operation}).")
        return operation

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error logging alert to database: {e}")
        return "error"
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_custom_tags():
    """
    Retrieve active entries from the customtags table in the ignorelist database.

    Returns:
        list: List of tuples containing (tag_id, src_ip, dst_ip, dst_port, protocol, tag_name)
              Returns None if there's an error.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "customtags")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to ignorelist database")
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


def get_ignorelist():
    """
    Retrieve active entries from the ignorelist database.
    
    Returns:
        list: List of tuples containing (alert_id, category, insert_date)
              Returns None if there's an error
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "ignorelist")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to ignorelist database")
            return None

        cursor = conn.cursor()
        cursor.execute("""
            SELECT ignorelist_id, ignorelist_src_ip, ignorelist_dst_ip, ignorelist_dst_port, ignorelist_protocol
            FROM ignorelist 
            WHERE ignorelist_enabled = 1
        """)
        ignorelist = cursor.fetchall()

        log_info(logger, f"[INFO] Retrieved {len(ignorelist)} active ignorelist entries")
        
        return ignorelist

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error retrieving ignorelist entries: {e}")
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
    Import custom tag entries into the customtags table in the ignorelist database.

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
        log_error(logger, "[ERROR] Unable to connect to ignorelist database.")
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

def import_ignorelists(config_dict):
    """
    Import ignorelist entries into the ignorelist database from a config_dict entry.

    Args:
        config_dict (dict): Configuration dictionary containing ignorelist entries.
                            Expected format: "IgnoreListEntries" -> JSON string of list of tuples
                            Each tuple: (src_ip, dst_ip, dst_port, protocol)
    """
    logger = logging.getLogger(__name__)
    ignorelist_entries_json = config_dict.get("IgnoreListEntries", "[]")
    if not ignorelist_entries_json:
        log_info(logger, "[INFO] No ignorelist entries found in config_dict.")
        return
    #print(f"[INFO] ignorelist_entries_json: {ignorelist_entries_json}")
    ignorelist_entries = json.loads(ignorelist_entries_json)

    if not ignorelist_entries:
        log_info(logger, "[INFO] No ignorelist entries found in config_dict.")
        return

    conn = connect_to_db(CONST_CONSOLIDATED_DB, "ignorelist")
    if not conn:
        log_error(logger, "[ERROR] Unable to connect to ignorelist database.")
        return

    try:
        cursor = conn.cursor()

        # Insert ignorelist entries into the database if they don't already exist
        for entry in ignorelist_entries:
            ignorelist_id, src_ip, dst_ip, dst_port, protocol = entry

            # Check if the ignorelist entry already exists
            cursor.execute("""
                SELECT COUNT(*) FROM ignorelist
                WHERE ignorelist_id = ? AND ignorelist_src_ip = ? AND ignorelist_dst_ip = ? AND ignorelist_dst_port = ? AND ignorelist_protocol = ?
            """, (ignorelist_id, src_ip, dst_ip, dst_port, protocol))
            exists = cursor.fetchone()[0]

            if exists:
                log_info(logger, f"[INFO] IgnoreList entry already exists: {entry}")
                continue

            # Insert the new ignorelist entry
            cursor.execute("""
                INSERT INTO ignorelist (
                    ignorelist_id, ignorelist_src_ip, ignorelist_dst_ip, ignorelist_dst_port, ignorelist_protocol, ignorelist_enabled, ignorelist_added, ignorelist_insert_date
                ) VALUES (?, ?, ?, ?, ?, 1, datetime('now', 'localtime'), datetime('now', 'localtime'))
            """, (ignorelist_id, src_ip, dst_ip, dst_port, protocol))

        conn.commit()
        log_info(logger, f"[INFO] Imported {len(ignorelist_entries)} ignorelist entries into the database.")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error importing ignorelist entries: {e}")
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

def get_localhosts_all():
    """
    Retrieve all localhost records with complete details from the localhosts database.

    Returns:
        list: A list of dictionaries containing all columns for each localhost entry,
              or an empty list if an error occurs.
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")

    if not conn:
        log_error(logger, "[ERROR] Unable to connect to localhosts database")
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ip_address, first_seen, original_flow, 
                   mac_address, mac_vendor, dhcp_hostname, dns_hostname, os_fingerprint,
                   lease_hostname, lease_hwaddr, lease_clientid, acknowledged, local_description, icon, tags
            FROM localhosts
        """)

        # Get column names from cursor description
        columns = [column[0] for column in cursor.description]
        
        # Convert rows to list of dictionaries with column names as keys
        localhosts = []
        for row in cursor.fetchall():
            localhost_dict = dict(zip(columns, row))
            localhosts.append(localhost_dict)
            
        log_info(logger, f"[INFO] Retrieved {len(localhosts)} localhost records with full details")
        return localhosts
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Failed to retrieve localhost records: {e}")
        return []
    finally:
        disconnect_from_db(conn)

def get_localhost_by_ip(ip_address):
    """
    Retrieve complete details for a specific localhost record by IP address.

    Args:
        ip_address (str): The IP address of the localhost to retrieve.

    Returns:
        dict: A dictionary containing all columns for the specified localhost,
              or None if the localhost is not found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the localhosts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to localhosts database.")
            return None

        cursor = conn.cursor()
        
        # Query for the specific IP address
        cursor.execute("""
            SELECT ip_address, first_seen, original_flow, 
                   mac_address, mac_vendor, dhcp_hostname, dns_hostname, os_fingerprint,
                   lease_hostname, lease_hwaddr, lease_clientid, acknowledged, local_description, icon, tags
            FROM localhosts
            WHERE ip_address = ?
        """, (ip_address,))
        
        row = cursor.fetchone()
        
        if not row:
            log_info(logger, f"[INFO] No localhost found with IP address: {ip_address}")
            return None
            
        # Get column names from cursor description
        columns = [column[0] for column in cursor.description]
        
        # Convert row to dictionary with column names as keys
        localhost_dict = dict(zip(columns, row))
        
        log_info(logger, f"[INFO] Retrieved details for localhost with IP: {ip_address}")
        return localhost_dict
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving localhost with IP {ip_address}: {e}")
        return None
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving localhost with IP {ip_address}: {e}")
        return None
    finally:
        if 'conn' in locals() and conn:
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


def get_recent_alerts_by_ip(ip_address):
    """
    Retrieve the most recent 100 alerts for a specific IP address from the alerts table.

    Args:
        ip_address (str): The IP address to filter alerts by.

    Returns:
        list: A list of dictionaries containing the most recent 100 alerts for the specified IP.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return []

        cursor = conn.cursor()
        
        # Retrieve alerts for the specified IP address, most recent first, limited to 100
        cursor.execute("""
            SELECT id, ip_address, flow, category, 
                   alert_enrichment_1, alert_enrichment_2,
                   times_seen, first_seen, last_seen, acknowledged
            FROM alerts 
            WHERE ip_address = ?
            ORDER BY last_seen DESC 
            LIMIT 100
        """, (ip_address,))
        
        rows = cursor.fetchall()
        
        # Get column names from cursor description
        columns = [column[0] for column in cursor.description]
        
        # Format the results as a list of dictionaries
        alerts = []
        for row in rows:
            alert_dict = dict(zip(columns, row))
            # Parse JSON if flow is stored as a string
            if 'flow' in alert_dict and isinstance(alert_dict['flow'], str):
                try:
                    alert_dict['flow'] = json.loads(alert_dict['flow'])
                except:
                    pass  # Keep as string if JSON parsing fails
            alerts.append(alert_dict)

        log_info(logger, f"[INFO] Retrieved {len(alerts)} recent alerts for IP address {ip_address}.")
        return alerts

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving alerts for IP {ip_address}: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving alerts for IP {ip_address}: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_all_alerts():
    """
    Retrieve all records from the alerts table.

    Returns:
        list: A list of dictionaries containing all records from the alerts table.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return []

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alerts")
        rows = cursor.fetchall()

        # Get column names from cursor description
        columns = [column[0] for column in cursor.description]
        
        # Format the results as a list of dictionaries
        alerts = []
        for row in rows:
            alert_dict = dict(zip(columns, row))
            # Parse JSON if flow is stored as a string
            if 'flow' in alert_dict and isinstance(alert_dict['flow'], str):
                try:
                    alert_dict['flow'] = json.loads(alert_dict['flow'])
                except:
                    pass  # Keep as string if JSON parsing fails
            alerts.append(alert_dict)

        log_info(logger, f"[INFO] Retrieved {len(alerts)} alerts from the database.")
        return alerts

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving alerts: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving alerts: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)





def collect_database_counts():
    """
    Collects counts from the alerts, localhosts, and ignorelist tables.

    Returns:
        dict: A dictionary containing the counts for acknowledged alerts, unacknowledged alerts,
              total alerts, localhosts entries, and ignorelist entries.
    """
    logger = logging.getLogger(__name__)
    counts = {
        "acknowledged_alerts": 0,
        "unacknowledged_alerts": 0,
        "total_alerts": 0,
        "unacknowledged_localhosts_count": 0,
        "acknowledged_localhosts_count": 0,
        "total_localhosts_count": 0,
        "ignorelist_count": 0,

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

        # Connect to the ignorelist database
        conn_ignorelist = connect_to_db(CONST_CONSOLIDATED_DB, "ignorelist")
        if conn_ignorelist:
            cursor = conn_ignorelist.cursor()
            # Count entries in ignorelist
            cursor.execute("SELECT COUNT(*) FROM ignorelist")
            counts["ignorelist_count"] = cursor.fetchone()[0]

            conn_ignorelist.close()
        else:
            log_error(logger, "[ERROR] Unable to connect to ignorelist database")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error: {e}")
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error: {e}")

    conn_ignorelist.close()
    return counts

def get_alerts_by_category(category_name):
    """
    Retrieve alerts from the database for a specific category.

    Args:
        category_name (str): The category name to filter alerts by

    Returns:
        list: A list of raw database rows for the specified category.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return []

        cursor = conn.cursor()
        
        # Retrieve all alerts for the specified category
        cursor.execute("""
            SELECT id, ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, 
                   times_seen, first_seen, last_seen, acknowledged
            FROM alerts
            WHERE category = ?
            ORDER BY last_seen DESC
        """, (category_name,))
        
        # Just return the raw rows
        rows = cursor.fetchall()
        
        log_info(logger, f"[INFO] Retrieved {len(rows)} alerts for category '{category_name}' from the database.")
        return rows

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving alerts for category '{category_name}': {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving alerts for category '{category_name}': {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)


def store_version():
    """
    Store the current version from CONST.py in the configuration database
    with the key 'Version'.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    try:
        # Import the version from CONST.py
        from src.const import VERSION
        
        # Connect to the configuration database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "configuration")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to configuration database.")
            return False

        cursor = conn.cursor()

        # Insert or update the Version in the configuration table
        cursor.execute("""
            INSERT INTO configuration (key, value)
            VALUES ('Version', ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
        """, (VERSION,))

        conn.commit()
        disconnect_from_db(conn)

        log_info(logger, f"[INFO] Version stored successfully: {VERSION}")
        return True

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while storing version: {e}")
        return False
    except ImportError as e:
        log_error(logger, f"[ERROR] Failed to import CONST_VERSION: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while storing version: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

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

def update_action_acknowledged(action_id):
    """
    Update the acknowledged field to 1 for a specific action based on the action_id.

    Args:
        action_id (str): The ID of the action to update.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "actions")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to actions database.")
            return False

        cursor = conn.cursor()
        cursor.execute("""
            UPDATE actions
            SET acknowledged = 1
            WHERE action_id = ?
        """, (action_id,))
        conn.commit()
        log_info(logger, f"[INFO] Updated acknowledged field to 1 for action ID: {action_id}")
        return True

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while updating action: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)


def insert_action(action_text):
    """
    Insert a new record into the actions table.

    Args:
        action_data (dict): A dictionary containing the action data to insert.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "actions")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to actions database.")
            return False

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO actions (action_text, acknowledged)
            VALUES (?, 0)
        """, (action_text,))
        conn.commit()
        log_info(logger, f"[INFO] Inserted new action with text: {action_text}")
        return True

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while inserting action: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_all_actions():
    """
    Retrieve all records from the actions table.

    Returns:
        list: A list of dictionaries containing all records from the actions table.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "actions")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to actions database.")
            return []

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM actions")
        rows = cursor.fetchall()
        disconnect_from_db(conn)

        # Format the results as a list of dictionaries
        actions = [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

        log_info(logger, f"[INFO] Retrieved {len(actions)} actions from the database.")
        return actions

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving actions: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_services_by_port(port_number):
    """
    Retrieve service information for a specific port number.
    
    Args:
        port_number (int): The port number to query
        
    Returns:
        dict: A dictionary where keys are protocols (e.g., 'tcp', 'udp') and values 
              are dictionaries containing 'service_name' and 'description'.
              Returns an empty dictionary if no services found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the services database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "services")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to services database.")
            return {}
            
        cursor = conn.cursor()
        
        # Query services for the specified port
        cursor.execute("""
            SELECT protocol, service_name, description 
            FROM services 
            WHERE port_number = ?
        """, (port_number,))
        
        rows = cursor.fetchall()
        
        # Format results as a dictionary
        services_dict = {}
        for row in rows:
            protocol = row[0]
            services_dict[protocol] = {
                'service_name': row[1],
                'description': row[2]
            }
        
        log_info(logger, f"[INFO] Retrieved {len(services_dict)} service entries for port {port_number}.")
        return services_dict
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving services for port {port_number}: {e}")
        return {}
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving services for port {port_number}: {e}")
        return {}
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

