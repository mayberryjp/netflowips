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


def get_services_by_port(port_number):
    """
    Retrieve service information for a specific port number.
    
    Args:
        port_number (int): The port number to query
        
    Returns:
        dict: A dictionary where keys are protocols (e.g., 'tcp', 'udp') and values 
              are dictionaries containing 'service_name' and 'description'.
              Returns an empty dictionary if no services found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the services database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "services")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to services database.")
            return {}
            
        cursor = conn.cursor()
        
        # Query services for the specified port
        cursor.execute("""
            SELECT protocol, service_name, description 
            FROM services 
            WHERE port_number = ?
        """, (port_number,))
        
        rows = cursor.fetchall()
        
        # Format results as a dictionary
        services_dict = {}
        for row in rows:
            protocol = row[0]
            services_dict[protocol] = {
                'service_name': row[1],
                'description': row[2]
            }
        
        log_info(logger, f"[INFO] Retrieved {len(services_dict)} service entries for port {port_number}.")
        return services_dict
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving services for port {port_number}: {e}")
        return {}
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving services for port {port_number}: {e}")
        return {}
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_all_services_database():
    """
    Retrieve all service information from the services table.
    
    Returns:
        list: A list of dictionaries containing service information with keys:
              'port_number', 'protocol', 'service_name', 'description'.
              Returns an empty list if no services found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the services database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "services")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to services database.")
            return []
            
        cursor = conn.cursor()
        
        # Query all services
        cursor.execute("""
            SELECT port_number, protocol, service_name, description 
            FROM services 
            ORDER BY port_number, protocol
        """)
        
        rows = cursor.fetchall()
        
        log_info(logger, f"[INFO] Retrieved {len(rows)} service entries from the database.")
        return rows
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving services: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving services: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)
    
def insert_service(port_number, protocol, service_name, description):
    """
    Insert or replace a service record in the services table.
    
    Args:
        port_number (int): The port number of the service
        protocol (str): The protocol (e.g., 'tcp', 'udp')
        service_name (str): The name of the service
        description (str): A description of the service
        
    Returns:
        bool: True if the insertion/update was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the services database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "services")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to services database.")
            return False
            
        cursor = conn.cursor()
        
        # Insert or replace the service record
        cursor.execute("""
            INSERT OR REPLACE INTO services 
            (port_number, protocol, service_name, description) 
            VALUES (?, ?, ?, ?)
        """, (port_number, protocol, service_name, description))
        
        # Commit the changes
        conn.commit()
        
        #log_info(logger, f"[INFO] Successfully inserted/updated service record for port {port_number}/{protocol}: {service_name}")
        return True
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while inserting service record: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while inserting service record: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)