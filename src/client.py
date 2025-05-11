import json
import sqlite3
from pathlib import Path
from enum import Enum
import logging
from datetime import datetime
import requests
from src.utils import log_info, log_error, log_warn
from src.database import get_machine_unique_identifier_from_db, get_localhosts, get_config_settings, connect_to_db, disconnect_from_db
from src.const import CONST_CONSOLIDATED_DB

class ActionType(Enum):
    """Placeholder for action types"""
    pass

def export_client_definition(client_ip):
    """
    Export client information to JSON format.
    Includes:
    - Host information
    - DNS query history with counts
    - Flow statistics with aggregated bytes/packets
    
    Args:
        client_ip (str): IP address of the client
    """
    logger = logging.getLogger(__name__)
    
    try:
        client_data = {
            "ip_address": client_ip,
            "export_date": datetime.now().isoformat(),
            "instance_identifier": get_machine_unique_identifier_from_db(),
            "host_info": None,
            "dns_queries": [],
            "flows": [],
            "actions": []
        }
        
        # Get host information from localhosts.db
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")
        localhosts_cursor = conn.cursor()
        localhosts_cursor.execute(
            "SELECT * FROM localhosts WHERE ip_address = ?", 
            (client_ip,)
        )
        host_record = localhosts_cursor.fetchone()
        if host_record:
            client_data["host_info"] = {
                "ip_address": host_record[0],
                "mac_address": host_record[3],
                "mac_vendor": host_record[4],
                "dhcp_hostname": host_record[5],
                "dns_hostname": host_record[6],
                "os_fingerprint": host_record[7],
                "lease_hostname": host_record[9],
                "icon": host_record[12],
                "local_description": host_record[8]
            }
        
        # Get DNS queries with counts from dnsqueries.db
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "pihole")
        dns_cursor = conn.cursor()
        dns_cursor.execute("""
            SELECT domain, sum(times_seen) as query_count, 
                   MAX(last_seen) as last_query,
                   MIN(first_seen) as first_query
            FROM pihole 
            WHERE client_ip = ?
            GROUP BY domain
            ORDER BY query_count DESC
        """, (client_ip,))
        
        client_data["dns_queries"] = [
            {
                "domain": row[0],
                "times_queried": row[1],
                "first_query": row[2],
                "last_query": row[3]
            }
            for row in dns_cursor.fetchall()
        ]
        
        # Get flows with aggregated statistics from allflows.db
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "allflows")
        flows_cursor = conn.cursor()
        flows_cursor.execute("""
            SELECT dst_ip, dst_port, protocol,
                   sum(times_seen) as flow_count,
                   SUM(packets) as total_packets,
                   SUM(bytes) as total_bytes,
                   MAX(last_seen) as last_flow,
                   MIN(flow_start) as first_flow
            FROM allflows 
            WHERE src_ip = ?
            GROUP BY dst_ip, dst_port, protocol
            ORDER BY total_bytes DESC
        """, (client_ip,))
        
        client_data["flows"] = [
            {
                "destination": row[0],
                "port": row[1],
                "protocol": row[2],
                "flow_count": row[3],
                "total_packets": row[4],
                "total_bytes": row[5],
                "first_seen": row[6],
                "last_seen": row[7]
            }
            for row in flows_cursor.fetchall()
        ]
        
        return client_data
        
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to export client definition for {client_ip}: {e}")
        return None
    finally:
        # Close all database connections
        for conn in [conn, conn, conn]:
            if 'conn' in locals() and conn:
                disconnect_from_db(conn)

def upload_client_definition(ip_address, client_data, machine_id):
    """
    Upload a single client definition to the classification API.
    
    Args:
        ip_address (str): IP address of the client
        client_data (dict): Client definition data to upload
        machine_id (str): Unique identifier for this machine
        
    Returns:
        bool: True if upload successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Construct API endpoint URL
        api_url = f"http://api.homelabids.com:8045/api/classification/{machine_id}/{ip_address}"
        
        # Upload client definition
        response = requests.put(
            api_url,
            json=client_data,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'NetFlowIPS-Client/1.0'
            },
            timeout=30
        )
        
        if response.status_code in (200, 201, 204):
            #log_info(logger, f"[INFO] Successfully uploaded client definition for {ip_address}")
            return True
        else:
            #log_error(logger, f"[ERROR] Failed to upload {ip_address}: HTTP {response.status_code}")
            return False
            
    except requests.RequestException as e:
        log_error(logger, f"[ERROR] Request failed for {ip_address}: {str(e)}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Processing failed for {ip_address}: {str(e)}")
        return False

def upload_all_client_definitions():
    """Get all IP addresses and upload client definitions"""
    logger = logging.getLogger(__name__)
    machine_id = get_machine_unique_identifier_from_db()
    
    try:
        # Get IPs as a set from get_localhosts()
        ip_addresses = get_localhosts()  
        success_count = 0
        error_count = 0
        
        # Debug log to verify data structure
        log_info(logger, f"[DEBUG] Number of IP addresses to process: {len(ip_addresses)}")
        
        for ip_address in ip_addresses:
            try:
                client_data = export_client_definition(ip_address)
                
                if not client_data:
                    log_warn(logger, f"[WARN] No client data generated for {ip_address}")
                    continue
                
                if upload_client_definition(ip_address, client_data, machine_id):
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                #log_error(logger, f"[ERROR] Processing failed for {ip_address}: {str(e)}")
                
        log_info(logger, f"[INFO] Upload complete. Success: {success_count}, Errors: {error_count}")
        
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error: {str(e)}")


def upload_configuration():
    """
    Retrieve the configuration using get_config_settings and post it as JSON
    to /api/configurations/<instance_identifier>, with sensitive keys removed.
    """
    logger = logging.getLogger(__name__)
    try:
        # Get the instance identifier
        instance_identifier = get_machine_unique_identifier_from_db()

        # Retrieve the configuration
        config_dict = get_config_settings()
        if not config_dict:
            log_error(logger, "[ERROR] Failed to retrieve configuration settings.")
            return False

        # Create a sanitized copy of the configuration
        sanitized_config = config_dict.copy()
        
        # List of sensitive keys to sanitize
        sensitive_keys = [
            "MaxMindAPIKey", 
            "PiholeApiKey", 
            "TelegramBotToken", 
            "TelegramChatId"
        ]
        
        # Set sensitive values to empty strings
        for key in sensitive_keys:
            if key in sanitized_config:
                sanitized_config[key] = ""
                log_info(logger, f"[INFO] Sanitized sensitive key: {key}")

        # Construct the API endpoint URL
        api_url = f"http://api.homelabids.com:8045/api/configurations/{instance_identifier}"

        # Post the sanitized configuration as JSON
        response = requests.post(
            api_url,
            json=sanitized_config,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'NetFlowIPS-Client/1.0'
            },
            timeout=30
        )

        # Check the response status
        if response.status_code in (200, 201, 204):
            log_info(logger, f"[INFO] Successfully uploaded configuration for instance {instance_identifier}.")
            return True
        else:
            log_error(logger, f"[ERROR] Failed to upload configuration: HTTP {response.status_code}")
            return False

    except requests.RequestException as e:
        log_error(logger, f"[ERROR] Request failed while uploading configuration: {str(e)}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while uploading configuration: {str(e)}")
        return False