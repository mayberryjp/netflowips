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

def get_localhost_by_ip(ip_address):
    """
    Retrieve complete details for a specific localhost record by IP address.

    Args:
        ip_address (str): The IP address of the localhost to retrieve.

    Returns:
        dict: A dictionary containing all columns for the specified localhost,
              or None if the localhost is not found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the localhosts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to localhosts database.")
            return None

        cursor = conn.cursor()
        
        # Query for the specific IP address using run_timed_query
        query = """
            SELECT ip_address, first_seen, original_flow, 
                   mac_address, mac_vendor, dhcp_hostname, dns_hostname, os_fingerprint,
                   lease_hostname, lease_hwaddr, lease_clientid, acknowledged, local_description, icon, tags, threat_score
            FROM localhosts
            WHERE ip_address = ?
        """
        
        rows, query_time = run_timed_query(
            cursor,
            query,
            (ip_address,),
            description=f"get_localhost_{ip_address}"
        )
        
        # Check if any rows were returned
        if not rows:
            log_info(logger, f"[INFO] No localhost found with IP address: {ip_address} (query took {query_time:.2f} ms)")
            return None
            
        # Return the first row since we're querying by primary key
        row = rows[0]
        
        log_info(logger, f"[INFO] Retrieved details for localhost with IP: {ip_address} in {query_time:.2f} ms")
        return row
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving localhost with IP {ip_address}: {e}")
        return None
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving localhost with IP {ip_address}: {e}")
        return None
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_localhosts_all():
    """
    Retrieve all localhost records with complete details from the localhosts database.

    Returns:
        list: A list of dictionaries containing all columns for each localhost entry,
              or an empty list if an error occurs.
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")

    if not conn:
        log_error(logger, "[ERROR] Unable to connect to localhosts database")
        return []

    try:
        cursor = conn.cursor()
        
        # Use run_timed_query for the SELECT operation
        query = """
            SELECT ip_address, first_seen, original_flow, 
                   mac_address, mac_vendor, dhcp_hostname, dns_hostname, os_fingerprint,
                   lease_hostname, lease_hwaddr, lease_clientid, acknowledged, local_description, icon, tags, threat_score
            FROM localhosts
        """
        
        rows, query_time = run_timed_query(
            cursor,
            query,
            description="get_all_localhosts"
        )

        # Get column names from cursor description
        columns = [column[0] for column in cursor.description]
        
        # Convert rows to list of dictionaries with column names as keys
        localhosts = []
        for row in rows:
            localhost_dict = dict(zip(columns, row))
            localhosts.append(localhost_dict)
            
        log_info(logger, f"[INFO] Retrieved {len(localhosts)} localhost records with full details in {query_time:.2f} ms")
        return localhosts
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Failed to retrieve localhost records: {e}")
        return []
    finally:
        disconnect_from_db(conn)

