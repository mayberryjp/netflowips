import os
import sys
from database.core import connect_to_db, disconnect_from_db
from pathlib import Path
# Set up path for imports
current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
sys.path.insert(0, "/database")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from init import *

def update_all_flows(rows, config_dict):
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

def get_flows_by_source_ip(src_ip):
    """
    Retrieve all flows from a specific source IP address, grouped by destination.
    
    Args:
        src_ip (str): The source IP address to search for
        
    Returns:
        list: A list of dictionaries containing aggregated flow data for each destination,
              ordered by total_bytes in descending order.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the allflows database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "allflows")
        if not conn:
            log_error(logger, f"[ERROR] Unable to connect to allflows database.")
            return []

        cursor = conn.cursor()
        
        # Query all flows from the specified source IP
        cursor.execute("""
            SELECT dst_ip, dst_port, protocol,
                   sum(times_seen) as flow_count,
                   SUM(packets) as total_packets,
                   SUM(bytes) as total_bytes,
                   MAX(last_seen) as last_flow,
                   MIN(flow_start) as first_flow
            FROM allflows 
            WHERE src_ip = ?
            GROUP BY dst_ip, dst_port, protocol
            ORDER BY total_bytes DESC
        """, (src_ip,))
        
        rows = cursor.fetchall()
            
        #log_info(logger, f"[INFO] Retrieved {len(rows)} flow records for source IP {src_ip}.")
        return rows
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving flows for source IP {src_ip}: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving flows for source IP {src_ip}: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_dead_connections_from_database():
    """
    Identify potential dead connections in the network by finding flows that have
    traffic in one direction but not in the reverse direction.
    
    Returns:
        list: A list of dictionaries containing information about potential dead connections.
              Each dictionary includes initiator_ip, responder_ip, responder_port, 
              protocol, tags, and packet counts.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the allflows database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "allflows")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to allflows database.")
            return []

        cursor = conn.cursor()
        
        # Execute the complex query to identify potential dead connections
        cursor.execute("""
                WITH ConnectionPairs AS (
                    SELECT 
                        a1.src_ip as initiator_ip,
                        a1.dst_ip as responder_ip,
                        a1.src_port as initiator_port,
                        a1.dst_port as responder_port,
                        a1.protocol as connection_protocol,
                        a1.packets as forward_packets,
                        a1.bytes as forward_bytes,
                        a1.times_seen as forward_seen,
                        a1.tags as row_tags,
                        COALESCE(a2.packets, 0) as reverse_packets,
                        COALESCE(a2.bytes, 0) as reverse_bytes,
                        COALESCE(a2.times_seen, 0) as reverse_seen
                    FROM allflows a1
                    LEFT JOIN allflows a2 ON 
                        a2.src_ip = a1.dst_ip 
                        AND a2.dst_ip = a1.src_ip
                        AND a2.src_port = a1.dst_port
                        AND a2.dst_port = a1.src_port
                        AND a2.protocol = a1.protocol
                )
                SELECT 
                    initiator_ip,
                    responder_ip,
                    responder_port,
                    forward_packets,
                    reverse_packets,
                    connection_protocol,
                    row_tags,
                    COUNT(*) as connection_count,
                    sum(forward_packets) as f_packets,
                    sum(reverse_packets) as r_packets
                FROM ConnectionPairs
                WHERE connection_protocol IN (6)  -- Exclude ICMP and IGMP
                AND row_tags not like '%DeadConnectionDetection%'
                AND responder_ip NOT LIKE '224%'  -- Exclude multicast
                AND responder_ip NOT LIKE '239%'  -- Exclude multicast
                AND responder_ip NOT LIKE '255%'  -- Exclude broadcast
                GROUP BY initiator_ip, responder_ip, responder_port, connection_protocol
                HAVING 
                    f_packets > 2
                    AND r_packets < 1
        """)
        
        rows = cursor.fetchall()
            
        log_info(logger, f"[INFO] Identified {len(rows)} potential dead connections.")
        return rows
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while querying dead connections: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while querying dead connections: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)