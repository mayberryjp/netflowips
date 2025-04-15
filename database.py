import sqlite3
from utils import log_info  # Assuming log_info is defined in utils
from const import CONST_LOCAL_HOSTS, IS_CONTAINER, CONST_NEWFLOWS_DB, CONST_ALLFLOWS_DB, CONST_CONFIG_DB, CONST_ALERTS_DB, CONST_ROUTER_IPADDRESS  # Assuming LOCAL_HOSTS is defined in const
import ipaddress
import os
from datetime import datetime
from notifications import send_telegram_message  # Import notification functions
import json

if (IS_CONTAINER):
    LOCAL_HOSTS = os.getenv("LOCAL_HOSTS", CONST_LOCAL_HOSTS)
    LOCAL_HOSTS = [LOCAL_HOSTS] if ',' not in LOCAL_HOSTS else LOCAL_HOSTS.split(',')
    ROUTER_IPADDRESS = os.getenv("LOCAL_HOSTS", CONST_ROUTER_IPADDRESS)
    ROUTER_IPADDRESS = [ROUTER_IPADDRESS] if ',' not in ROUTER_IPADDRESS else ROUTER_IPADDRESS.split(',')

# Initialize the database
def init_newflows_db():
    conn = sqlite3.connect(CONST_NEWFLOWS_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS flows (
            src_ip TEXT,
            dst_ip TEXT,
            src_port INTEGER,
            dst_port INTEGER,
            protocol INTEGER,
            packets INTEGER,
            bytes INTEGER,
            flow_start TEXT,
            flow_end TEXT,
            last_seen TEXT,
            times_seen INTEGER,
            PRIMARY KEY (src_ip, dst_ip, src_port, dst_port, protocol)
        )
    ''')
    conn.commit()
    conn.close()

def delete_newflowsdb():
    """
    Deletes a file at the given path if it exists.

    Args:
        file_path (str): The full path to the file to be deleted.
    """
    try:
        if os.path.exists(CONST_NEWFLOWS_DB):
            os.remove(CONST_NEWFLOWS_DB)
            log_info(None, f"[INFO] Deleted: {CONST_NEWFLOWS_DB}")
        else:
            log_info(None, "[WARN] File does not exist.")
    except Exception as e:
        print(f"[ERROR] Error deleting file: {e}")


def connect_to_db(DB_NAME):
    """Establish a connection to the specified database."""
    try:
        conn = sqlite3.connect(DB_NAME)
        return conn
    except sqlite3.Error as e:
        log_info(None, f"Error connecting to database {DB_NAME}: {e}")
        return None

def update_allflows(rows, config_dict):
    """Update allflows.db with the rows from newflows.db."""
    allflows_conn = connect_to_db(CONST_ALLFLOWS_DB)

    if allflows_conn:
        try:
            allflows_cursor = allflows_conn.cursor()

            # Ensure the allflows table exists with the new columns and updated primary key
            allflows_cursor.execute("""
                CREATE TABLE IF NOT EXISTS allflows (
                    src_ip TEXT,
                    dst_ip TEXT,
                    dst_port INTEGER,
                    protocol INTEGER,
                    packets INTEGER,
                    bytes INTEGER,
                    flow_start TEXT,
                    flow_end TEXT,
                    times_seen INTEGER DEFAULT 1,
                    sent_pkts INTEGER DEFAULT 0,
                    sent_bytes INTEGER DEFAULT 0,
                    rcv_pkts INTEGER DEFAULT 0,
                    rcv_bytes INTEGER DEFAULT 0,
                    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (src_ip, dst_ip, dst_port, protocol)
                )
            """)

            for row in rows:
                # Extract row values
                src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, last_seen, times_seen = row

                # Determine if src_ip or dst_ip is in LOCAL_HOSTS
                is_src_local = any(ipaddress.ip_address(src_ip) in ipaddress.ip_network(net) for net in LOCAL_HOSTS)
                is_dst_local = any(ipaddress.ip_address(dst_ip) in ipaddress.ip_network(net) for net in LOCAL_HOSTS)

                # Determine if the flow involves a router IP address
                involves_router = any(ipaddress.ip_address(src_ip) in ipaddress.ip_network(net) or
                                      ipaddress.ip_address(dst_ip) in ipaddress.ip_network(net) for net in ROUTER_IPADDRESS)
                
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

                original_flow = json.dumps(row)  # Encode the original flow as JSON

                # Ensure src_ip is always the IP in LOCAL_HOSTS
                if not is_src_local and is_dst_local:
                    # Swap src_ip and dst_ip
                    src_ip, dst_ip = dst_ip, src_ip
                    src_port, dst_port = dst_port, src_port
                    sent_pkts = 0
                    sent_bytes = 0
                    rcv_pkts = packets
                    rcv_bytes = bytes_
                elif is_src_local and not is_dst_local:
                    sent_pkts = packets
                    sent_bytes = bytes_
                    rcv_pkts = 0
                    rcv_bytes = 0
                elif involves_router:
                    # Handle flows involving a router IP address
                    log_info(None, f"[INFO] Flow involves a router IP address: {row}")
                    if config_dict.get("RouterFlowsDetection") == 2:
                            # Send a Telegram message and log the alert
                            message = f"Flow involves a router IP address: {router_ip_seen}\nFlow: {original_flow}"
                            send_telegram_message(message)
                            log_alert_to_db(router_ip_seen, row, "Flow involves a router IP address",f"{router_ip_seen}_{src_ip}_{dst_ip}_{protocol}_{router_port}_RouterFlowsDetection",False)
                    elif config_dict.get("RouterFlowsDetection") == 1:
                            # Only log the alert
                            log_alert_to_db(router_ip_seen, row, "Flow involves a router IP address",f"{router_ip_seen}_{src_ip}_{dst_ip}_{protocol}_{router_port}_RouterFlowsDetection",False)
                    sent_pkts = packets if is_src_local else 0
                    sent_bytes = bytes_ if is_src_local else 0
                    rcv_pkts = packets if is_dst_local else 0
                    rcv_bytes = bytes_ if is_dst_local else 0
                elif is_src_local and is_dst_local:
                    # Handle flows where both src_ip and dst_ip are in LOCAL_HOSTS
                    log_info(None, f"[INFO] Flow involves two local hosts: {row}")
                    if config_dict.get("LocalFlowsDetection") == 2:
                            # Send a Telegram message and log the alert
                            message = f"Flow involves two local hosts: {src_ip} and {dst_ip}\nFlow: {original_flow}"
                            send_telegram_message(message)
                            log_alert_to_db(router_ip_seen, row, "Flow involves two local hosts",f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_LocalFlowsDetection",False)
                    elif config_dict.get("LocalFlowsDetection") == 1:
                            # Only log the alert
                            log_alert_to_db(router_ip_seen, row, "Flow involves two local hosts",f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_LocalFlowsDetection",False)   
                    sent_pkts = packets
                    sent_bytes = bytes_
                    rcv_pkts = packets
                    rcv_bytes = bytes_
                elif not is_src_local and not is_dst_local:
                    # Handle flows where neither src_ip nor dst_ip is in LOCAL_HOSTS
                    log_info(None, f"[INFO] Flow involves two foreign hosts: {row}")
                    if config_dict.get("ForeignFlowsDetection") == 2:
                            # Send a Telegram message and log the alert
                            message = f"Flow involves two foreign hosts: {src_ip} and {dst_ip}\nFlow: {original_flow}"
                            send_telegram_message(message)
                            log_alert_to_db(router_ip_seen, row, "Flow involves two foreign hosts",f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_ForeignFlowsDetection",False)
                    elif config_dict.get("ForeignFlowsDetection") == 1:
                            # Only log the alert
                            log_alert_to_db(router_ip_seen, row, "Flow involves two foreign hosts",f"{src_ip}_{dst_ip}_{protocol}_{src_port}_{dst_port}_ForeignFlowsDetection",False)               
                    sent_pkts = 0
                    sent_bytes = 0
                    rcv_pkts = 0
                    rcv_bytes = 0
                else:
                    # Skip rows where neither or both IPs are in LOCAL_HOSTS
                    log_info(None, f"[WARN] Skipping row with unexpected IPs: {row}")
                    continue

                now = datetime.utcnow().isoformat()
                # Insert or update the flow in allflows.db
                allflows_cursor.execute("""
                    INSERT INTO allflows (
                        src_ip, dst_ip, dst_port, protocol, packets, bytes, flow_start, flow_end, times_seen,
                        sent_pkts, sent_bytes, rcv_pkts, rcv_bytes, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    ON CONFLICT(src_ip, dst_ip, dst_port, protocol)
                    DO UPDATE SET
                        packets = packets + excluded.packets,
                        bytes = bytes + excluded.bytes,
                        flow_end = excluded.flow_end,
                        times_seen = times_seen + 1,
                        sent_pkts = sent_pkts + excluded.sent_pkts,
                        sent_bytes = sent_bytes + excluded.sent_bytes,
                        rcv_pkts = rcv_pkts + excluded.rcv_pkts,
                        rcv_bytes = rcv_bytes + excluded.rcv_bytes,
                        last_seen = excluded.last_seen
                """, (src_ip, dst_ip, dst_port, protocol, packets, bytes_, flow_start, flow_end,
                      sent_pkts, sent_bytes, rcv_pkts, rcv_bytes, now))

            # Commit changes to allflows.db
            allflows_conn.commit()
            log_info(None, f"[INFO] Updated {CONST_ALLFLOWS_DB} with {len(rows)} rows.")

        except sqlite3.Error as e:
            log_info(None, f"[ERROR] Error updating {CONST_ALLFLOWS_DB}: {e}")
        finally:
            allflows_conn.close()

def delete_all_records_from_newflows():
    """Delete all records from the newflows.db database."""
    conn = connect_to_db(CONST_NEWFLOWS_DB)
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM flows")  # Replace 'flows' with your table name
            conn.commit()
            log_info(None, f"[INFO] All records deleted from {CONST_NEWFLOWS_DB}.")
        except sqlite3.Error as e:
            log_info(None, f"[ERROR] Error deleting records from {CONST_NEWFLOWS_DB}: {e}")
        finally:
            conn.close()

def init_config_db():
    """
    Initialize the configuration database with default settings.
    Creates a new database if it doesn't exist and populates default values.
    """
    try:
        conn = connect_to_db(CONST_CONFIG_DB)
        cursor = conn.cursor()

        # Create the configuration table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuration (
                key TEXT PRIMARY KEY,
                value INTEGER
            )
        ''')

        # Check if the table is empty
        cursor.execute("SELECT COUNT(*) FROM configuration")
        count = cursor.fetchone()[0]

        if count == 0:
            # Insert default configurations
            default_configs = [
                ('NewHostsDetection', 2),
                ('LocalFlowsDetection', 1),
                ('RouterFlowsDetection', 1),
                ('ForeignFlowsDetection', 1)
                # Add more default configurations here as needed
            ]
            
            cursor.executemany(
                "INSERT INTO configuration (key, value) VALUES (?, ?)",
                default_configs
            )
            
            conn.commit()
            log_info(None, "[INFO] Configuration database initialized with default values.")
        
        conn.close()
        
    except sqlite3.Error as e:
        log_info(None, f"[ERROR] Error initializing configuration database: {e}")

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

