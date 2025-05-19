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

def insert_action(action_text):
    """
    Insert a new record into the actions table.

    Args:
        action_data (dict): A dictionary containing the action data to insert.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "actions")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to actions database.")
            return False

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO actions (action_text, acknowledged)
            VALUES (?, 0)
        """, (action_text,))
        conn.commit()
        log_info(logger, f"[INFO] Inserted new action with text: {action_text}")
        return True

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while inserting action: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_all_actions():
    """
    Retrieve all records from the actions table.

    Returns:
        list: A list of dictionaries containing all records from the actions table.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "actions")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to actions database.")
            return []

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM actions")
        rows = cursor.fetchall()
        disconnect_from_db(conn)

        # Format the results as a list of dictionaries
        actions = [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

        log_info(logger, f"[INFO] Retrieved {len(actions)} actions from the database.")
        return actions

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving actions: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def update_action_acknowledged(action_id):
    """
    Update the acknowledged field to 1 for a specific action based on the action_id.

    Args:
        action_id (str): The ID of the action to update.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "actions")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to actions database.")
            return False

        cursor = conn.cursor()
        cursor.execute("""
            UPDATE actions
            SET acknowledged = 1
            WHERE action_id = ?
        """, (action_id,))
        conn.commit()
        log_info(logger, f"[INFO] Updated acknowledged field to 1 for action ID: {action_id}")
        return True

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while updating action: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)