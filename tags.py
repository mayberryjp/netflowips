from utils import log_info, log_error, dump_json, log_warn, calculate_broadcast
import logging




def tag_whitelist(record, whitelist_entries):
    """
    Check if a single row matches any whitelist entry.

    Args:
        row: A single flow record
        whitelist_entries: List of whitelist entries from database

    Returns:
        bool: True if the row matches a whitelist entry, False otherwise
    """
    logger = logging.getLogger(__name__)
    #log_info(logger, "[INFO] Checking if the row is whitelisted")

    if not whitelist_entries:
        return None

   # src_ip, dst_ip, src_port, dst_port, protocol, *_ = row

    #log_info(logger, f"[INFO] Checking whitelist for src_ip: {src_ip}, dst_ip: {dst_ip}, src_port: {src_port}, dst_port: {dst_port}, protocol: {protocol}")

    for whitelist_id, whitelist_src_ip, whitelist_dst_ip, whitelist_dst_port, whitelist_protocol in whitelist_entries:
        #log_info(logger, f"[INFO] Checking against whitelist entry: {whitelist_id}, src_ip: {whitelist_src_ip}, dst_ip: {whitelist_dst_ip}, dst_port: {whitelist_dst_port}, protocol: {whitelist_protocol}")
        # Check if the flow matches any whitelist entry
        src_match = (whitelist_src_ip == record['src_ip'] or whitelist_src_ip == record['dst_ip'] or whitelist_src_ip == "*")
        dst_match = (whitelist_dst_ip == record['dst_ip'] or whitelist_dst_ip == record['src_ip'] or whitelist_dst_ip == "*")
        port_match = ((int(whitelist_dst_port) in (record['src_port'], record['dst_port'])) or whitelist_dst_port == "*")
        protocol_match = ((int(whitelist_protocol) == record['protocol']) or (whitelist_protocol == "*"))

        if src_match and dst_match and port_match and protocol_match:
            #log_info(logger, f"[INFO] Row is whitelisted with ID: {whitelist_id}")
            return f"IgnoreList;IgnoreList_{whitelist_id};"
    
    #log_info(logger, "[INFO] Row is not whitelisted")
    return None

def tag_broadcast(record, broadcast_addresses):
    """
    Remove flows where the destination IP matches broadcast addresses of LOCAL_NETWORKS.
    
    Args:
        rows: List of flow records
        config_dict: Dictionary containing configuration settings
        
    Returns:
        list: Filtered rows with broadcast destination addresses removed
    """
    logger = logging.getLogger(__name__)

    if not broadcast_addresses:
        log_warn(logger, "[WARN] No broadcast addresses found for LOCAL_NETWORKS")
        return None

    if record["dst_ip"] not in broadcast_addresses:
        return None
    else:
        return "Broadcast;"
    

def tag_multicast(record):
    """
    Tag flows where the destination IP is in multicast range (224.0.0.0 to 239.255.255.255).
    
    Args:
        record: Flow record to check
        broadcast_addresses: List of broadcast addresses (not used but kept for consistency)
        
    Returns:
        str: "Multicast;" if destination IP is multicast, None otherwise
    """
    logger = logging.getLogger(__name__)

    try:
        # Get first octet of destination IP
        first_octet = int(record["dst_ip"].split('.')[0])
        
        # Check if in multicast range (224-239)
        if 224 <= first_octet <= 239:
            return "Multicast;"
        return None
        
    except (ValueError, IndexError) as e:
        log_error(logger, f"[ERROR] Invalid IP address format in record: {e}")
        return None
    

def apply_tags(record, whitelist_entries, broadcast_addresses):
    """
    Apply multiple tagging functions to one or more rows. For each row, append the tag to the tags position.

    Args:
        rows: A single flow record or a list of flow records.
        whitelist_entries: List of whitelist entries from the database.

    Returns:
        list: The same number of rows as input, with tags appended to the tags position of each row.
    """

    whitelist_tag = tag_whitelist(record, whitelist_entries)
    if whitelist_tag:
        record['tags'] += f"{whitelist_tag}"

    broadcast_tag = tag_broadcast(record, broadcast_addresses)
    if broadcast_tag:
        record['tags'] += f"{broadcast_tag}"

    multicast_tag = tag_multicast(record)
    if multicast_tag:
        record['tags'] += f"{multicast_tag}"

    return record
