import logging
import ipaddress
from datetime import datetime

def log_info(logger, message):
    """Log a message and print it to the console with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    formatted_message = f"[{timestamp}] {message}"
    print(formatted_message)
    logger=logger or logging.getLogger(__name__)
    logger.info(formatted_message)
    

def is_ip_in_range(ip, ranges):
    """Check if an IP address is within the specified ranges."""
    try:
        for ip_range in ranges:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(ip_range):
                return True
        return False
    except ValueError as e:
        log_info(None, f"[ERROR] Invalid IP address or range: {e}")
        return False