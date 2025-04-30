import json
import sqlite3
from pathlib import Path
from enum import Enum
import logging
from datetime import datetime
import requests
from const import (
    CONST_LOCALHOSTS_DB, 
    CONST_DNSQUERIES_DB, 
    CONST_ALLFLOWS_DB
)
from utils import log_info, log_error, log_warn
from database import get_machine_unique_identifier_from_db, get_localhosts

class ActionType(Enum):
    """Placeholder for action types"""
    pass

def export_client_definition(client_ip):
    """
    Export client information to a JSON file.
    
    Args:
        client_ip (str): IP address of the client to export
        
    Creates a JSON file with:
    - Local host information
    - DNS queries history
    - Network flow history
    - Recommended actions
    """
    logger = logging.getLogger(__name__)

    instance_identifier = get_machine_unique_identifier_from_db()

    
    try:
        # Create output directory if it doesn't exist
        
        # Initialize the client data structure
        client_data = {
            "ip_address": client_ip,
            "export_date": datetime.now().isoformat(),
            "instance_identifier": instance_identifier
        }
        
        # Get host information from localhosts.db
        localhosts_conn = sqlite3.connect(CONST_LOCALHOSTS_DB)
        localhosts_cursor = localhosts_conn.cursor()
        localhosts_cursor.execute(
            "SELECT ip_address,mac_address,mac_vendor,dhcp_hostname, os_fingerprint, lease_hostname, icon, local_description FROM localhosts WHERE ip_address = ?", 
            (client_ip,)
        )
        host_record = localhosts_cursor.fetchone()
        if host_record:
            client_data["host_info"] = {
                "ip_address": host_record[0],
                "mac_address": host_record[1],
                "mac_vendor": host_record[2],
                "dhcp_hostname": host_record[3],
                "os_fingerprint": host_record[4],
                "lease_hostname": host_record[5],
                "icon": host_record[6],
                "local_description": host_record[7]
            }
        
        # Get DNS queries from dnsqueries.db
        dns_conn = sqlite3.connect(CONST_DNSQUERIES_DB)
        dns_cursor = dns_conn.cursor()
        dns_cursor.execute("""
            SELECT domain 
            FROM pihole 
            WHERE client_ip = ? 
            GROUP BY domain
        """, (client_ip,))
        client_data["dns_queries"] = [row[0] for row in dns_cursor.fetchall()]
        
        # Get flows from allflows.db
        flows_conn = sqlite3.connect(CONST_ALLFLOWS_DB)
        flows_cursor = flows_conn.cursor()
        flows_cursor.execute("""
            SELECT DISTINCT dst_ip, dst_port, protocol
            FROM allflows 
            WHERE src_ip = ?
            and dst_port < src_port
            ORDER BY last_seen DESC
        """, (client_ip,))
        client_data["flows"] = [
            {
                "destination": row[0],
                "port": row[1],
                "protocol": row[2]
            }
            for row in flows_cursor.fetchall()
        ]
        
       # log_info(logger, f"[INFO] Exported client definition for {client_ip}")
        
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to export client definition for {client_ip}: {e}")
    finally:
        # Close all database connections
        for conn in [localhosts_conn, dns_conn, flows_conn]:
            if 'conn' in locals() and conn:
                conn.close()

    return client_data

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
        api_url = f"http://api.homelabids.com:8044/api/classification/{machine_id}/{ip_address}"
        
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
