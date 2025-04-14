import sqlite3
from utils import log_info  # Assuming log_info is defined in utils
from const import CONST_LOCAL_HOSTS, IS_CONTAINER  # Assuming LOCAL_HOSTS is defined in const
import ipaddress
import os
from datetime import datetime

if (IS_CONTAINER):
    LOCAL_HOSTS = os.getenv("LOCAL_HOSTS", CONST_LOCAL_HOSTS)
    LOCAL_HOSTS = [LOCAL_HOSTS] if ',' not in LOCAL_HOSTS else LOCAL_HOSTS.split(',')

def connect_to_db(db_name="/database/newflows.db"):
    """Establish a connection to the specified database."""
    try:
        conn = sqlite3.connect(db_name)
        return conn
    except sqlite3.Error as e:
        log_info(None, f"Error connecting to database {db_name}: {e}")
        return None

def update_all_flows(rows):
    """Update allflows.db with the rows from newflows.db."""
    allflows_conn = connect_to_db("/database/allflows.db")

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

                # Ensure src_ip is always the IP in LOCAL_HOSTS
                if not is_src_local and is_dst_local:
                    # Swap src_ip and dst_ip
                    src_ip, dst_ip = dst_ip, src_ip
                    src_port,dst_port = dst_port, src_port
                    sent_pkts = 0
                    sent_bytes = 0
                    rcv_pkts = packets
                    rcv_bytes = bytes_
                elif is_src_local and not is_dst_local:
                    sent_pkts = packets
                    sent_bytes = bytes_
                    rcv_pkts = 0
                    rcv_bytes = 0
                else:
                    # Skip rows where neither or both IPs are in LOCAL_HOSTS
                    log_info(None, f"Skipping row with unexpected IPs: {row}")
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
            log_info(None, f"Updated allflows.db with {len(rows)} rows.")

        except sqlite3.Error as e:
            log_info(None, f"Error updating allflows.db: {e}")
        finally:
            allflows_conn.close()

def delete_all_records_from_newflows():
    """Delete all records from the newflows.db database."""
    conn = connect_to_db("/database/newflows.db")
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM flows")  # Replace 'flows' with your table name
            conn.commit()
            log_info(None, "All records deleted from newflows.db.")
        except sqlite3.Error as e:
            log_info(None, f"Error deleting records from newflows.db: {e}")
        finally:
            conn.close()