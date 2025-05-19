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

def get_config_settings():
    """Read configuration settings from the configuration database into a dictionary."""
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "configuration")
        if not conn:
            log_error(logger,"[ERROR] Unable to connect to configuration database")
            return None

        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM configuration")
        config_dict = dict(cursor.fetchall())
        log_info(logger, f"[INFO] Successfully loaded {len(config_dict)} configuration settings")
        return config_dict
    except sqlite3.Error as e:
        log_error(logger,f"[ERROR] Error reading configuration database: {e}")
        disconnect_from_db(conn)
        return None
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def update_config_setting(key, value):
    """
    Insert or update a configuration setting in the database.
    
    Args:
        key (str): The configuration key
        value (str): The configuration value
        
    Returns:
        bool: True if the operation was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the configuration database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "configuration")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to configuration database")
            return False
            
        cursor = conn.cursor()
        
        # Insert or replace the configuration setting
        cursor.execute("""
            INSERT OR REPLACE INTO configuration (key, value, last_changed) 
            VALUES (?, ?, datetime('now', 'localtime'))
        """, (key, value))
        
        # Commit the changes
        conn.commit()
        
        log_info(logger, f"[INFO] Successfully updated configuration setting: {key}")
        return True
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while updating configuration setting: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while updating configuration setting: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)


