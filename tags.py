from utils import log_info, log_error
import logging




def tag_whitelist(row, whitelist_entries):
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
        return False

    src_ip, dst_ip, src_port, dst_port, protocol = row[0:5]

    #log_info(logger, f"[INFO] Checking whitelist for src_ip: {src_ip}, dst_ip: {dst_ip}, src_port: {src_port}, dst_port: {dst_port}, protocol: {protocol}")

    for whitelist_id, whitelist_src_ip, whitelist_dst_ip, whitelist_dst_port, whitelist_protocol in whitelist_entries:
        #log_info(logger, f"[INFO] Checking against whitelist entry: {whitelist_id}, src_ip: {whitelist_src_ip}, dst_ip: {whitelist_dst_ip}, dst_port: {whitelist_dst_port}, protocol: {whitelist_protocol}")
        # Check if the flow matches any whitelist entry
        src_match = (whitelist_src_ip == src_ip or whitelist_src_ip == dst_ip or whitelist_src_ip == "*")
        dst_match = (whitelist_dst_ip == dst_ip or whitelist_dst_ip == src_ip or whitelist_dst_ip == "*")
        port_match = ((int(whitelist_dst_port) in (src_port, dst_port)) or whitelist_dst_port == "*")
        protocol_match = ((int(whitelist_protocol) == protocol) or (whitelist_protocol == "*"))

        if src_match and dst_match and port_match and protocol_match:
            #log_info(logger, f"[INFO] Row is whitelisted with ID: {whitelist_id}")
            return f"whitelist;whitelist_{whitelist_id}"
    
    #log_info(logger, "[INFO] Row is not whitelisted")
    return None

def apply_tags(rows, whitelist_entries):
    """
    Apply multiple tagging functions to one or more rows. For each row, append the tag to the tags position.

    Args:
        rows: A single flow record or a list of flow records.
        whitelist_entries: List of whitelist entries from the database.

    Returns:
        list: The same number of rows as input, with tags appended to the tags position of each row.
    """

    for row in rows:
        # Call tag_whitelist and append the tag if it exists
        tag = tag_whitelist(row, whitelist_entries)
        if tag:
            row[11] += f";{tag}"


    return rows
