import logging
import ipaddress
import json
import socket
import struct
from datetime import datetime
from ipaddress import IPv4Network


def log_info(logger, message):
    """Log a message and print it to the console with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    formatted_message = f"[{timestamp}] {message}"
    print(formatted_message)
    logger.info(formatted_message)

def log_error(logger, message):
    """Log a message and print it to the console with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    formatted_message = f"[{timestamp}] {message}"
    print(formatted_message)
    logger.error(formatted_message)

def log_warn(logger, message):
    """Log a message and print it to the console with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    formatted_message = f"[{timestamp}] {message}"
    print(formatted_message)
    logger.warn(formatted_message)

def is_ip_in_range(ip, ranges):
    """Check if an IP address is within the specified ranges."""
    logger = logging.getLogger(__name__)
    try:
        for ip_range in ranges:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(ip_range):
                return True
        return False
    except ValueError as e:
        log_error(logger, f"[ERROR] Invalid IP address or range: {e}")
        return False

def ip_network_to_range(network):
    logger = logging.getLogger(__name__)
    """
    Convert a CIDR network to start and end IP addresses as integers using inet_aton.
    
    Args:
        network (str): Network in CIDR notation (e.g., '192.168.1.0/24')
    
    Returns:
        tuple: (start_ip, end_ip, netmask) as integers
    """
    try:
        net = IPv4Network(network)
        # Convert IP addresses to integers using inet_aton and struct.unpack
        start_ip = struct.unpack('!L', socket.inet_aton(str(net.network_address)))[0]
        end_ip = struct.unpack('!L', socket.inet_aton(str(net.broadcast_address)))[0]
        netmask = struct.unpack('!L', socket.inet_aton(str(net.netmask)))[0]
        
        return start_ip, end_ip, netmask
    except Exception as e:
        log_warn(logger, f"[WARN] Invalid network format {network}: {e}")
        return None, None, None

def dump_json(obj):
    """
    Convert an object to a formatted JSON string.
    
    Args:
        obj: Any JSON-serializable object
        
    Returns:
        str: Pretty-printed JSON string or error message if serialization fails
    """
    logger = logging.getLogger(__name__)
    try:
        return json.dumps(obj, indent=2, sort_keys=True, default=str)
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to serialize object to JSON: {e}")
        return str(obj)
    
def ip_to_int(ip_addr):
    """Convert an IP address to an integer using inet_aton."""
    try:
        return struct.unpack('!L', socket.inet_aton(ip_addr))[0]
    except:
        return None

def get_usable_ips(networks):
    """
    Get a list of all usable IP addresses for multiple network ranges.

    Args:
        networks (list): A list of networks in CIDR notation (e.g., ['192.168.1.0/24', '10.0.0.0/8']).

    Returns:
        dict: A dictionary where the keys are the networks and the values are lists of usable IP addresses.
    """
    logger = logging.getLogger(__name__)
    results = {}

    for network in networks:
        try:
            net = IPv4Network(network, strict=False)
            # Exclude the network address and broadcast address
            usable_ips = [str(ip) for ip in net.hosts()]
            results[network] = usable_ips
            log_info(logger, f"[INFO] Found {len(usable_ips)} usable IPs in network {network}")
        except ValueError as e:
            log_error(logger, f"[ERROR] Invalid network format {network}: {e}")
            results[network] = []

    return results