def get_localhosts():
    """
    Retrieve all local hosts from the localhosts database.

    Returns:
        set: A set of IP addresses from the localhosts database, or an empty set if an error occurs.
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")

    if not conn:
        log_error(logger, "[ERROR] Unable to connect to localhosts database")
        return set()

    try:
        cursor = conn.cursor()
        
        # Use run_timed_query to get IP addresses and track performance
        query = "SELECT ip_address FROM localhosts"
        rows, query_time = run_timed_query(
            cursor,
            query,
            description="get_localhost_ips"
        )
        
        # Convert results to a set of IP addresses
        localhosts = set(row[0] for row in rows)
        
        log_info(logger, f"[INFO] Retrieved {len(localhosts)} local hosts from the database in {query_time:.2f} ms")
        return localhosts
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Failed to retrieve local hosts: {e}")
        return set()
    finally:
        disconnect_from_db(conn)

def update_localhosts(ip_address, mac_address=None, mac_vendor=None, dhcp_hostname=None, dns_hostname=None, os_fingerprint=None, lease_hostname=None, lease_hwaddr=None, lease_clientid=None):
    """
    Update or insert a record in the localhosts database for a given IP address.

    Args:
        ip_address (str): The IP address to update or insert.
        first_seen (str): The first seen timestamp in ISO format (optional).
        original_flow (str): The original flow information as a JSON string (optional).
        mac_address (str): The MAC address associated with the IP address (optional).
        mac_vendor (str): The vendor of the MAC address (optional).
        dhcp_hostname (str): The hostname from DHCP (optional).
        dns_hostname (str): The hostname from DNS (optional).
        os_fingerprint (str): The operating system fingerprint (optional).

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")

    if not conn:
        log_error(logger, "[ERROR] Unable to connect to localhosts database")
        return False

    try:
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE localhosts
            SET mac_address = COALESCE(?, mac_address),
                mac_vendor = COALESCE(?, mac_vendor),
                dhcp_hostname = COALESCE(?, dhcp_hostname),
                dns_hostname = COALESCE(?, dns_hostname),
                os_fingerprint = COALESCE(?, os_fingerprint),
                lease_hwaddr = COALESCE(?, lease_hwaddr),
                lease_clientid = COALESCE(?, lease_clientid),
                lease_hostname = COALESCE(?, lease_hostname)
            WHERE ip_address = ?
        """, (mac_address, mac_vendor, dhcp_hostname, dns_hostname, os_fingerprint, lease_hwaddr, lease_clientid, lease_hostname, ip_address))
        log_info(logger, f"[INFO] Discovery updated record for IP: {ip_address}")

        conn.commit()
        return True
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Failed to update localhosts database: {e}")
        return False
    finally:
        disconnect_from_db(conn)

def insert_localhost_basic(ip_address, original_flow=None):
    """
    Insert a new basic localhost record into the database.

    Args:
        ip_address (str): The IP address of the localhost (required)
        original_flow (str/dict): The original flow information as a JSON string or dict (optional)

    Returns:
        bool: True if the insertion was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the localhosts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to localhosts database.")
            return False

        cursor = conn.cursor()
        
        # Convert dict to JSON string if necessary
        if original_flow and isinstance(original_flow, dict):
            original_flow = json.dumps(original_flow)
        
        # Insert the localhost record
        cursor.execute(
            "INSERT INTO localhosts (ip_address, first_seen, original_flow) VALUES (?, datetime('now', 'localtime'), ?)",
            (ip_address, original_flow)
        )
        
        conn.commit()
        log_info(logger, f"[INFO] Successfully inserted basic localhost record for IP: {ip_address}")
        return True
        
    except sqlite3.IntegrityError:
        # Handle case where IP already exists
        #log_warn(logger, f"[WARN] Localhost with IP: {ip_address} already exists in database")
        return False
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while inserting localhost {ip_address}: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while inserting localhost {ip_address}: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def classify_localhost(ip_address, description, icon):
    """
    Classify a localhost by setting its description, icon, and acknowledging it.
    
    Args:
        ip_address (str): The IP address of the localhost to classify
        description (str): A descriptive label for the localhost (e.g., "Office Printer", "Media Server")
        icon (str): The icon identifier to use for this device (e.g., "printer", "server", "desktop")
        
    Returns:
        bool: True if the classification was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the localhosts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to localhosts database.")
            return False

        cursor = conn.cursor()
        
        # Update the localhost record with classification details
        cursor.execute("""
            UPDATE localhosts
            SET local_description = ?, icon = ?, acknowledged = 1
            WHERE ip_address = ?
        """, (description, icon, ip_address))
        
        # Check if a row was affected
        if cursor.rowcount > 0:
            conn.commit()
            log_info(logger, f"[INFO] Successfully classified localhost {ip_address} as '{description}' with icon '{icon}'")
            return True
        else:
            log_warn(logger, f"[WARN] No localhost found with IP {ip_address} to classify")
            return False
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while classifying localhost {ip_address}: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while classifying localhost {ip_address}: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def delete_localhost_database(ip_address):
    """
    Delete a localhost record from the database.
    
    Args:
        ip_address (str): The IP address of the localhost to delete
        
    Returns:
        bool: True if the deletion was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the localhosts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to localhosts database.")
            return False

        cursor = conn.cursor()
        
        # Delete the localhost record
        cursor.execute("DELETE FROM localhosts WHERE ip_address = ?", (ip_address,))
        
        # Check if a row was affected
        if cursor.rowcount > 0:
            conn.commit()
            log_info(logger, f"[INFO] Successfully deleted localhost with IP: {ip_address}")
            return True
        else:
            log_warn(logger, f"[WARN] No localhost found with IP {ip_address} to delete")
            return False
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while deleting localhost {ip_address}: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while deleting localhost {ip_address}: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def update_localhost_threat_score(ip_address, threat_score):
    """
    Update the threat score for a localhost in the database.
    
    Args:
        ip_address (str): The IP address of the localhost to update
        threat_score (float): The threat score value to set (higher values indicate higher risk)
        
    Returns:
        bool: True if the update was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the localhosts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "localhosts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to localhosts database.")
            return False

        cursor = conn.cursor()
        
        # First check if the localhost exists
        cursor.execute("SELECT 1 FROM localhosts WHERE ip_address = ?", (ip_address,))
        if not cursor.fetchone():
            log_warn(logger, f"[WARN] No localhost found with IP {ip_address} to update threat score")
            return False
        
        # Update the threat_score for the specified localhost
        cursor.execute("""
            UPDATE localhosts
            SET threat_score = ?
            WHERE ip_address = ?
        """, (threat_score, ip_address))
        
        conn.commit()
        log_info(logger, f"[INFO] Successfully updated threat score for {ip_address} to {threat_score}")
        return True
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while updating threat score for {ip_address}: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while updating threat score for {ip_address}: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)