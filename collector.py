import sqlite3
import socket
import struct
from datetime import datetime
from const import VERSION, LISTEN_ON_ADDRESS, LISTEN_ON_PORT
import logging
import threading

DB_NAME = 'rawflows.db'
HOST = LISTEN_ON_ADDRESS
PORT = LISTEN_ON_PORT

# Consolidated logging function
def log_info(logger, message):
    print(message)
    logger.info(message)

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

# Parse IPFIX (NetFlow v10) record
def parse_record(data, templates):
    """
    Parse an IPFIX (NetFlow v10) record.
    
    Args:
        data (bytes): The raw data received from the socket.
        templates (dict): A dictionary to store and retrieve IPFIX templates.

    Returns:
        list: A list of parsed flow records, or None if parsing fails.
    """
    try:
        # IPFIX Header (20 bytes)
        if len(data) < 20:
            return None  # Invalid record length
        version, length, export_time, sequence_number, observation_domain_id = struct.unpack('!HHIII', data[:16])
        
        if version != 10:
            raise ValueError(f"Unsupported NetFlow version: {version}")

        # Process the remaining data
        offset = 16
        records = []

        while offset < length:
            set_id, set_length = struct.unpack('!HH', data[offset:offset + 4])
            offset += 4

            if set_id == 2:  # Template Set
                while offset < length:
                    template_id, field_count = struct.unpack('!HH', data[offset:offset + 4])
                    offset += 4
                    fields = []
                    for _ in range(field_count):
                        field_type, field_length = struct.unpack('!HH', data[offset:offset + 4])
                        offset += 4
                        fields.append((field_type, field_length))
                    templates[template_id] = fields

            elif set_id > 255:  # Data Set
                template_id = set_id
                if template_id not in templates:
                    raise ValueError(f"Template ID {template_id} not found")

                template = templates[template_id]
                while offset < length:
                    record = {}
                    for field_type, field_length in template:
                        field_value = data[offset:offset + field_length]
                        offset += field_length
                        record[field_type] = field_value
                    records.append(record)

            else:
                # Skip unsupported set types
                offset += set_length - 4

        return records

    except Exception as e:
        print(f"[ERROR] Failed to parse IPFIX record: {e}")
        return None

# Handle incoming UDP datagrams
def handle_datagrams():
    logger = logging.getLogger(__name__)
    templates = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((HOST, PORT))
        log_info(logger, f"[INFO] NetFlow daemon listening on {HOST}:{PORT}")

        while True:
            data, addr = s.recvfrom(2048)
            records = parse_record(data, templates)
            if records:
                for record in records:
                    # Extract fields from the record and update the database
                    src_ip = record.get(8)  # Example field type for src_ip
                    dst_ip = record.get(12)  # Example field type for dst_ip
                    src_port = int.from_bytes(record.get(7), 'big')  # Example field type for src_port
                    dst_port = int.from_bytes(record.get(11), 'big')  # Example field type for dst_port
                    protocol = int.from_bytes(record.get(4), 'big')  # Example field type for protocol
                    packets = int.from_bytes(record.get(2), 'big')  # Example field type for packets
                    bytes_ = int.from_bytes(record.get(1), 'big')  # Example field type for bytes
                    flow_start = datetime.utcfromtimestamp(int.from_bytes(record.get(22), 'big')).isoformat()
                    flow_end = datetime.utcfromtimestamp(int.from_bytes(record.get(23), 'big')).isoformat()
                    update_flow(src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes_, flow_start, flow_end)
                    log_info(logger, f"[INFO] Updated flow: {record}")

if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    log_info(logger, f"[INFO] I am softflowips collector {VERSION}")
    init_db()
    handle_datagrams()
