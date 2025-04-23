import nmap
import os
import logging
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import log_info, log_error

def os_fingerprint(ip_addresses, config_dict):
    """
    Perform operating system fingerprinting for a list of IP addresses.

    Args:
        ip_addresses (list): A list of IP addresses to scan.

    Returns:
        dict: A dictionary where the keys are IP addresses and the values are the operating system fingerprint information.
    """
    logger = logging.getLogger(__name__)

    log_info(logger, f"[INFO] Nmap OS Fingerprinting starting")

    nmap_dir = r'C:\Program Files (x86)\Nmap'
    os.environ['PATH'] = nmap_dir + os.pathsep + os.environ['PATH']

    scanner = nmap.PortScanner()

    results = []

    for ip in ip_addresses:
        try:
            # Perform OS detection
            scan_result = scanner.scan(ip, arguments='-O')  # '-O' enables OS detection
            os_matches = scan_result['scan'].get(ip, {}).get('osmatch', [])
            
            if os_matches:
                # Use the highest match (first match in the list)
                best_match = os_matches[0]
                vendor = best_match.get('osclass', [{}])[0].get('vendor', 'Unknown')
                osfamily = best_match.get('osclass', [{}])[0].get('osfamily', 'Unknown')
                osgen = best_match.get('osclass', [{}])[0].get('osgen', 'Unknown')
                accuracy = best_match.get('accuracy', 'Unknown')

                results.append({
                    "ip": ip,
                    "os_fingerprint": f"{vendor}_{osfamily}_{osgen}_{accuracy}",
                })
            else:
                results.append({
                    "ip": ip,
                    "os_fingerprint": "No OS fingerprint detected",
                })
        except Exception as e:
            results.append({
                "ip": ip,
                "os_fingerprint": f"ERROR: {e}",
            })

    log_info(logger, f"[INFO] Nmap OS fingerprinting finished")

    return results
