import sqlite3
from utils import log_info  # Assuming log_info is defined in utils
from const import CONST_LOCAL_HOSTS, IS_CONTAINER, CONST_DEFAULT_CONFIGS, CONST_ALLFLOWS_DB, CONST_CONFIG_DB, CONST_ALERTS_DB, CONST_ROUTER_IPADDRESS  # Assuming LOCAL_HOSTS is defined in const
import ipaddress
import os
from datetime import datetime
from notifications import send_telegram_message  # Import notification functions
import json

if (IS_CONTAINER):
    LOCAL_HOSTS = os.getenv("LOCAL_HOSTS", CONST_LOCAL_HOSTS)
    LOCAL_HOSTS = [LOCAL_HOSTS] if ',' not in LOCAL_HOSTS else LOCAL_HOSTS.split(',')

def delete_database(db_path):
    """
    Deletes the specified SQLite database file if it exists.

    Args:
        db_path (str): The full path to the database file to be deleted.
    """
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
            log_info(None, f"[INFO] Deleted: {db_path}")
        else:
            log_info(None, f"[INFO] {db_path} does not exist, skipping deletion.")
    except Exception as e:
        log_info(None, f"[ERROR] Error deleting {db_path}: {e}")

def connect_to_db(DB_NAME):
    """Establish a connection to the specified database."""
    try:
        conn = sqlite3.connect(DB_NAME)
        return conn
    except sqlite3.Error as e:
        log_info(None, f"Error connecting to database {DB_NAME}: {e}")
        return None

def create_database(db_name, create_table_sql):
    """
    Initializes a SQLite database with the specified schema.

    Args:
        db_name (str): The full path to the database file.
        create_table_sql (str): The SQL statement to create the table schema.
    """
    try:
        conn = connect_to_db(db_name)
        if not conn:
            log_info(None, f"[ERROR] Unable to connect to {db_name}")
            return

        cursor = conn.cursor()

        # Execute the CREATE TABLE statement
        cursor.execute(create_table_sql)

        conn.commit()
        log_info(None, f"[INFO] {db_name} initialized successfully.")
        conn.close()
    except sqlite3.Error as e:
        log_info(None, f"[ERROR] Error initializing {db_name}: {e}")

def update_allflows(rows, config_dict):
    """Update allflows.db with the rows from newflows.db."""

    allflows_conn = connect_to_db(CONST_ALLFLOWS_DB)
    if allflows_conn:
        try:
            allflows_cursor = allflows_conn.cursor()

            for row in rows:
                # Extract row values
                src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, last_seen, times_seen = row

                # Determine if src_ip or dst_ip is in LOCAL_HOSTS
                #is_src_local = any(ipaddress.ip_address(src_ip) in ipaddress.ip_network(net) for net in LOCAL_HOSTS)
               # is_dst_local = any(ipaddress.ip_address(dst_ip) in ipaddress.ip_network(net) for net in LOCAL_HOSTS)

                now = datetime.utcnow().isoformat()
                # Insert or update the flow in allflows.db
                allflows_cursor.execute("""
                    INSERT INTO allflows (
                        src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes, flow_start, flow_end, times_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(src_ip, dst_ip, src_port, dst_port, protocol)
                    DO UPDATE SET
                        packets = packets + excluded.packets,
                        bytes = bytes + excluded.bytes,
                        flow_end = excluded.flow_end,
                        times_seen = times_seen + 1,
                        last_seen = excluded.last_seen
                """, (src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, now))
                
            # Commit changes to allflows.db
            allflows_conn.commit()
            log_info(None, f"[INFO] Updated {CONST_ALLFLOWS_DB} with {len(rows)} rows.")

        except sqlite3.Error as e:
            log_info(None, f"[ERROR] Error updating {CONST_ALLFLOWS_DB}: {e}")
        finally:
            allflows_conn.close()


def delete_all_records(db_name, table_name='flows'):
    """
    Delete all records from the specified database and table.
    
    Args:
        db_name (str): The database file path to delete records from
        table_name (str): The table name to delete records from (default: 'flows')
    """
    conn = connect_to_db(db_name)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {table_name}")
            conn.commit()
            log_info(None, f"[INFO] All records deleted from {db_name}.{table_name}")
        except sqlite3.Error as e:
            log_info(None, f"[ERROR] Error deleting records from {db_name}: {e}")
        finally:
            conn.close()


def init_configurations():
    """
    Inserts default configurations into the CONST_CONFIG_DB database.
    Ensures that default values are only inserted if the key does not already exist.
    """
    try:
        conn = connect_to_db(CONST_CONFIG_DB)
        if not conn:
            log_info(None, "[ERROR] Unable to connect to configuration database")
            return

        cursor = conn.cursor()

        # Insert default configurations only if the key does not exist
        for key, value in CONST_DEFAULT_CONFIGS:
            cursor.execute("""
                INSERT OR IGNORE INTO configuration (key, value)
                VALUES (?, ?)
            """, (key, value))

        conn.commit()
        log_info(None, "[INFO] Default configurations initialized successfully.")
        conn.close()

    except sqlite3.Error as e:
        log_info(None, f"[ERROR] Error initializing default configurations: {e}")

def get_config_settings():
    """
    Read configuration settings from the configuration database into a dictionary.
    
    Returns:
        dict: Dictionary containing configuration key-value pairs.
        None: If there's an error accessing the database.
    """
    try:
        conn = connect_to_db(CONST_CONFIG_DB)
        if not conn:
            log_info(None, "[ERROR] Unable to connect to configuration database")
            return None

        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM configuration")
        
        # Convert results to dictionary
        config_dict = dict(cursor.fetchall())
        
        conn.close()
        log_info(None, f"[INFO] Successfully loaded {len(config_dict)} configuration settings")
        return config_dict

    except sqlite3.Error as e:
        log_info(None, f"[ERROR] Error reading configuration database: {e}")
        return None


def log_alert_to_db(ip_address, flow, category, alert_id_hash, realert=False):
    """
    Logs an alert to the alerts.db SQLite database.

    Args:
        ip_address (str): The IP address in question.
        flow (dict): The flow data as a dictionary.
        category (str): The alert category name.
    """
    try:
        conn = sqlite3.connect(CONST_ALERTS_DB)
        cursor = conn.cursor()

        # Generate the primary key by concatenating ip_address and category


        # Insert or update the alert in the database
        cursor.execute("""
            INSERT INTO alerts (id, ip_address, flow, category, times_seen, first_seen, last_seen)
            VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(id)
            DO UPDATE SET
                times_seen = times_seen + 1,
                last_seen = CURRENT_TIMESTAMP
        """, (alert_id_hash, ip_address, json.dumps(flow), category))

        conn.commit()
        conn.close()
        log_info(None, f"[INFO] Alert logged to database for IP: {ip_address}, Category: {category}")
    except sqlite3.Error as e:
        log_info(None, f"[ERROR] Error logging alert to database: {e}")

