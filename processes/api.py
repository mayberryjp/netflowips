import sys
import os
from pathlib import Path
current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
src_dir = f"{parent_dir}/src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
from bottle import Bottle, request, response, hook, route
import sqlite3
import json
from src.database import get_config_settings, get_all_actions, insert_action, update_action_acknowledged, connect_to_db, collect_database_counts, disconnect_from_db, get_traffic_stats_for_ip  # Import the function
from src.const import IS_CONTAINER, CONST_API_LISTEN_ADDRESS, CONST_API_LISTEN_PORT, CONST_CONSOLIDATED_DB
from src.utils import log_info, log_warn, log_error  # Import logging functions
import logging
from datetime import datetime, timedelta
# Import DNS lookup function
from integrations.dns import dns_lookup
# Import geolocation function
from integrations.maxmind import lookup_ip_country

# Initialize the Bottle app
app = Bottle()

# Define CORS headers
CORS_HEADERS = {
    'Access-Control-Allow-Origin': 'http://localhost:3030',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
}

# Add CORS headers to all responses
@app.hook('after_request')
def enable_cors():
    """Add CORS headers to every response"""
    for key, value in CORS_HEADERS.items():
        response.headers[key] = value

# Handle OPTIONS preflight requests
@app.route('/<path:path>', method='OPTIONS')
@app.route('/', method='OPTIONS')
def options_handler(path=None):
    """Handle OPTIONS requests for CORS preflight"""
    # Set CORS headers explicitly for OPTIONS
    for key, value in CORS_HEADERS.items():
        response.headers[key] = value
    return {}

if IS_CONTAINER:
    API_LISTEN_ADDRESS = os.getenv("API_LISTEN_ADDRESS", CONST_API_LISTEN_ADDRESS)
    API_LISTEN_PORT = os.getenv("API_LISTEN_PORT", CONST_API_LISTEN_PORT)

# Helper function to set JSON response headers
def set_json_response():
    response.content_type = 'application/json'


# API for CONST_CONSOLIDATED_DB
@app.route('/api/configurations', method=['GET', 'POST'])
def configurations():
    logger = logging.getLogger(__name__)
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "configurations")
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            # Fetch all configurations
            cursor.execute("SELECT * FROM configuration")
            rows = cursor.fetchall()
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, "Fetched all configurations successfully.")
            return json.dumps([{"key": row[0], "value": row[1]} for row in rows])
        except sqlite3.Error as e:
            disconnect_from_db(conn)
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
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, f"Added new configuration: {key}")
            return {"message": "Configuration added successfully"}
        except sqlite3.Error as e:
            disconnect_from_db(conn)
            log_error(logger, f"Error adding configuration: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/configurations/<key>', method=['PUT', 'DELETE'])
def modify_configuration(key):
    logger = logging.getLogger(__name__)
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "configurations")
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
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, f"Updated configuration: {key}")
            return {"message": "Configuration updated successfully"}
        except sqlite3.Error as e:
            disconnect_from_db(conn)
            log_error(logger, f"Error updating configuration: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'DELETE':
        # Delete a configuration
        try:
            cursor.execute("DELETE FROM configuration WHERE key = ?", (key,))
            conn.commit()
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, f"Deleted configuration: {key}")
            return {"message": "Configuration deleted successfully"}
        except sqlite3.Error as e:
            disconnect_from_db(conn)
            log_error(logger, f"Error deleting configuration: {e}")
            response.status = 500
            return {"error": str(e)}


