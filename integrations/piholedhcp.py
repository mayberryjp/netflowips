import requests
import logging
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import log_info, log_error

def authenticate_pihole(pihole_url, api_token):
    """
    Authenticate with the Pi-hole v6 API and retrieve a session ID.

    Args:
        pihole_url (str): The base URL of the Pi-hole instance (e.g., "http://192.168.1.2/admin").
        api_token (str): The API token for authenticating with the Pi-hole API.

    Returns:
        str: The session ID if authentication is successful, or None if it fails.
    """
    logger = logging.getLogger(__name__)

    endpoint = f"{pihole_url}/auth"
    payload = {"password": api_token}  # Send the password in the request body

    try:
        response = requests.post(endpoint, json=payload, timeout=10)  # Use JSON payload
        response.raise_for_status()
        data = response.json()

        # Extract the session ID from the response
        session_data = data.get("session", {})
        if session_data.get("valid", False):
            session_id = session_data.get("sid")
            log_info(logger, f"[INFO] Pihole Authentication successful.")
            return session_id
        else:
            log_error(logger, "[ERROR] Pihole Authentication failed: Invalid credentials")
            return None
    except requests.exceptions.RequestException as e:
        log_error(logger, f"[ERROR] Pihole Authentication failed: {e}")
        return None
    except ValueError:
        log_error(logger, "[ERROR] Pihole Failed to parse authentication response")
        return None


def get_pihole_dhcp_clients(existing_localhosts, config_dict):
    """
    Fetch the DHCP server client list from a Pi-hole v6 instance using the /network/devices API.

    Args:
        pihole_url (str): The base URL of the Pi-hole instance (e.g., "http://192.168.1.2/admin").
        session_id (str): The session ID obtained from the authentication step.

    Returns:
        list: A list of dictionaries containing processed DHCP client information, or an error message if the request fails.
    """
    logger = logging.getLogger(__name__)

    log_info(logger,f"[INFO] Pihole DHCP discovery starting")

    pihole_url = config_dict.get('PiholeUrl', None)
    api_token = config_dict.get('PiholeApiKey', None)

    if not pihole_url or not api_token:
        log_error(logger, "[ERROR] Pi-hole URL or API token not provided in configuration")
        return {"error": "Pi-hole URL or API token not provided"}

    session_id = authenticate_pihole(pihole_url, api_token)
    if not session_id:
        log_error(logger,"[ERROR] Pihole Authentication failed. Exiting.")

    endpoint = f"{pihole_url}/network/devices"
    headers = {"sid": f"{session_id}"}

    try:
        response = requests.get(endpoint, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

       # log_info(logger, f"[INFO] Received response from Pi-hole: {data}")
        devices = data.get("devices", [])
        processed_clients = []

        for device in devices:
            hwaddr = device.get("hwaddr", "Unknown")
            mac_vendor = device.get("macVendor", "Unknown")
            interface = device.get("interface", "Unknown")
            ips = device.get("ips", [])

            for ip_entry in ips:
                processed_clients.append({
                    "ip": ip_entry.get("ip", "Unknown"),
                    "hostname": ip_entry.get("name", "Unknown"),
                    "last_seen": ip_entry.get("lastSeen", "Unknown"),
                    "mac_address": hwaddr,
                    "mac_vendor": mac_vendor,
                    "interface": interface
                })

        return_hosts = []

        for host in existing_localhosts:
            for client in processed_clients:
                if host == client["ip"]:
                    return_hosts.append({
                        "ip": client["ip"],
                        "hostname": client["hostname"],
                        "mac_address": client["mac_address"],
                        "mac_vendor": client["mac_vendor"],
                    })

        log_info(logger,f"[INFO] Pihole DHCP discovery finished")

        return return_hosts

    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch DHCP client list: {e}"}
    except ValueError:
        return {"error": "Failed to parse JSON response from Pi-hole"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}
