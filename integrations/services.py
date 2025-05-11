import requests
import csv
import logging
import io
import sqlite3
from src.utils import log_info, log_error
from src.database import connect_to_db, disconnect_from_db
from src.const import CONST_CONSOLIDATED_DB, CONST_CREATE_SERVICES_SQL

def create_services_db():
    """
    Downloads the IANA service names and port numbers CSV and stores it in the database.
    
    The function creates a 'services' table with columns:
    - port_number (integer)
    - protocol (string)
    - service_name (string)
    - description (string)
    """
    logger = logging.getLogger(__name__)
    
    # IANA services CSV URL
    csv_url = "https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.csv"
    
    try:
        # Step 1: Download the CSV file
        log_info(logger, "[INFO] Downloading IANA service names and port numbers CSV...")
        response = requests.get(csv_url, timeout=30)
        
        if response.status_code != 200:
            log_error(logger, f"[ERROR] Failed to download IANA services CSV: {response.status_code}")
            return False
        
        # Step 2: Connect to the database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "services")
        if not conn:
            log_error(logger, f"[ERROR] Failed to connect to the database {CONST_CONSOLIDATED_DB}.")
            return False
            
        cursor = conn.cursor()
        
        # Step 4: Parse and insert the CSV data
        log_info(logger, "[INFO] Parsing and inserting IANA services data...")
        
        # Clear existing data
        cursor.execute("DELETE FROM services")
        
        # Parse CSV
        csv_data = io.StringIO(response.text)
        reader = csv.DictReader(csv_data)
        
        # Insert data
        count = 0
        for row in reader:
            service_name = row.get("Service Name", "")
            port_number = row.get("Port Number", "")
            protocol = row.get("Transport Protocol", "")
            description = row.get("Description", "")
            
            # Skip rows without a port number or where port is a range
            if not port_number or "-" in port_number:
                continue
                
            try:
                # Convert port to integer
                port_int = int(port_number)
                
                cursor.execute("""
                    INSERT OR REPLACE INTO services 
                    (port_number, protocol, service_name, description) 
                    VALUES (?, ?, ?, ?)
                """, (port_int, protocol, service_name, description))
                
                count += 1
                
                # Commit in batches to avoid large transactions
                if count % 1000 == 0:
                    conn.commit()
                    log_info(logger, f"[INFO] Processed {count} service entries...")
                    
            except ValueError:
                # Skip rows where port cannot be converted to integer
                continue
        
        # Final commit
        conn.commit()
        
        # Create index for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_port_protocol ON services (port_number, protocol)")
        conn.commit()
        
        disconnect_from_db(conn)
        
        log_info(logger, f"[INFO] Successfully loaded {count} IANA service entries into the database.")
        return True
        
    except requests.RequestException as e:
        log_error(logger, f"[ERROR] Error downloading IANA services CSV: {e}")
        return False
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while creating services database: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error creating services database: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_all_services():
    """
    Retrieves all service entries from the services database in a dictionary format
    for fast lookups.
    
    Returns:
        dict: A nested dictionary where:
            - The outer key is the port number
            - The inner key is the protocol (e.g., 'tcp', 'udp')
            - The value is a dict with 'service_name' and 'description'
        
        Example: {
            80: {
                'tcp': {'service_name': 'http', 'description': 'World Wide Web HTTP'},
                'udp': {'service_name': 'http', 'description': 'World Wide Web HTTP'}
            }
        }
        
        Returns an empty dictionary if an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "services")
        if not conn:
            log_error(logger, "[ERROR] Failed to connect to the services database.")
            return {}
            
        cursor = conn.cursor()
        
        # Query all services
        log_info(logger, "[INFO] Retrieving all service entries from database...")
        cursor.execute("""
            SELECT port_number, protocol, service_name, description 
            FROM services 
            ORDER BY port_number, protocol
        """)
        
        # Fetch all rows
        rows = cursor.fetchall()
        
        # Convert rows to nested dictionary for fast lookups
        services_dict = {}
        for row in rows:
            port_number = row[0]
            protocol = row[1]
            service_name = row[2]
            description = row[3]
            
            # Create port entry if it doesn't exist
            if port_number not in services_dict:
                services_dict[port_number] = {}
                
            # Add protocol entry
            services_dict[port_number][protocol] = {
                'service_name': service_name,
                'description': description
            }
        
        log_info(logger, f"[INFO] Retrieved services for {len(services_dict)} ports from database.")
        return services_dict
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving services: {e}")
        return {}
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error retrieving services: {e}")
        return {}
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)