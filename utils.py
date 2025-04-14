import logging
import ipaddress

def log_info(logger, message):
    """Log a message and print it to the console."""
    print(message)
    if logger:
        logger.info(message)

def is_ip_in_range(ip, ranges):
    """Check if an IP address is within the specified ranges."""
    for ip_range in ranges:
        if ipaddress.ip_address(ip) in ipaddress.ip_network(ip_range):
            return True
    return False