def init_alerts_db():
    """
    Initializes the alerts.db SQLite database if it doesn't already exist.
    """
    try:
        # Check if the database file already exists
        if not os.path.exists(CONST_ALERTS_DB):
            conn = sqlite3.connect(CONST_ALERTS_DB)
            cursor = conn.cursor()

            # Create the alerts table with the updated schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,  -- Primary key based on concatenating ip_address and category
                    ip_address TEXT,
                    flow TEXT,
                    category TEXT,
                    times_seen INTEGER DEFAULT 0,
                    first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_seen TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            conn.close()
            log_info(None, "[INFO] alerts.db initialized successfully.")
        else:
            log_info(None, "[INFO] alerts.db already exists.")
    except sqlite3.Error as e:
        log_info(None, f"[ERROR] Error initializing alerts.db: {e}")


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


def delete_config_db():
    """
    Deletes the configuration.db SQLite database file if it exists.
    """
    try:
        if os.path.exists(CONST_CONFIG_DB):
            os.remove(CONST_CONFIG_DB)
            log_info(None, f"[INFO] Deleted: {CONST_CONFIG_DB}")
        else:
            log_info(None, "[INFO] configuration.db does not exist, skipping deletion.")
    except Exception as e:
        log_info(None, f"[ERROR] Error deleting configuration.db: {e}")