@app.route('/api/alerts/category/<category_name>', method=['GET'])
def get_alerts_by_category_api(category_name):
    """
    API endpoint to get alerts for a specific category.
    
    Args:
        category_name: The category name to filter alerts by.
    
    Returns:
        JSON object containing all alerts for the specified category.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Import the function from database.py
        from src.database import get_alerts_by_category
        
        # Get alerts by category
        alerts = get_alerts_by_category(category_name)
        
        if not alerts:
            log_info(logger, f"[INFO] No alerts found for category: {category_name}")
            return json.dumps([])
        
        # Format the response
        formatted_alerts = [{
            "id": row[0],
            "ip_address": row[1],
            "category": row[3],
            "enrichment_1": row[4],
            "enrichment_2": row[5],
            "times_seen": row[6],
            "first_seen": row[7],
            "last_seen": row[8],
            "acknowledged": bool(row[9])
        } for row in alerts]
        
        set_json_response()
        log_info(logger, f"[INFO] Retrieved {len(alerts)} alerts for category {category_name}")
        return json.dumps(formatted_alerts, indent=2)
        
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error fetching alerts for category {category_name}: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to get alerts for category {category_name}: {e}")
        response.status = 500
        return {"error": str(e)}

# API for CONST_CONSOLIDATED_DB
@app.route('/api/alerts', method=['GET'])
def alerts():
    logger = logging.getLogger(__name__)
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "alerts")
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            # Fetch all alerts
            cursor.execute("SELECT * FROM alerts")
            rows = cursor.fetchall()
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, "Fetched all alerts successfully.")
            return json.dumps([{"id": row[0], "ip_address": row[1], "category": row[3], "enrichment_1": row[4], "enrichment_2": row[5], "times_seen": row[6], "first_seen": row[7], "last_seen": row[8], "acknowledged": row[9]} for row in rows])
        except sqlite3.Error as e:
            disconnect_from_db(conn)
            log_error(logger, f"Error fetching alerts: {e}")
            response.status = 500
            return {"error": str(e)}


@app.route('/api/alerts/<id>', method=['PUT'])
def modify_alert(id):
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "alerts")
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
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, f"Updated alert: {id}")
            return {"message": "Alert updated successfully"}
        except sqlite3.Error as e:
            disconnect_from_db(conn)
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
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "alerts")

    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    try:
        # Delete the alert with the specified ID
        cursor.execute("DELETE FROM alerts WHERE id = ?", (id,))
        conn.commit()
        disconnect_from_db(conn)

        set_json_response()
        log_info(logger, f"[INFO] Deleted alert with ID: {id}")
        return {"message": f"Alert with ID {id} deleted successfully"}
    except sqlite3.Error as e:
        disconnect_from_db(conn)
        log_error(logger, f"[ERROR] Error deleting alert with ID {id}: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error deleting alert with ID {id}: {e}")
        response.status = 500
        return {"error": str(e)}
    
@app.route('/api/classify/<ip_address>', method=['GET'])
def classify_client_api(ip_address):
    """
    API endpoint to classify a client device by retrieving its data definition
    and sending it to the master classification API.

    Args:
        ip_address: The IP address of the client to classify.

    Returns:
        JSON object containing the classification results.
    """
    logger = logging.getLogger(__name__)
    try:
        # Import the required functions
        from src.client import export_client_definition, classify_client
        from src.database import get_machine_unique_identifier_from_db
        
        # Get the machine identifier
        machine_identifier = get_machine_unique_identifier_from_db()
        if not machine_identifier:
            log_error(logger, f"[ERROR] Failed to get machine identifier for classification")
            response.status = 500
            return {"error": "Could not retrieve machine identifier"}
            
        # Get client definition
        client_data = export_client_definition(ip_address)
        if not client_data:
            log_warn(logger, f"[WARN] No client data found for {ip_address}")
            response.status = 404
            return {"error": f"No client data found for {ip_address}"}
        
        # Send to classification API
        classification_result = classify_client(machine_identifier, client_data)
        if not classification_result:
            log_error(logger, f"[ERROR] Failed to classify client {ip_address}")
            response.status = 500
            return {"error": "Classification request failed"}
        
        # Return the classification result
        set_json_response()
        log_info(logger, f"[INFO] Successfully classified client {ip_address}")
        return json.dumps(classification_result, indent=2)
        
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to classify client {ip_address}: {e}")
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

@app.route('/api/alerts/recent/<ip_address>', method=['GET'])
def get_recent_alerts_by_ip(ip_address):
    """
    API endpoint to get the most recent alerts for a specific IP address.
    Returns alerts sorted by last_seen timestamp in descending order.

    Args:
        ip_address: The IP address to filter alerts by.

    Returns:
        JSON object containing the most recent alerts for the specified IP address.
    """
    logger = logging.getLogger(__name__)
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "alerts")
    
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    try:
        # Fetch the most recent alerts for the specified IP address
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
        disconnect_from_db(conn)
        
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
        log_info(logger, f"[INFO] Retrieved {len(alerts)} recent alerts for IP address {ip_address}")
        return json.dumps(alerts, indent=2)
        
    except sqlite3.Error as e:
        disconnect_from_db(conn)
        log_error(logger, f"[ERROR] Database error fetching recent alerts for IP {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to get recent alerts for IP {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}


@app.route('/api/alerts/summary/<ip_address>', method=['GET'])
def summarize_alerts_by_ip_address(ip_address):
    """
    API endpoint to summarize recent alerts for a specific IP address.

    Args:
        ip_address: The IP address to filter alerts by.

    Returns:
        JSON object containing a summary of alerts for the specified IP address.
    """
    logger = logging.getLogger(__name__)
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "alerts")
    
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    try:
        # Query to fetch alerts for the specified IP address within the last 12 hours
        intervals = 48
        now = datetime.now()
        start_time = now - timedelta(hours=intervals)

        cursor.execute("""
            SELECT strftime('%Y-%m-%d %H:00:00', last_seen) as hour, COUNT(*)
            FROM alerts
            WHERE ip_address = ? AND last_seen >= ?
            GROUP BY hour
            ORDER BY hour
        """, (ip_address, start_time.strftime('%Y-%m-%d %H:%M:%S')))

        rows = cursor.fetchall()
        disconnect_from_db(conn)

        # Initialize the result dictionary
        result = {"ip_address": ip_address, "alert_intervals": [0] * intervals}

        # Process the rows to build the summary
        for row in rows:
            hour = datetime.strptime(row[0], '%Y-%m-%d %H:00:00')
            count = row[1]

            # Calculate the index for the hour interval
            hour_diff = int((now - hour).total_seconds() // 3600)
            if 0 <= hour_diff < intervals:
                # Reverse the index to place the most recent at the last position
                result["alert_intervals"][intervals - 1 - hour_diff] = count

        set_json_response()
        log_info(logger, f"[INFO] Summarized alerts for IP address {ip_address}")
        return json.dumps(result, indent=2)

    except sqlite3.Error as e:
        disconnect_from_db(conn)
        log_error(logger, f"[ERROR] Database error summarizing alerts for IP {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to summarize alerts for IP {ip_address}: {e}")
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

        # Query to fetch alerts within the last 12 hours
        cursor.execute("""
            SELECT ip_address, strftime('%Y-%m-%d %H:00:00', last_seen) as hour, COUNT(*)
            FROM alerts
            WHERE last_seen >= ?
            GROUP BY ip_address, hour
            ORDER BY ip_address, hour
        """, (start_time.strftime('%Y-%m-%d %H:%M:%S'),))

        rows = cursor.fetchall()
        disconnect_from_db(conn)

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
        disconnect_from_db(conn)
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
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "alerts")
    
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
        disconnect_from_db(conn)
        
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
        disconnect_from_db(conn)
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
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, )
    
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
        disconnect_from_db(conn)
        
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
        disconnect_from_db(conn)
        log_error(logger, f"[ERROR] Database error fetching alerts for IP {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to get alerts for IP {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}

# API for CONST_CONSOLIDATED_DB
@app.route('/api/whitelist', method=['GET', 'POST'])
def whitelist():
    db_name = CONST_CONSOLIDATED_DB
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
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, "Fetched all whitelist entries successfully.")
            return json.dumps([{"whitelist_id": row[0], "src_ip": row[1], "dst_ip": row[2], "dst_port": row[3], "protocol": row[4], "added": row[5]} for row in rows])
        except sqlite3.Error as e:
            disconnect_from_db(conn)
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
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, f"Added new whitelist entry: {whitelist_id} {src_ip} -> {dst_ip}:{dst_port}/{protocol}")
            return {"message": "Whitelist entry added successfully"}
        except sqlite3.Error as e:
            disconnect_from_db(conn)
            log_error(logger, f"Error adding whitelist entry: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/whitelist/<id>', method=['PUT', 'DELETE'])
def modify_whitelist(id):
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "whitelist")
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
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, f"Updated whitelist entry: {id}")
            return {"message": "Whitelist entry updated successfully"}
        except sqlite3.Error as e:
            disconnect_from_db(conn)
            log_error(logger, f"Error updating whitelist entry: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'DELETE':
        # Delete a whitelist entry
        try:
            cursor.execute("DELETE FROM whitelist WHERE id = ?", (id,))
            conn.commit()
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, f"Deleted whitelist entry: {id}")
            return {"message": "Whitelist entry deleted successfully"}
        except sqlite3.Error as e:
            disconnect_from_db(conn)
            log_error(logger, f"Error deleting whitelist entry: {e}")
            response.status = 500
            return {"error": str(e)}

# API for CONST_CONSOLIDATED_DB
@app.route('/api/localhosts', method=['GET'])
def localhosts():
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "localhosts")
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            # Fetch all local hosts
            cursor.execute("SELECT * FROM localhosts")
            rows = cursor.fetchall()
            disconnect_from_db(conn)
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
            disconnect_from_db(conn)
            log_error(logger, f"Error fetching local hosts: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/localhosts/<ip_address>', method=['PUT'])
def modify_localhost(ip_address):
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "localhosts")
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
            disconnect_from_db(conn)
            set_json_response()
            log_info(logger, f"Updated local host: {ip_address}")
            return {"message": "Local host updated successfully"}
        except sqlite3.Error as e:
            disconnect_from_db(conn)
            log_error(logger, f"Error updating local host: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/localhosts/<ip_address>', method=['DELETE'])
def delete_localhost(ip_address):
    """
    API endpoint to delete a local host by its IP address.

    Args:
        ip_address: The IP address of the local host to delete.

    Returns:
        JSON object indicating success or failure.
    """
    logger = logging.getLogger(__name__)
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "localhosts")

    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    try:
        # Delete the local host with the specified IP address
        cursor.execute("DELETE FROM localhosts WHERE ip_address = ?", (ip_address,))
        conn.commit()
        disconnect_from_db(conn)

        set_json_response()
        log_info(logger, f"[INFO] Deleted local host with IP address: {ip_address}")
        return {"message": f"Local host with IP address {ip_address} deleted successfully"}
    except sqlite3.Error as e:
        disconnect_from_db(conn)
        log_error(logger, f"[ERROR] Error deleting local host with IP address {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error deleting local host with IP address {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}
    

@app.route('/api/localhosts/<ip_address>', method=['GET'])
def get_localhost(ip_address):
    """
    API endpoint to get information for a single local host by IP address.

    Args:
        ip_address: The IP address of the local host to retrieve.

    Returns:
        JSON object containing the local host's details or an error message.
    """
    logger = logging.getLogger(__name__)
    db_name = CONST_CONSOLIDATED_DB
    conn = connect_to_db(db_name, "localhosts")
    
    if not conn:
        log_error(logger, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    try:
        # Fetch the local host with the specified IP address
        cursor.execute("SELECT * FROM localhosts WHERE ip_address = ?", (ip_address,))
        row = cursor.fetchone()
        disconnect_from_db(conn)

        if row:
            # Format the response
            localhost = {
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
            }
            set_json_response()
            log_info(logger, f"Fetched local host details for IP address: {ip_address}")
            return json.dumps(localhost, indent=2)
        else:
            log_warn(logger, f"No local host found for IP address: {ip_address}")
            response.status = 404
            return {"error": f"No local host found for IP address: {ip_address}"}

    except sqlite3.Error as e:
        disconnect_from_db(conn)
        log_error(logger, f"Error fetching local host for IP address {ip_address}: {e}")
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


@app.route('/api/trafficstats/<ip_address>', method=['GET'])
def get_traffic_stats(ip_address):
    """
    API endpoint to get all traffic statistics for a specific IP address.

    Args:
        ip_address: The IP address to filter traffic statistics by.

    Returns:
        JSON object containing the traffic statistics for the specified IP address.
    """
    logger = logging.getLogger(__name__)
    try:
        
        # Call the function to get traffic stats for the IP address
        traffic_stats = get_traffic_stats_for_ip(ip_address)

        if traffic_stats:
            set_json_response()
            log_info(logger, f"[INFO] Successfully retrieved traffic stats for IP address {ip_address}")
            return json.dumps(traffic_stats, indent=2)
        else:
            set_json_response()
            log_warn(logger, f"[WARN] No traffic stats found for IP address {ip_address}")
            return json.dumps([])  # Return an empty list instead of a 404 error

    except Exception as e:
        log_error(logger, f"[ERROR] Failed to get traffic stats for IP address {ip_address}: {e}")
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

@app.route('/api/actions/<action_id>/acknowledge', method=['PUT'])
def update_action_acknowledged_api(action_id):
    """
    API endpoint to update the acknowledged field for a specific action.

    Args:
        action_id: The ID of the action to update.

    Returns:
        JSON object indicating success or failure.
    """
    logger = logging.getLogger(__name__)
    try:
        
        if update_action_acknowledged(action_id):
            return {"message": f"Action with ID {action_id} acknowledged successfully"}
        else:
            response.status = 500
            return {"error": f"Failed to acknowledge action with ID {action_id}"}
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to acknowledge action with ID {action_id}: {e}")
        response.status = 500
        return {"error": str(e)}

@app.route('/api/actions', method=['POST'])
def insert_action_api():
    """
    API endpoint to insert a new action into the database.

    Returns:
        JSON object indicating success or failure.
    """
    logger = logging.getLogger(__name__)
    try:
        action_data = request.json
        if insert_action(action_data):
            return {"message": "Action inserted successfully"}
        else:
            response.status = 500
            return {"error": "Failed to insert action"}
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to insert action: {e}")
        response.status = 500
        return {"error": str(e)}


@app.route('/api/actions', method=['GET'])
def get_actions():
    """
    API endpoint to retrieve all actions from the database.

    Returns:
        JSON object containing all actions.
    """
    logger = logging.getLogger(__name__)
    try:
        actions = get_all_actions()
        set_json_response()
        return json.dumps(actions, indent=2)
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to retrieve actions: {e}")
        response.status = 500
        return {"error": str(e)}

@app.route('/api/investigate/<ip_address>', method=['GET'])
def investigate_ip(ip_address):
    """
    API endpoint to investigate an IP address by performing reverse DNS lookup
    and geolocation lookup.

    Args:
        ip_address: The IP address to investigate.

    Returns:
        JSON object containing the IP address, country, and DNS lookup results.
    """
    logger = logging.getLogger(__name__)
    try:
        result = {
            "ip_address": ip_address,
            "dns": None,
            "country": None
        }
        
        # Get configuration settings
        config_dict = get_config_settings()

        DNS_SERVERS = config_dict['ApprovedLocalDnsServersList'].split(',')

        if DNS_SERVERS and config_dict.get('DiscoveryReverseDns', 0) > 0:
            dns_results = dns_lookup([ip_address], DNS_SERVERS, config_dict)
            log_info(logger, f"[INFO] DNS Results: {dns_results}")
            
            # Handle the returned format properly
            if isinstance(dns_results, list):
                # Find the result for our IP
                for entry in dns_results:
                    if entry.get('ip') == ip_address:
                        result["dns"] = entry.get('dns_hostname')
                        break
            elif isinstance(dns_results, dict) and ip_address in dns_results:
                # Handle the old format for backward compatibility
                result["dns"] = dns_results[ip_address]
        else:
            log_info(logger, "[INFO] DNS lookup skipped - no DNS servers configured or discovery disabled")

        # Perform geolocation lookup
        geo_result = lookup_ip_country(ip_address)
        if geo_result:
            result["country"] = geo_result
        else:
            log_info(logger, f"[INFO] No geolocation result found for IP: {ip_address}")

        set_json_response()
        log_info(logger, f"[INFO] Successfully investigated IP address: {ip_address}")
        return json.dumps(result, indent=2)
        
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to investigate IP address {ip_address}: {e}")
        response.status = 500
        return {"error": str(e)}
    

@app.route('/api/services/<port>', method=['GET'])
def get_services_by_port_api(port):
    """
    API endpoint to get service information for a specific port.
    
    Args:
        port (str): The port number to retrieve service information for.
        
    Returns:
        JSON object containing service information for the specified port.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Convert port to integer
        port_number = int(port)
        
        # Import the function from database.py
        from src.database import get_services_by_port
        
        # Get service information for the port
        services = get_services_by_port(port_number)
        
        if not services:
            log_info(logger, f"[INFO] No services found for port {port_number}")
            return json.dumps({})
        
        set_json_response()
        log_info(logger, f"[INFO] Retrieved service information for port {port_number}")
        return json.dumps(services, indent=2)
        
    except ValueError:
        log_error(logger, f"[ERROR] Invalid port number: {port}")
        response.status = 400
        return {"error": "Invalid port number"}
    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Database error fetching services for port {port}: {e}")
        response.status = 500
        return {"error": str(e)}
    except Exception as e:
        log_error(logger, f"[ERROR] Failed to get services for port {port}: {e}")
        response.status = 500
        return {"error": str(e)}


# Run the Bottle app
if __name__ == '__main__':
    logger = logging.getLogger(__name__) 
    log_info(logger, "Starting API server...")
    app.run(host=API_LISTEN_ADDRESS, port=API_LISTEN_PORT, debug=False)