import socket
import struct
from const import CONST_COLLECTOR_LISTEN_ADDRESS, CONST_COLLECTOR_LISTEN_PORT, IS_CONTAINER, CONST_NEWFLOWS_DB
import os
from utils import log_info, log_warn, log_error
import logging
from datetime import datetime, timezone
from database import connect_to_db, get_whitelist
from tags import apply_tags

if (IS_CONTAINER):
    COLLECTOR_LISTEN_ADDRESS=os.getenv("COLLECTOR_LISTEN_ADDRESS", CONST_COLLECTOR_LISTEN_ADDRESS)
    COLLECTOR_LISTEN_PORT=os.getenv("COLLECTOR_LISTEN_PORT", CONST_COLLECTOR_LISTEN_PORT) 


# Update or insert flow in the DB
def update_newflow(record):
    conn = connect_to_db(CONST_NEWFLOWS_DB)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    c.execute('''
        INSERT INTO flows (
            src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes, flow_start, flow_end, last_seen, times_seen, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,?)
        ON CONFLICT(src_ip, dst_ip, src_port, dst_port, protocol)
        DO UPDATE SET 
            packets = packets + excluded.packets,
            bytes = bytes + excluded.bytes,
            flow_end = excluded.flow_end,
            last_seen = excluded.last_seen,
            times_seen = times_seen + 1
    ''', (record['src_ip'], record['dst_ip'], record['src_port'], record['dst_port'],record['protocol'], record['packets'], record['bytes'], record['flow_start'], record['flow_end'], now,  record['tags']))

    conn.commit()
    conn.close()

def parse_netflow_v5_header(data):
    # Unpack the header into its individual fields
    return struct.unpack('!HHIIIIBBH', data[:24])


def parse_netflow_v5_record(data, offset):
    fields = struct.unpack('!IIIHHIIIIHHBBBBHHBBH', data[offset:offset+48])
    length = len(fields)
 
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
        'tags': None,
        'last_seen': datetime.now().isoformat(),
        'times_seen': 1
    }


# Main NetFlow v5 processing loop
def handle_netflow_v5():
    logger = logging.getLogger(__name__)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((COLLECTOR_LISTEN_ADDRESS, COLLECTOR_LISTEN_PORT))
        log_info(logger, f"[INFO] NetFlow v5 collector listening on {COLLECTOR_LISTEN_ADDRESS}:{COLLECTOR_LISTEN_PORT}")

        while True:
            whitelist = get_whitelist()
            flow_count = 0  # Initialize a counter for the number of flows processed
            data, addr = s.recvfrom(8192)
            try:
                if len(data) < 24:
                    log_warn(logger, "[WARN] Packet too short for NetFlow v5 header")
                    continue

                # Parse NetFlow v5 header
                version, count, sys_uptime, unix_secs, unix_nsecs, flow_sequence, engine_type, engine_id, sampling_interval = parse_netflow_v5_header(data)

                if version != 5:
                    log_warn(logger, f"[WARN] Unsupported NetFlow version: {version}")
                    continue

                offset = 24
                for _ in range(count):
                    if offset + 48 > len(data):
                        break

                    record = parse_netflow_v5_record(data, offset)

                    offset += 48

                    # Convert flow times to UTC with timezone awareness
                    flow_start = datetime.fromtimestamp(
                        unix_secs - ((sys_uptime - record['start_time']) / 1000),
                        tz=timezone.utc
                    ).isoformat()
                    
                    flow_end = datetime.fromtimestamp(
                        unix_secs - ((sys_uptime - record['end_time']) / 1000),
                        tz=timezone.utc
                    ).isoformat()
                    
                    record = apply_tags(record, whitelist)

                    update_newflow(record)

                    flow_count += 1  # Increment the flow counter

                # Log the number of flows processed in this packet
                log_info(logger, f"[INFO] Processed {count} flows from packet. Total flows processed: {flow_count}")

            except Exception as e:
                log_error(logger, f"[ERROR] Failed to process NetFlow v5 packet: {e}")