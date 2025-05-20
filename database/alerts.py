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

def summarize_alerts_by_ip():
    """
    Summarize alerts by IP address over the last 12 hours in one-hour increments.
    Returns results for every hour whether there were alerts or not.

    Returns:
        dict: A dictionary where the main key is the IP address, and the value is another dictionary
            with the key "alert_intervals" containing an array of 12 values representing the count
            of alerts for each one-hour interval, sorted from oldest to most recent.
    """
    logger = logging.getLogger(__name__)
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "alerts")
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    intervals = 12

    try:
        # Get the current time and calculate the start time (12 hours ago)
        now = datetime.now()
        start_time = now - timedelta(hours=intervals)

        # First, get all unique IP addresses with alerts in the time period
        cursor.execute("""
            SELECT DISTINCT ip_address 
            FROM localhosts
        """)
        
        all_ips = [row[0] for row in cursor.fetchall()]
        
        # Query to fetch alerts within the last 12 hours
        cursor.execute("""
            SELECT ip_address, strftime('%Y-%m-%d %H:00:00', last_seen) as hour, COUNT(*)
            FROM alerts
            WHERE last_seen >= ?
            GROUP BY ip_address, hour
            ORDER BY ip_address, hour
        """, (start_time.strftime('%Y-%m-%d %H:%M:%S'),))

        alerts_by_hour = cursor.fetchall()
        disconnect_from_db(conn)

        # Generate all hour intervals for the past 12 hours
        hour_intervals = []
        for i in range(intervals):
            interval_time = now - timedelta(hours=intervals-i-1)
            hour_intervals.append(interval_time.strftime('%Y-%m-%d %H:00:00'))

        # Initialize the result dictionary with all IPs and all hours
        result = {}
        for ip in all_ips:
            result[ip] = {"alert_intervals": [0] * intervals}
            
        # Fill in the actual alert counts where they exist
        for row in alerts_by_hour:
            ip_address = row[0]
            hour = row[1]
            count = row[2]
            
            # Only process IPs that are in our all_ips list (from localhosts)
            if ip_address in all_ips:
                # Find which interval this hour belongs to
                try:
                    hour_index = hour_intervals.index(hour)
                    result[ip_address]["alert_intervals"][hour_index] = count
                except ValueError:
                    # This shouldn't happen if our hour generation is correct
                    log_warn(logger, f"Hour {hour} not found in generated intervals")


        return result

    except sqlite3.Error as e:
        disconnect_from_db(conn)
        log_error(logger, f"Error summarizing alerts: {e}")
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"Unexpected error: {e}")
        return {"error": str(e)}

