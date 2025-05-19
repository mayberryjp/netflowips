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


def get_custom_tags():
    """
    Retrieve active entries from the customtags table in the ignorelist database.

    Returns:
        list: List of tuples containing (tag_id, src_ip, dst_ip, dst_port, protocol, tag_name)
              Returns None if there's an error.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "customtags")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to ignorelist database")
            return None

        cursor = conn.cursor()
        cursor.execute("""
            SELECT tag_id, src_ip, dst_ip, dst_port, protocol
            FROM customtags
            WHERE enabled = 1
        """)
        customtags = cursor.fetchall()

        log_info(logger, f"[INFO] Retrieved {len(customtags)} active custom tag entries")

        return customtags

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error retrieving custom tag entries: {e}")
        return None
    finally:
        if conn:
            disconnect_from_db(conn)

def import_custom_tags(config_dict):
    """
    Import custom tag entries into the customtags table in the ignorelist database.

    Args:
        config_dict (dict): Configuration dictionary containing tag entries.
                            Expected format: "TagEntries" -> JSON string of list of tuples
                            Each tuple: (tag_id, src_ip, dst_ip, dst_port, protocol, tag_name)
    """
    logger = logging.getLogger(__name__)
    tag_entries_json = config_dict.get("TagEntries", "[]")
    tag_entries = json.loads(tag_entries_json)

    if not tag_entries:
        log_info(logger, "[INFO] No custom tag entries found in config_dict.")
        return

    conn = connect_to_db(CONST_CONSOLIDATED_DB, "customtags")
    if not conn:
        log_error(logger, "[ERROR] Unable to connect to ignorelist database.")
        return

    try:
        cursor = conn.cursor()

        # Insert custom tag entries into the database if they don't already exist
        for entry in tag_entries:
            tag_id, src_ip, dst_ip, dst_port, protocol = entry

            # Check if the custom tag entry already exists
            cursor.execute("""
                SELECT COUNT(*) FROM customtags
                WHERE tag_id = ? AND src_ip = ? AND dst_ip = ? AND dst_port = ? AND protocol = ?
            """, (tag_id, src_ip, dst_ip, dst_port, protocol))
            exists = cursor.fetchone()[0]

            if exists:
                log_info(logger, f"[INFO] Custom tag entry already exists: {entry}")
                continue

            # Insert the new custom tag entry
            cursor.execute("""
                INSERT INTO customtags (
                    tag_id, src_ip, dst_ip, dst_port, protocol, tag_name, enabled, added, insert_date
                ) VALUES (?, ?, ?, ?, ?, "", 1, datetime('now', 'localtime'), datetime('now', 'localtime'))
            """, (tag_id, src_ip, dst_ip, dst_port, protocol))

        conn.commit()
        log_info(logger, f"[INFO] Imported {len(tag_entries)} custom tag entries into the database.")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error importing custom tag entries: {e}")
    finally:
        disconnect_from_db(conn)