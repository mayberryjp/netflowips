import json
import sqlite3
from pathlib import Path
from enum import Enum
import logging
from datetime import datetime
from const import (
    CONST_LOCALHOSTS_DB, 
    CONST_DNSQUERIES_DB, 
    CONST_ALLFLOWS_DB
)
from utils import log_info, log_error

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
    
    try:
        # Create output directory if it doesn't exist
        
        # Initialize the client data structure
        client_data = {
            "ip_address": client_ip,
            "export_date": datetime.now().isoformat(),
        }
        
        # Get host information from localhosts.db
        localhosts_conn = sqlite3.connect(CONST_LOCALHOSTS_DB)
        localhosts_cursor = localhosts_conn.cursor()
        localhosts_cursor.execute(
            "SELECT ip_address,mac_address,mac_vendor,dhcp_hostname, os_fingerprint, lease_hostname FROM localhosts WHERE ip_address = ?", 
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
                "lease_hostname": host_record[5]
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
        
            
        log_info(logger, f"[INFO] Exported client definition for {client_ip}")
        
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to export client definition for {client_ip}: {e}")
    finally:
        # Close all database connections
        for conn in [localhosts_conn, dns_conn, flows_conn]:
            if 'conn' in locals() and conn:
                conn.close()

    return client_data

