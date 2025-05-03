import logging
import ipaddress
import json
import socket
import struct
from datetime import datetime
from ipaddress import IPv4Network
import sys
import os
import traceback
import uuid
import hashlib
from const import IS_CONTAINER, CONST_SITE
from config import get_config_settings_detached

if (IS_CONTAINER):
    SITE = os.getenv("SITE", CONST_SITE)

def log_info(logger, message):

    """Log a message and print it to the console with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    script_name = os.path.basename(sys.argv[0])
    formatted_message = f"[{timestamp}] {script_name} {message}"
    print(formatted_message)
    logger.info(formatted_message)

def log_error(logger, message):
    """Log a message and print it to the console with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    script_name = os.path.basename(sys.argv[0])
    # Get the current line number from the traceback
    tb = traceback.extract_tb(sys.exc_info()[2])
    if tb:
        # Get the last frame in the traceback (where the error occurred)
        last_frame = tb[-1]
        file_name = os.path.basename(last_frame.filename)
        line_number = last_frame.lineno
    else:
        file_name = script_name
        line_number = "N/A"
    formatted_message = f"[{timestamp}] {script_name}[/{file_name}/{line_number}] {message}"
    print(formatted_message)
    logger.error(formatted_message)

    config_dict = get_config_settings_detached()

    if config_dict['SendErrorsToCloudApi']  == 1:
        # Send the error message to the cloud API
        try:
            import requests
            url = f"https://api.homelabids.com/errorreport/{config_dict['MachineUniqueIdentifier']}"  # Replace with your API endpoint
            payload = {
                "error_message": message,
                "script_name": script_name,
                "file_name": file_name,
                "timestamp": timestamp,
                "site": SITE,
                "line_number": line_number,
                "machine_unique_identiifer": config_dict['MachineUniqueIdentifier']
            }
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                log_info(logger, "[INFO] Error reported to cloud API successfully.")
            else:
                log_warn(logger, f"[WARN] Failed to report error to cloud API: {response.status_code}")
        except Exception as e:
            log_warn(logger, f"[WARN] Failed to send error report to cloud API: {e}")

    if SITE == 'TESTPPE':
        exit(1)

def log_warn(logger, message):
    """Log a message and print it to the console with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    script_name = os.path.basename(sys.argv[0])
    formatted_message = f"[{timestamp}] {script_name} {message}"
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

def calculate_broadcast(network_cidr):
    """
    Calculate broadcast address from CIDR notation.
    
    Args:
        network_cidr (str): Network in CIDR notation (e.g., '192.168.1.0/24')
    
    Returns:
        str: Broadcast address or None if invalid input
        
    Example:
        >>> calculate_broadcast('192.168.1.0/24')
        '192.168.1.255'
        >>> calculate_broadcast('10.0.0.0/8')
        '10.255.255.255'
    """
    logger = logging.getLogger(__name__)
    try:
        # Parse CIDR notation
        network = ipaddress.IPv4Network(network_cidr, strict=False)
        broadcast = str(network.broadcast_address)
        
        log_info(logger, f"[INFO] Calculated broadcast {broadcast} for network {network_cidr}")
        return broadcast
        
    except ValueError as e:
        log_error(logger, f"[ERROR] Invalid CIDR format {network_cidr}: {e}")
        return None
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to calculate broadcast address: {e}")
        return None

def get_machine_unique_identifier():
    """
    Generate a unique identifier for the machine based on its hardware (e.g., MAC address).

    Returns:
        str: A unique identifier as a hexadecimal string.
    """
    logger = logging.getLogger(__name__)
    try:
        # Get the MAC address of the machine
        mac_address = uuid.getnode()

        if mac_address == uuid.getnode():
            log_info(logger, f"[INFO] Retrieved MAC address: {mac_address}")

        # Convert the MAC address to a hashed unique identifier
        unique_id = hashlib.sha256(str(mac_address).encode('utf-8')).hexdigest()

        log_info(logger, f"[INFO] Generated unique identifier: {unique_id}")
        return unique_id
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to generate machine unique identifier: {e}")
        return None


