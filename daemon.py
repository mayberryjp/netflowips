import sqlite3
import socket
import struct
from datetime import datetime
import threading

DB_NAME = 'netflow.db'
HOST = '0.0.0.0'
PORT = 2055  # Default port for softflowd; adjust as needed

# Initialize the SQLite DB
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
            PRIMARY KEY (src_ip, dst_ip, src_port, dst_port, protocol)
        )
    ''')
    conn.commit()
    conn.close()

# Update flow in the database
def update_flow(src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()

    c.execute('''
        INSERT INTO flows (src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes, flow_start, flow_end, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(src_ip, dst_ip, src_port, dst_port, protocol)
        DO UPDATE SET 
            packets = packets + excluded.packets,
            bytes = bytes + excluded.bytes,
            flow_end = excluded.flow_end,
            last_seen = excluded.last_seen
    ''', (src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end, now))

    conn.commit()
    conn.close()

# Parse Softflowd record
def parse_record(data):
    if len(data) < 48:
        return None  # Invalid record length
    try:
        src_ip = socket.inet_ntoa(data[0:4])
        dst_ip = socket.inet_ntoa(data[4:8])
        src_port, dst_port, protocol, packets, bytes_ = struct.unpack('!HHHHH', data[8:18])
        flow_start = datetime.utcfromtimestamp(struct.unpack('!I', data[18:22])[0]).isoformat()
        flow_end = datetime.utcfromtimestamp(struct.unpack('!I', data[22:26])[0]).isoformat()
        return (src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end)
    except Exception as e:
        print(f"[ERROR] Failed to parse record: {e}")
        return None

# Handle incoming UDP datagrams
def handle_datagrams():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((HOST, PORT))
        print(f"NetFlow daemon listening on {HOST}:{PORT}")
        while True:
            data, addr = s.recvfrom(2048)
            record = parse_record(data)
            if record:
                update_flow(*record)

if __name__ == "__main__":
    init_db()
    handle_datagrams()
