from src.utils import log_error, log_warn
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
    

def tag_custom(record, tag_entries):
    """
    Apply custom tags to flows based on matching criteria similar to whitelisting.
    
    Args:
        record: Flow record to check
        tag_entries: List of tag entries in format [tag_name, tag_src_ip, tag_dst_ip, tag_dst_port, tag_protocol]
        
    Returns:
        str: Custom tags to be applied or None if no matches
    """
    logger = logging.getLogger(__name__)
    
    if not tag_entries:
        return None
    
    applied_tags = []
    
    for tag_name, tag_src_ip, tag_dst_ip, tag_dst_port, tag_protocol in tag_entries:
        try:
            # Check for matches using wildcard pattern similar to whitelist
            src_match = (tag_src_ip == record['src_ip'] or tag_src_ip == record['dst_ip'] or tag_src_ip == "*")
            dst_match = (tag_dst_ip == record['dst_ip'] or tag_dst_ip == record['src_ip'] or tag_dst_ip == "*")
            
            # Port check - handle string conversion for wildcard
            port_match = (tag_dst_port == "*" or 
                         int(tag_dst_port) in (record['src_port'], record['dst_port']))
            
            # Protocol check - handle string conversion for wildcard
            protocol_match = (tag_protocol == "*" or 
                             int(tag_protocol) == record['protocol'])
            
            # If all criteria match, add the tag
            if src_match and dst_match and port_match and protocol_match:
                applied_tags.append(f"{tag_name};")
                #log_info(logger, f"[INFO] Custom tag '{tag_name}' applied to flow: {record['src_ip']} -> {record['dst_ip']}:{record['dst_port']}")
                
        except (ValueError, KeyError, TypeError) as e:
            log_error(logger, f"[ERROR] Error applying custom tag: {e}")
    
    # Return all matched tags as a single string
    if applied_tags:
        return "".join(applied_tags)
    return None
    
def apply_tags(record, whitelist_entries, broadcast_addresses, tag_entries, config_dict):
    """
    Apply multiple tagging functions to one or more rows. For each row, append the tag to the tags position.

    Args:
        record: Flow record to tag
        whitelist_entries: List of whitelist entries from the database
        broadcast_addresses: Set of broadcast addresses
        tag_entries: List of custom tag entries

    Returns:
        record: Updated record with tags
    """
    # Initialize tags if not present
    if 'tags' not in record:
        record['tags'] = ""

    # Apply existing tags
    if whitelist_entries:
        whitelist_tag = tag_whitelist(record, whitelist_entries)
        if whitelist_tag:
            record['tags'] += f"{whitelist_tag}"

    broadcast_tag = tag_broadcast(record, broadcast_addresses)
    if broadcast_tag:
        record['tags'] += f"{broadcast_tag}"

    multicast_tag = tag_multicast(record)
    if multicast_tag:
        record['tags'] += f"{multicast_tag}"
        
    if config_dict.get("AlertOnCustomTags", 0) > 0:
        # Apply custom tags
        if tag_entries:
            custom_tags = tag_custom(record, tag_entries)
            if custom_tags:
                record['tags'] += custom_tags

    return record

