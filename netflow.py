import socket
import struct
from const import CONST_COLLECTOR_LISTEN_ADDRESS, CONST_COLLECTOR_LISTEN_PORT, IS_CONTAINER, CONST_CONSOLIDATED_DB
import os
from utils import log_info, log_warn, log_error, calculate_broadcast
import logging
from datetime import datetime, timezone
from database import connect_to_db, get_whitelist, get_config_settings
from tags import apply_tags
from queue import Queue
import threading
import time
import json

if (IS_CONTAINER):
    COLLECTOR_LISTEN_ADDRESS=os.getenv("COLLECTOR_LISTEN_ADDRESS", CONST_COLLECTOR_LISTEN_ADDRESS)
    COLLECTOR_LISTEN_PORT=os.getenv("COLLECTOR_LISTEN_PORT", CONST_COLLECTOR_LISTEN_PORT) 

# Create global queue for netflow packets
netflow_queue = Queue()

# Update or insert flow in the DB
def update_newflow(record):
    conn = connect_to_db(CONST_CONSOLIDATED_DB)
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
    ''', (record['src_ip'], record['dst_ip'], record['src_port'], record['dst_port'],record['protocol'], record['packets'], record['bytes'], record['start_time'], record['end_time'], now,  record['tags']))

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
        'tags': "",
        'last_seen': datetime.now().isoformat(),
        'times_seen': 1
    }

def collect_netflow_packets(listen_address, listen_port):
    """Collect packets and add them to queue"""
    logger = logging.getLogger(__name__)
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((listen_address, listen_port))
        log_info(logger, f"[INFO] NetFlow v5 collector listening on {listen_address}:{listen_port}")
        
        while True:
            try:
                data, addr = s.recvfrom(8192)
                netflow_queue.put((data, addr))
            except Exception as e:
                log_error(logger, f"[ERROR] Socket error: {e}")
                time.sleep(1)

def process_netflow_packets():
    """Process queued packets at fixed interval"""
    logger = logging.getLogger(__name__)
    
    while True:
        try:
            whitelist = get_whitelist()
            config_dict = get_config_settings()

            if not config_dict:
                log_error(logger, "[ERROR] Failed to load configuration settings")
                time.sleep(60)  # Wait before retry
                continue

            tag_entries_json = config_dict.get("TagEntries", "[]")
            tag_entries = json.loads(tag_entries_json)

            LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))
            
            # Calculate broadcast addresses for all local networks
            broadcast_addresses = set()
            for network in LOCAL_NETWORKS:
                broadcast_ip = calculate_broadcast(network)
                if broadcast_ip:
                    broadcast_addresses.add(broadcast_ip)
                    #log_info(logger, f"[INFO] Found broadcast address {broadcast_ip} for network {network}")
            
            # Add global broadcast address
            broadcast_addresses.add('255.255.255.255')
            
            packets = []
            # Collect all available packets
            while not netflow_queue.empty():
                packets.append(netflow_queue.get())
                
            if packets:
                log_info(logger, f"[INFO] Processing {len(packets)} queued packets")
                total_flows = 0
                
                for data, addr in packets:
                    if len(data) < 24:
                        continue
                        
                    version, count, *header_fields = parse_netflow_v5_header(data)
                    if version != 5:
                        continue
                        
                    offset = 24
                    for _ in range(count):
                        if offset + 48 > len(data):
                            break
                            
                        record = parse_netflow_v5_record(data, offset)
                        offset += 48
                        
                        # Apply tags and update flow database
                        record = apply_tags(record, whitelist, broadcast_addresses, tag_entries, config_dict)
                        update_newflow(record)
                        total_flows += 1
                        
                log_info(logger, f"[INFO] Processed {total_flows} flows from {len(packets)} packets")
                
            # Wait for next processing interval
            interval = int(config_dict.get('CollectorProcessingInterval', 60))
            time.sleep(interval)
            
        except Exception as e:
            log_error(logger, f"[ERROR] Failed to process NetFlow packets: {e}")
            time.sleep(60)  # Wait before retry

def handle_netflow_v5():
    """Start collector and processor threads"""
    logger = logging.getLogger(__name__)
    
    # Start collector thread
    collector = threading.Thread(
        target=collect_netflow_packets,
        args=(COLLECTOR_LISTEN_ADDRESS, COLLECTOR_LISTEN_PORT),
        daemon=True
    )
    collector.start()
    
    # Run processor in main thread
    process_netflow_packets()