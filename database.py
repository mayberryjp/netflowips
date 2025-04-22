import sqlite3
import logging
from utils import log_info, log_error, log_warn  # Assuming log_info is defined in utils
from const import CONST_LOCAL_NETWORKS, IS_CONTAINER, CONST_DEFAULT_CONFIGS, CONST_ALLFLOWS_DB, CONST_CONFIG_DB, CONST_ALERTS_DB, CONST_ROUTER_IPADDRESS, CONST_WHITELIST_DB
import ipaddress
import os
from datetime import datetime
from notifications import send_telegram_message
import json

logger = logging.getLogger(__name__)  # Create a logger for this module

if IS_CONTAINER:
    LOCAL_NETWORKS = os.getenv("LOCAL_NETWORKS", CONST_LOCAL_NETWORKS).split(',')

def delete_database(db_path):
    """Deletes the specified SQLite database file if it exists."""
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
    try:
        conn = sqlite3.connect(DB_NAME)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database {DB_NAME}: {e}")
        return None

def create_database(db_name, create_table_sql):
    """Initializes a SQLite database with the specified schema."""
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
    """Inserts default configurations into the CONST_CONFIG_DB database."""
    try:
        conn = connect_to_db(CONST_CONFIG_DB)
        if not conn:
            logger.error("[ERROR] Unable to connect to configuration database")
            return

        cursor = conn.cursor()
        for key, value in CONST_DEFAULT_CONFIGS:
            cursor.execute("""
                INSERT OR IGNORE INTO configuration (key, value)
                VALUES (?, ?)
            """, (key, value))
        conn.commit()
        log_info(logger, f"[INFO] Default configurations initialized successfully.")
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"[ERROR] Error initializing default configurations: {e}")

def get_config_settings():
    """Read configuration settings from the configuration database into a dictionary."""
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
    try:
        conn = sqlite3.connect(CONST_ALERTS_DB)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alerts (id, ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, times_seen, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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



