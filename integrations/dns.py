import dns.resolver
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
# Set up path for imports
current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

sys.path.insert(0, "/database")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from init import *


def dns_lookup(ip_addresses, dns_servers, config_dict):
    """
    Perform DNS lookup for a list of IP addresses using specific DNS servers.

    Args:
        ip_addresses (list): A list of IP addresses to perform DNS lookups on.
        dns_servers (list): A list of DNS servers to use for lookups (default is ['8.8.8.8']).

    Returns:
        dict: A dictionary where the keys are IP addresses and the values are the resolved hostnames or an error message.
    """
    logger = logging.getLogger(__name__)

    resolver_timeout = config_dict['DnsResolverTimeout'] if 'DnsResolverTimeout' in config_dict else 3
    resolver_retries = config_dict['DnsResolverRetries'] if 'DnsResolverRetries' in config_dict else 1
    
    log_info(logger,f"[INFO] DNS discovery starting")
    results = []
    resolver = dns.resolver.Resolver()
    log_info(logger,f"[INFO] DNS servers are {dns_servers}")
    resolver.nameservers = dns_servers  # Set the specific DNS servers
    resolver.timeout = resolver_timeout
    resolver.lifetime = resolver_retries

    count = 0
    total = len(ip_addresses)

    for ip in ip_addresses:

        try:
            # Perform reverse DNS lookup
            query = resolver.resolve_address(ip)
            hostname = str(query[0])  # Extract the hostname
            results.append({
                "ip": ip,
                "dns_hostname": hostname
            })

        except dns.resolver.NXDOMAIN:
            results.append({
                "ip": ip,
                "dns_hostname": "NXDOMAIN"
            })
            insert_action(f"You have an IP address without a reverse DNS entry. It is recommeneded to inventory all your local network devices in your local DNS. In Pi-hole, you can do this by going to Settings > Local DNS Records. Affected IP address is {ip}. DNS response was 'NXDOMAIN'.")
        except dns.resolver.Timeout:
            results.append({
                "ip": ip,
                "dns_hostname": "TIMEOUT"
            })
        except dns.resolver.NoNameservers:
            results.append({
                "ip": ip,
                "dns_hostname": "NONAMESERVER"
            })
        except Exception as e:
            results.append({
                "ip": ip,
                "dns_hostname": "ERROR"
            })

    log_info(logger,f"[INFO] DNS discovery finished")
    return results