def get_hourly_alerts_summary(ip_address, start_time=None):
    """
    Get a summary of alerts by hour for a specific IP address.
    
    Args:
        ip_address (str): The IP address to filter alerts by
        start_time (str, optional): The timestamp to start from in ISO format 
                                  (e.g., '2023-05-01 00:00:00').
                                  If not provided, retrieves all alerts.
        
    Returns:
        list: A list of tuples containing (hour, count) for each hour,
              where hour is in format 'YYYY-MM-DD HH:00:00' and count is the number of alerts.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return []

        cursor = conn.cursor()
        
        # If no start_time provided, use a very old date to get all alerts
        if not start_time:
            start_time = '2000-01-01 00:00:00'
        
        # Get hourly summary of alerts
        cursor.execute("""
            SELECT strftime('%Y-%m-%d %H:00:00', last_seen) as hour, COUNT(*)
            FROM alerts
            WHERE ip_address = ? AND last_seen >= ?
            GROUP BY hour
            ORDER BY hour
        """, (ip_address, start_time))
        
        hourly_summary = cursor.fetchall()
        
        log_info(logger, f"[INFO] Retrieved hourly alert summary for IP {ip_address} starting from {start_time}.")
        return hourly_summary
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving hourly alert summary: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving hourly alert summary: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_all_alerts_by_ip(ip_address):
    """
    Retrieve all alerts for a specific IP address from the alerts table.

    Args:
        ip_address (str): The IP address to filter alerts by.

    Returns:
        list: A list of dictionaries containing all alerts for the specified IP,
              ordered by last_seen timestamp in descending order.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return []

        cursor = conn.cursor()
        
        # Retrieve all alerts for the specified IP address, most recent first
        cursor.execute("""
            SELECT id, ip_address, flow, category, 
                alert_enrichment_1, alert_enrichment_2,
                times_seen, first_seen, last_seen, acknowledged
            FROM alerts 
            WHERE ip_address = ?
            ORDER BY last_seen DESC
        """, (ip_address,))
        
        rows = cursor.fetchall()
        
        # Get column names from cursor description
        columns = [column[0] for column in cursor.description]
        
        # Format the results as a list of dictionaries
        alerts = []
        for row in rows:
            alert_dict = dict(zip(columns, row))
            # Parse JSON if flow is stored as a string
            if 'flow' in alert_dict and isinstance(alert_dict['flow'], str):
                try:
                    alert_dict['flow'] = json.loads(alert_dict['flow'])
                except:
                    pass  # Keep as string if JSON parsing fails
            alerts.append(alert_dict)

        log_info(logger, f"[INFO] Retrieved {len(alerts)} alerts for IP address {ip_address}.")
        return alerts
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving alerts for IP {ip_address}: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving alerts for IP {ip_address}: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_alert_count_by_id(alert_id):
    """
    Get the count of alerts with the specified ID in the database.
    
    Args:
        alert_id (str): The ID of the alert to count
        
    Returns:
        int: The count of matching alerts, or 0 if not found or an error occurs
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return 0

        cursor = conn.cursor()
        
        # Count alerts with the specified ID
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE id = ?", (alert_id,))
        
        # Get the count from the result
        count = cursor.fetchone()[0]
        
        #log_info(logger, f"[INFO] Found {count} alerts with ID {alert_id}.")
        return count
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while counting alerts with ID {alert_id}: {e}")
        return 0
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while counting alerts with ID {alert_id}: {e}")
        return 0
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_recent_alerts_database():
    """
    Retrieve the most recent 100 alerts from the alerts table.

    Returns:
        list: A list of dictionaries containing the most recent 100 alerts,
              ordered by last_seen timestamp in descending order.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return []

        cursor = conn.cursor()
        
        # Retrieve the most recent alerts, limited to 100
        cursor.execute("""
            SELECT id, ip_address, flow, category, 
                alert_enrichment_1, alert_enrichment_2,
                times_seen, first_seen, last_seen, acknowledged
            FROM alerts 
            ORDER BY last_seen DESC 
            LIMIT 100
        """)
        
        rows = cursor.fetchall()
        
        return rows

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving recent alerts: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving recent alerts: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def delete_alert(alert_id):
    """
    Delete an alert from the database.
    
    Args:
        alert_id (str): The ID of the alert to delete
        
    Returns:
        bool: True if the deletion was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return False

        cursor = conn.cursor()
        
        # Delete the alert
        cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        
        # Check if any rows were affected
        if cursor.rowcount > 0:
            conn.commit()
            log_info(logger, f"[INFO] Alert with ID {alert_id} was successfully deleted.")
            return True
        else:
            log_warn(logger, f"[WARN] No alert found with ID {alert_id} to delete.")
            return False

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while deleting alert {alert_id}: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while deleting alert {alert_id}: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def log_alert_to_db(ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, alert_id_hash, realert=False):
    """
    Logs an alert to the alerts.db SQLite database and indicates whether it was an insert or an update.

    Args:
        ip_address (str): The IP address associated with the alert.
        flow (dict): The flow data as a dictionary.
        category (str): The category of the alert.
        alert_enrichment_1 (str): Additional enrichment data for the alert.
        alert_enrichment_2 (str): Additional enrichment data for the alert.
        alert_id_hash (str): A unique hash for the alert.
        realert (bool): Whether this is a re-alert.

    Returns:
        str: "insert" if a new row was inserted, "update" if an existing row was updated, or "error" if an error occurred.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return "error"

        cursor = conn.cursor()

        # Execute the insert or update query
        cursor.execute("""
            INSERT INTO alerts (id, ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, times_seen, first_seen, last_seen, acknowledged)
            VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now', 'localtime'), datetime('now', 'localtime'), 0)
            ON CONFLICT(id)
            DO UPDATE SET
                times_seen = times_seen + 1,
                last_seen = datetime('now', 'localtime')
        """, (alert_id_hash, ip_address, json.dumps(flow), category, alert_enrichment_1, alert_enrichment_2))

        # Check the number of rows affected
        if conn.total_changes == 1:
            operation = "insert"
        else:
            operation = "update"

        conn.commit()
        log_info(logger, f"[INFO] Alert logged to database for IP: {ip_address}, Category: {category} ({operation}).")
        return operation

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error logging alert to database: {e}")
        return "error"
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_alerts_summary():
    """
    Get a summary of alerts by category from alerts.db.
    Prints total count and breakdown by category.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database")
            return

        cursor = conn.cursor()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM alerts")
        total_count = cursor.fetchone()[0]
        
        # Get counts by category
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM alerts 
            GROUP BY category 
            ORDER BY count DESC
        """)
        categories = cursor.fetchall()
        
        # Log the summary
        log_info(logger, f"[INFO] Total alerts: {total_count}")
        log_info(logger, "[INFO] Breakdown by category:")
        for category, count in categories:
            percentage = (count / total_count * 100) if total_count > 0 else 0
            log_info(logger, f"[INFO]   {category}: {count} ({percentage:.1f}%)")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Error getting alerts summary: {e}")
    finally:
        if 'conn' in locals():
            disconnect_from_db(conn)

