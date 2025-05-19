import os
import sys
from database.core import connect_to_db, disconnect_from_db
from pathlib import Path
# Set up path for imports
current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
sys.path.insert(0, "/database")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from init import *


def insert_pihole_query(client_ip, domain, times_seen=1):
    """
    Insert or update a DNS query record in the pihole database.
    
    Args:
        client_ip (str): The IP address of the client that made the DNS query
        domain (str): The domain name that was queried
        times_seen (int, optional): The number of times this query was seen (default: 1)
        
    Returns:
        bool: True if the insertion/update was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the pihole database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "pihole")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to pihole database.")
            return False
            
        cursor = conn.cursor()
        
        # Insert or update the DNS query record
        cursor.execute("""
            INSERT INTO pihole (client_ip, domain, type, times_seen, first_seen, last_seen)
            VALUES (?, ?, 'A', ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
            ON CONFLICT(client_ip, domain, type)
            DO UPDATE SET
                last_seen = datetime('now', 'localtime'),
                times_seen = times_seen + excluded.times_seen
        """, (client_ip, domain, times_seen))
        
        # Commit the changes
        conn.commit()
        
        #log_info(logger, f"[INFO] Successfully inserted/updated DNS query record for client {client_ip}, domain {domain}")
        return True
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while inserting DNS query record: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while inserting DNS query record: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_client_dns_queries(client_ip):
    """
    Retrieve all DNS queries made by a specific client IP address.
    
    Args:
        client_ip (str): The IP address of the client
        
    Returns:
        list: A list of dictionaries containing domain, query_count, last_query, and first_query
              for each domain queried by the client, ordered by query_count descending.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:

        # Connect to the pihole database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "pihole")
        if not conn:
            log_error(logger, f"[ERROR] Unable to connect to Pi-hole database.")
            return []

        dns_cursor = conn.cursor()
        
        # Query for all domains queried by the client IP
        dns_cursor.execute("""
            SELECT domain, sum(times_seen) as query_count, 
                   MAX(last_seen) as last_query,
                   MIN(first_seen) as first_query
            FROM pihole 
            WHERE client_ip = ?
            GROUP BY domain
            ORDER BY query_count DESC
        """, (client_ip,))
        
        rows = dns_cursor.fetchall()
        
        #log_info(logger, f"[INFO] Retrieved {len(rows)} DNS query records for client IP {client_ip}.")
        return rows
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving DNS queries for client IP {client_ip}: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving DNS queries for client IP {client_ip}: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)