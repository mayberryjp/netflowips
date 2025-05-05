from bottle import Bottle, request, response
import sqlite3
import json
import os
from database import connect_to_db, collect_database_counts  # Import the function
from const import CONST_CONFIG_DB, CONST_ALERTS_DB, CONST_WHITELIST_DB, CONST_LOCALHOSTS_DB, IS_CONTAINER, CONST_API_LISTEN_ADDRESS, CONST_API_LISTEN_PORT
from utils import log_info, log_warn, log_error  # Import logging functions
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Initialize the Bottle app
app = Bottle()

if IS_CONTAINER:
    API_LISTEN_ADDRESS = os.getenv("API_LISTEN_ADDRESS", CONST_API_LISTEN_ADDRESS)
    API_LISTEN_PORT = os.getenv("API_LISTEN_PORT", CONST_API_LISTEN_PORT)

# Helper function to set JSON response headers
def set_json_response():
    response.content_type = 'application/json'

# API for CONST_CONFIG_DB
@app.route('/api/configurations', method=['GET', 'POST'])
def configurations():
    logger = logging.getLogger(__name__)
    db_name = CONST_CONFIG_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            # Fetch all configurations
            cursor.execute("SELECT * FROM configuration")
            rows = cursor.fetchall()
            conn.close()
            set_json_response()
            log_info(logger, "Fetched all configurations successfully.")
            return json.dumps([{"key": row[0], "value": row[1]} for row in rows])
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error fetching configurations: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'POST':
        # Add a new configuration
        data = request.json
        key = data.get('key')
        value = data.get('value')
        try:
            cursor.execute("INSERT INTO configuration (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(logger, f"Added new configuration: {key}")
            return {"message": "Configuration added successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error adding configuration: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/configurations/<key>', method=['PUT', 'DELETE'])
def modify_configuration(key):
    logger = logging.getLogger(__name__)
    db_name = CONST_CONFIG_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'PUT':
        # Update a configuration
        data = request.json
        value = data.get('value')
        try:
            cursor.execute("UPDATE configuration SET value = ? WHERE key = ?", (value, key))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(logger, f"Updated configuration: {key}")
            return {"message": "Configuration updated successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error updating configuration: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'DELETE':
        # Delete a configuration
        try:
            cursor.execute("DELETE FROM configuration WHERE key = ?", (key,))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(logger, f"Deleted configuration: {key}")
            return {"message": "Configuration deleted successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error deleting configuration: {e}")
            response.status = 500
            return {"error": str(e)}

# API for CONST_ALERTS_DB
@app.route('/api/alerts', method=['GET'])
def alerts():
    logger = logging.getLogger(__name__)
    db_name = CONST_ALERTS_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            # Fetch all alerts
            cursor.execute("SELECT * FROM alerts")
            rows = cursor.fetchall()
            conn.close()
            set_json_response()
            log_info(logger, "Fetched all alerts successfully.")
            return json.dumps([{"id": row[0], "ip_address": row[1], "category": row[3], "last_seen": row[8], "acknowledged": row[9]} for row in rows])
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error fetching alerts: {e}")
            response.status = 500
            return {"error": str(e)}


@app.route('/api/alerts/<id>', method=['PUT'])
def modify_alert(id):
    db_name = CONST_ALERTS_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'PUT':
        # Update an alert
        data = request.json
        acknowledged = data.get('acknowledged')
 
        try:
            cursor.execute("UPDATE alerts SET acknowledged = ? WHERE id = ?", (acknowledged, id))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(logger, f"Updated alert: {id}")
            return {"message": "Alert updated successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error updating alert: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/alerts/<id>', method=['DELETE'])
def delete_alert(id):
    """
    API endpoint to delete an alert by its ID.

    Args:
        id: The ID of the alert to delete.

    Returns:
        JSON object indicating success or failure.
    """
    logger = logging.getLogger(__name__)
    db_name = CONST_ALERTS_DB
    conn = connect_to_db(db_name)

    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    try:
        # Delete the alert with the specified ID
        cursor.execute("DELETE FROM alerts WHERE id = ?", (id,))
        conn.commit()
        conn.close()

        set_json_response()
        log_info(logger, f"[INFO] Deleted alert with ID: {id}")
        return {"message": f"Alert with ID {id} deleted successfully"}
    except sqlite3.Error as e:
        conn.close()
        log_error(logger, f"[ERROR] Error deleting alert with ID {id}: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error deleting alert with ID {id}: {e}")
        response.status = 500
        return {"error": str(e)}

@app.route('/api/alerts/summary', method=['GET'])
def summarize_alerts():
    """
    API endpoint to summarize alerts by IP address over the last 12 hours in one-hour increments.
    """
    logger = logging.getLogger(__name__)
    try:
        summary = summarize_alerts_by_ip()
        set_json_response()
        #log_info(logger, "[INFO] Summarized alerts successfully.")
        return json.dumps(summary)
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to summarize alerts: {e}")
        response.status = 500
        return {"error": str(e)}

def summarize_alerts_by_ip():
    """
    Summarize alerts by IP address over the last 12 hours in one-hour increments.

    Returns:
        dict: A dictionary where the main key is the IP address, and the value is another dictionary
              with the key "alert_intervals" containing an array of 12 values representing the count
              of alerts for each one-hour interval, sorted from oldest to most recent.
    """
    logger = logging.getLogger(__name__)
    db_name = CONST_ALERTS_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    intervals = 12

    try:
        # Get the current time and calculate the start time (12 hours ago)
        now = datetime.now()
        start_time = now - timedelta(hours=intervals)

        # Query to fetch alerts within the last 12 hours
        cursor.execute("""
            SELECT ip_address, strftime('%Y-%m-%d %H:00:00', last_seen) as hour, COUNT(*)
            FROM alerts
            WHERE last_seen >= ?
            GROUP BY ip_address, hour
            ORDER BY ip_address, hour
        """, (start_time.strftime('%Y-%m-%d %H:%M:%S'),))

        rows = cursor.fetchall()
        conn.close()

        # Initialize the result dictionary
        result = {}

        # Process the rows to build the summary
        for row in rows:
            ip_address = row[0]
            hour = datetime.strptime(row[1], '%Y-%m-%d %H:00:00')
            count = row[2]

            if ip_address not in result:
                # Initialize the alert_intervals array with 12 zeros
                result[ip_address] = {"alert_intervals": [0] * intervals}

            # Calculate the index for the hour interval
            hour_diff = int((now - hour).total_seconds() // 3600)
            if 0 <= hour_diff < intervals:
                # Reverse the index to place the most recent at the last position
                result[ip_address]["alert_intervals"][intervals - 1 - hour_diff] = count

        return result

    except sqlite3.Error as e:
        conn.close()
        log_error(logger, f"Error summarizing alerts: {e}")
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"Unexpected error: {e}")
        return {"error": str(e)}

@app.route('/api/alerts/recent', method=['GET'])
def get_recent_alerts():
    """
    API endpoint to get the 100 most recent alerts.
    Returns alerts sorted by last_seen timestamp in descending order.
    """
    logger = logging.getLogger(__name__)
    db_name = CONST_ALERTS_DB
    conn = connect_to_db(db_name)
    
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    try:
        # Fetch 100 most recent alerts
        cursor.execute("""
            SELECT id, ip_address, flow, category, 
                   alert_enrichment_1, alert_enrichment_2,
                   times_seen, first_seen, last_seen, acknowledged
            FROM alerts 
            ORDER BY last_seen DESC 
            LIMIT 100
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        # Format the response
        alerts = [{
            "id": row[0],
            "ip_address": row[1],
            "flow": row[2],
            "category": row[3],
            "enrichment_1": row[4],
            "enrichment_2": row[5],
            "times_seen": row[6],
            "first_seen": row[7],
            "last_seen": row[8],
            "acknowledged": bool(row[9])
        } for row in rows]
        
        set_json_response()
        log_info(logger, f"[INFO] Retrieved {len(alerts)} recent alerts")
        return json.dumps(alerts, indent=2)
        
    except sqlite3.Error as e:
        conn.close()
        log_error(logger, f"[ERROR] Database error fetching recent alerts: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to get recent alerts: {e}")
        response.status = 500
        return {"error": str(e)}

@app.route('/api/alerts/<ip_address>', method=['GET'])
def get_alerts_by_ip(ip_address):
    """
    API endpoint to get alerts for a specific IP address.
    
    Args:
        ip_address: The IP address to filter alerts by.
    
    Returns:
        JSON object containing all alerts for the specified IP address.
    """
    logger = logging.getLogger(__name__)
    db_name = CONST_ALERTS_DB
    conn = connect_to_db(db_name)
    
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    try:
        # Fetch alerts for the specified IP address
        cursor.execute("""
            SELECT id, ip_address, flow, category, 
                   alert_enrichment_1, alert_enrichment_2,
                   times_seen, first_seen, last_seen, acknowledged
            FROM alerts 
            WHERE ip_address = ?
            ORDER BY last_seen DESC
        """, (ip_address,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Format the response
        alerts = [{
            "id": row[0],
            "ip_address": row[1],
            "flow": row[2],
            "category": row[3],
            "enrichment_1": row[4],
            "enrichment_2": row[5],
            "times_seen": row[6],
            "first_seen": row[7],
            "last_seen": row[8],
            "acknowledged": bool(row[9])
        } for row in rows]
        
        set_json_response()
        log_info(logger, f"[INFO] Retrieved {len(alerts)} alerts for IP address {ip_address}")
        return json.dumps(alerts, indent=2)
        
    except sqlite3.Error as e:
        conn.close()
        log_error(logger, f"[ERROR] Database error fetching alerts for IP {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to get alerts for IP {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}

# API for CONST_WHITELIST_DB
@app.route('/api/whitelist', method=['GET', 'POST'])
def whitelist():
    db_name = CONST_WHITELIST_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            # Fetch all whitelist entries
            cursor.execute("SELECT * FROM whitelist")
            rows = cursor.fetchall()
            conn.close()
            set_json_response()
            log_info(logger, "Fetched all whitelist entries successfully.")
            return json.dumps([{"whitelist_id": row[0], "src_ip": row[1], "dst_ip": row[2], "dst_port": row[3], "protocol": row[4], "added": row[5]} for row in rows])
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error fetching whitelist entries: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'POST':
        # Add a new whitelist entry
        data = request.json
        whitelist_id = data.get("whitelist_id")
        src_ip = data.get('src_ip')
        dst_ip = data.get('dst_ip')
        dst_port = data.get('dst_port')
        protocol = data.get('protocol')
        try:
            cursor.execute("INSERT INTO whitelist (whitelist_id, src_ip, dst_ip, dst_port, protocol) VALUES (?, ?, ?, ?)", 
                           (whitelist_id, src_ip, dst_ip, dst_port, protocol))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(logger, f"Added new whitelist entry: {whitelist_id} {src_ip} -> {dst_ip}:{dst_port}/{protocol}")
            return {"message": "Whitelist entry added successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error adding whitelist entry: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/whitelist/<id>', method=['PUT', 'DELETE'])
def modify_whitelist(id):
    db_name = CONST_WHITELIST_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'PUT':
        # Update a whitelist entry
        data = request.json
        src_ip = data.get('src_ip')
        dst_ip = data.get('dst_ip')
        dst_port = data.get('dst_port')
        protocol = data.get('protocol')
        try:
            cursor.execute("UPDATE whitelist SET src_ip = ?, dst_ip = ?, dst_port = ?, protocol = ? WHERE id = ?", 
                           (src_ip, dst_ip, dst_port, protocol, id))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(logger, f"Updated whitelist entry: {id}")
            return {"message": "Whitelist entry updated successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error updating whitelist entry: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'DELETE':
        # Delete a whitelist entry
        try:
            cursor.execute("DELETE FROM whitelist WHERE id = ?", (id,))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(logger, f"Deleted whitelist entry: {id}")
            return {"message": "Whitelist entry deleted successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error deleting whitelist entry: {e}")
            response.status = 500
            return {"error": str(e)}

# API for CONST_LOCALHOSTS_DB
@app.route('/api/localhosts', method=['GET'])
def localhosts():
    db_name = CONST_LOCALHOSTS_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            # Fetch all local hosts
            cursor.execute("SELECT * FROM localhosts")
            rows = cursor.fetchall()
            conn.close()
            set_json_response()
            log_info(logger, "Fetched all local hosts successfully.")
            return json.dumps([
                {
                    "ip_address": row[0],
                    "first_seen": row[1],
                    "original_flow": row[2],
                    "mac_address": row[3],
                    "mac_vendor": row[4],
                    "dhcp_hostname": row[5],
                    "dns_hostname": row[6],
                    "os_fingerprint": row[7],
                    "local_description": row[8],
                    "lease_hostname": row[9],
                    "lease_hwaddr": row[10],
                    "lease_clientid": row[11],
                    "icon": row[12],                # New column
                    "tags": row[13],                # New column
                    "acknowledged": row[14]         # New column
                } for row in rows
            ])
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error fetching local hosts: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/localhosts/<ip_address>', method=['PUT'])
def modify_localhost(ip_address):
    db_name = CONST_LOCALHOSTS_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'PUT':
        # Update a local host
        data = request.json
        local_description = data.get('local_description')
        icon = data.get('icon')
        acknowledged = data.get('acknowledged')

        try:
            cursor.execute("""
                UPDATE localhosts
                SET local_description = ?, icon = ?, acknowledged = 1
                WHERE ip_address = ?
            """, (local_description, icon, ip_address))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(logger, f"Updated local host: {ip_address}")
            return {"message": "Local host updated successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(logger, f"Error updating local host: {e}")
            response.status = 500
            return {"error": str(e)}


@app.route('/api/homeassistant', method=['GET'])
def get_database_counts():
    """
    API endpoint to get counts from the alerts, localhosts, and whitelist tables.
    """
    logger = logging.getLogger(__name__)
    try:
        # Call the function to collect database counts
        counts = collect_database_counts()
        set_json_response()
        log_info(logger, "[INFO] Fetched database counts successfully.")
        return json.dumps(counts)
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to fetch database counts: {e}")
        response.status = 500
        return {"error": str(e)}
    

@app.route('/api/homepage', method=['GET'])
def get_database_counts():
    """
    API endpoint to get counts from the alerts, localhosts, and whitelist tables.
    """
    logger = logging.getLogger(__name__)
    try:
        # Call the function to collect database counts
        counts = collect_database_counts()
        set_json_response()
        log_info(logger, "[INFO] Fetched database counts successfully.")
        return json.dumps(counts)
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to fetch database counts: {e}")
        response.status = 500
        return {"error": str(e)}
    
@app.route('/api/quickstats', method=['GET'])
def get_database_counts():
    """
    API endpoint to get counts from the alerts, localhosts, and whitelist tables.
    """
    logger = logging.getLogger(__name__)
    try:
        # Call the function to collect database counts
        counts = collect_database_counts()
        set_json_response()
        log_info(logger, "[INFO] Fetched database counts successfully.")
        return json.dumps(counts)
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to fetch database counts: {e}")
        response.status = 500
        return {"error": str(e)}

@app.route('/api/client/<ip_address>', method=['GET'])
def get_client_info(ip_address):
    """
    API endpoint to get detailed client information for a specific IP address.
    Returns JSON object containing host info, DNS queries, and flow history.
    
    Args:
        ip_address: IP address of the client to query
    """
    logger = logging.getLogger(__name__)
    try:
        from client import export_client_definition
        
        # Get client definition directly
        client_data = export_client_definition(ip_address)
        
        if client_data:
            set_json_response()
            log_info(logger, f"[INFO] Successfully retrieved client info for {ip_address}")
            return json.dumps(client_data, indent=2)
        else:
            log_warn(logger, f"[WARN] No client data found for {ip_address}")
            response.status = 404
            return {"error": f"No client data found for {ip_address}"}
            
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to get client info for {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}




# Run the Bottle app
if __name__ == '__main__':
    logger = logging.getLogger(__name__) 
    log_info(logger, "Starting API server...")
    app.run(host=API_LISTEN_ADDRESS, port=API_LISTEN_PORT, debug=False)