def get_recent_alerts_by_ip(ip_address):
    """
    Retrieve the most recent 100 alerts for a specific IP address from the alerts table.

    Args:
        ip_address (str): The IP address to filter alerts by.

    Returns:
        list: A list of dictionaries containing the most recent 100 alerts for the specified IP.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return []

        cursor = conn.cursor()
        
        # Retrieve alerts for the specified IP address, most recent first, limited to 100
        cursor.execute("""
            SELECT id, ip_address, flow, category, 
                   alert_enrichment_1, alert_enrichment_2,
                   times_seen, first_seen, last_seen, acknowledged
            FROM alerts 
            WHERE ip_address = ?
            ORDER BY last_seen DESC 
            LIMIT 100
        """, (ip_address,))
        
        rows = cursor.fetchall()
        
        # Get column names from cursor description
        columns = [column[0] for column in cursor.description]
        
        # Format the results as a list of dictionaries
        alerts = []
        for row in rows:
            alert_dict = dict(zip(columns, row))
            # Parse JSON if flow is stored as a string
            if 'flow' in alert_dict and isinstance(alert_dict['flow'], str):
                try:
                    alert_dict['flow'] = json.loads(alert_dict['flow'])
                except:
                    pass  # Keep as string if JSON parsing fails
            alerts.append(alert_dict)

        log_info(logger, f"[INFO] Retrieved {len(alerts)} recent alerts for IP address {ip_address}.")
        return alerts

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving alerts for IP {ip_address}: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving alerts for IP {ip_address}: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_all_alerts():
    """
    Retrieve all records from the alerts table.

    Returns:
        list: A list of dictionaries containing all records from the alerts table.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    try:
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return []

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alerts")
        rows = cursor.fetchall()

        # Get column names from cursor description
        columns = [column[0] for column in cursor.description]
        
        # Format the results as a list of dictionaries
        alerts = []
        for row in rows:
            alert_dict = dict(zip(columns, row))
            # Parse JSON if flow is stored as a string
            if 'flow' in alert_dict and isinstance(alert_dict['flow'], str):
                try:
                    alert_dict['flow'] = json.loads(alert_dict['flow'])
                except:
                    pass  # Keep as string if JSON parsing fails
            alerts.append(alert_dict)

        log_info(logger, f"[INFO] Retrieved {len(alerts)} alerts from the database.")
        return alerts

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving alerts: {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving alerts: {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def get_alerts_by_category(category_name):

    """
    Retrieve alerts from the database for a specific category.

    Args:
        category_name (str): The category name to filter alerts by

    Returns:
        list: A list of raw database rows for the specified category.
              Returns an empty list if no data is found or an error occurs.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return []

        cursor = conn.cursor()
        
        # Retrieve all alerts for the specified category
        cursor.execute("""
            SELECT id, ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, 
                   times_seen, first_seen, last_seen, acknowledged
            FROM alerts
            WHERE category = ?
            ORDER BY last_seen DESC
        """, (category_name,))
        
        # Just return the raw rows
        rows = cursor.fetchall()
        
        log_info(logger, f"[INFO] Retrieved {len(rows)} alerts for category '{category_name}' from the database.")
        return rows

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while retrieving alerts for category '{category_name}': {e}")
        return []
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while retrieving alerts for category '{category_name}': {e}")
        return []
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)

def update_alert_acknowledgment(alert_id, acknowledged):
    """
    Update the acknowledged status of an alert in the database.
    
    Args:
        alert_id (str): The ID of the alert to update
        acknowledged (int): 1 for acknowledged, 0 for not acknowledged
        
    Returns:
        bool: True if the update was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Connect to the alerts database
        conn = connect_to_db(CONST_CONSOLIDATED_DB, "alerts")
        if not conn:
            log_error(logger, "[ERROR] Unable to connect to alerts database.")
            return False

        cursor = conn.cursor()
        
        # Update the acknowledged flag
        cursor.execute("UPDATE alerts SET acknowledged = ? WHERE id = ?", (acknowledged, alert_id))
        
        # Check if any rows were affected
        if cursor.rowcount > 0:
            conn.commit()
            log_info(logger, f"[INFO] Alert {alert_id} acknowledged status updated to {acknowledged}.")
            return True
        else:
            log_warn(logger, f"[WARN] No alert found with ID {alert_id}.")
            return False

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error while updating alert acknowledgment: {e}")
        return False
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error while updating alert acknowledgment: {e}")
        return False
    finally:
        if 'conn' in locals() and conn:
            disconnect_from_db(conn)