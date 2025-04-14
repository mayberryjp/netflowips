import sqlite3
import socket
import struct
import logging
from datetime import datetime
from const import VERSION, CONST_LISTEN_ADDRESS, CONST_LISTEN_PORT, IS_CONTAINER
import os
from utils import log_info

if (IS_CONTAINER):
    LISTEN_ADDRESS=os.getenv("LISTEN_ADDRESS", CONST_LISTEN_ADDRESS)
    LISTEN_PORT=os.getenv("LISTEN_PORT", CONST_LISTEN_PORT) 

DB_NAME = 'newflows.db'

def delete_newflowsdb():
    """
    Deletes a file at the given path if it exists.

    Args:
        file_path (str): The full path to the file to be deleted.
    """
    try:
        if os.path.exists(DB_NAME):
            os.remove(DB_NAME)
            print(f"[INFO] Deleted: {DB_NAME}")
        else:
            print("[WARN] File does not exist.")
    except Exception as e:
        print(f"[ERROR] Error deleting file: {e}")




# Initialize the database
def init_db():
    conn = sqlite3.connect(DB_NAME)
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

# Update or insert flow in the DB
def update_flow(src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()

    c.execute('''
        INSERT INTO flows (
            src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes, flow_start, flow_end, last_seen, times_seen
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(src_ip, dst_ip, src_port, dst_port, protocol)
        DO UPDATE SET 
            packets = packets + excluded.packets,
            bytes = bytes + excluded.bytes,
            flow_end = excluded.flow_end,
            last_seen = excluded.last_seen,
            times_seen = excluded.times_seen + 1
    ''', (src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, now))

    conn.commit()
    conn.close()

def parse_netflow_v5_header(data):
    # Unpack the header into its individual fields
    return struct.unpack('!HHIIIIBBH', data[:24])


def parse_netflow_v5_record(data, offset):
    fields = struct.unpack('!IIIHHIIIIHHBBBBHHBBH', data[offset:offset+48])
    length = len(fields)
    #for i in range(0, length):
   #     print(f"{fields[i]}")

 #   print(f"src ip: {socket.inet_ntoa(struct.pack('!I', fields[0]))} dst ip: {socket.inet_ntoa(struct.pack('!I', fields[1]))} src port: {fields[9]} dst port: {fields[10]} protocol: {fields[13]} packets: {fields[5]} bytes: {fields[6]}")
    return {
        'src_ip': socket.inet_ntoa(struct.pack('!I', fields[0])),
        'dst_ip': socket.inet_ntoa(struct.pack('!I', fields[1])),
        'nexthop': socket.inet_ntoa(struct.pack('!I', fields[2])),
        'input_iface': fields[3],
        'output_iface': fields[4],
        'packets': fields[5],
        'bytes': fields[6],
        'start_time': fields[7],
        'end_time': fields[8],
        'src_port': fields[9],
        'dst_port': fields[10],
        'tcp_flags': fields[11],
        'protocol': fields[13],
        'tos': fields[12],
        'src_as': fields[14],
        'dst_as': fields[15],
        'src_mask': fields[16],
        'dst_mask': fields[17],
    }


# Main NetFlow v5 processing loop
def handle_netflow_v5():
    logger = logging.getLogger(__name__)


    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((LISTEN_ADDRESS, LISTEN_PORT))
        log_info(logger, f"[INFO] NetFlow v5 collector listening on {LISTEN_ADDRESS}:{LISTEN_PORT}")

        while True:
            flow_count = 0  # Initialize a counter for the number of flows processed
            data, addr = s.recvfrom(8192)
            try:
                if len(data) < 24:
                    log_info(logger, "[WARNING] Packet too short for NetFlow v5 header")
                    continue

                # Parse NetFlow v5 header
                version, count, sys_uptime, unix_secs, unix_nsecs, flow_sequence, engine_type, engine_id, sampling_interval = parse_netflow_v5_header(data)

                if version != 5:
                    log_info(logger, f"[WARNING] Unsupported NetFlow version: {version}")
                    continue

                offset = 24
                for _ in range(count):
                    if offset + 48 > len(data):
                        break

                    record = parse_netflow_v5_record(data, offset)
                    offset += 48

                    # Convert flow times to UTC
                    flow_start = datetime.utcfromtimestamp(unix_secs - ((sys_uptime - record['start_time']) / 1000)).isoformat()
                    flow_end = datetime.utcfromtimestamp(unix_secs - ((sys_uptime - record['end_time']) / 1000)).isoformat()

                    update_flow(
                        record['src_ip'],
                        record['dst_ip'],
                        record['src_port'],
                        record['dst_port'],
                        record['protocol'],
                        record['packets'],
                        record['bytes'],
                        flow_start,
                        flow_end
                    )

                    flow_count += 1  # Increment the flow counter

                # Log the number of flows processed in this packet
                log_info(logger, f"[INFO] Processed {count} flows from packet. Total flows processed: {flow_count}")

            except Exception as e:
                log_info(logger, f"[ERROR] Failed to process NetFlow v5 packet: {e}")

# Entry point
if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    log_info(logger, f"[INFO] Starting NetFlow v5 collector {VERSION}")
    delete_newflowsdb()
    init_db()
    handle_netflow_v5()
