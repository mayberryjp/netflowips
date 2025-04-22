from bottle import Bottle, request, response
import sqlite3
import json
import os
from database import connect_to_db
from const import CONST_CONFIG_DB, CONST_ALERTS_DB, CONST_WHITELIST_DB, CONST_LOCALHOSTS_DB, IS_CONTAINER, CONST_API_LISTEN_ADDRESS, CONST_API_LISTEN_PORT
from utils import log_info, log_warn, log_error  # Import logging functions
import logging

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
@app.route('/api/alerts', method=['GET', 'POST'])
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
            log_info(None, "Fetched all alerts successfully.")
            return json.dumps([{"id": row[0], "message": row[1], "timestamp": row[2]} for row in rows])
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error fetching alerts: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'POST':
        # Add a new alert
        data = request.json
        message = data.get('message')
        timestamp = data.get('timestamp')
        try:
            cursor.execute("INSERT INTO alerts (message, timestamp) VALUES (?, ?)", (message, timestamp))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(None, f"Added new alert: {message}")
            return {"message": "Alert added successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error adding alert: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/alerts/<id>', method=['PUT', 'DELETE'])
def modify_alert(id):
    db_name = CONST_ALERTS_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(None, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'PUT':
        # Update an alert
        data = request.json
        message = data.get('message')
        timestamp = data.get('timestamp')
        try:
            cursor.execute("UPDATE alerts SET message = ?, timestamp = ? WHERE id = ?", (message, timestamp, id))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(None, f"Updated alert: {id}")
            return {"message": "Alert updated successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error updating alert: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'DELETE':
        # Delete an alert
        try:
            cursor.execute("DELETE FROM alerts WHERE id = ?", (id,))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(None, f"Deleted alert: {id}")
            return {"message": "Alert deleted successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error deleting alert: {e}")
            response.status = 500
            return {"error": str(e)}

# API for CONST_WHITELIST_DB
@app.route('/api/whitelist', method=['GET', 'POST'])
def whitelist():
    db_name = CONST_WHITELIST_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(None, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            # Fetch all whitelist entries
            cursor.execute("SELECT * FROM whitelist")
            rows = cursor.fetchall()
            conn.close()
            set_json_response()
            log_info(None, "Fetched all whitelist entries successfully.")
            return json.dumps([{"id": row[0], "src_ip": row[1], "dst_ip": row[2], "dst_port": row[3], "protocol": row[4]} for row in rows])
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error fetching whitelist entries: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'POST':
        # Add a new whitelist entry
        data = request.json
        src_ip = data.get('src_ip')
        dst_ip = data.get('dst_ip')
        dst_port = data.get('dst_port')
        protocol = data.get('protocol')
        try:
            cursor.execute("INSERT INTO whitelist (src_ip, dst_ip, dst_port, protocol) VALUES (?, ?, ?, ?)", 
                           (src_ip, dst_ip, dst_port, protocol))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(None, f"Added new whitelist entry: {src_ip} -> {dst_ip}:{dst_port}/{protocol}")
            return {"message": "Whitelist entry added successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error adding whitelist entry: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/whitelist/<id>', method=['PUT', 'DELETE'])
def modify_whitelist(id):
    db_name = CONST_WHITELIST_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(None, f"Unable to connect to the database: {db_name}")
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
            log_info(None, f"Updated whitelist entry: {id}")
            return {"message": "Whitelist entry updated successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error updating whitelist entry: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'DELETE':
        # Delete a whitelist entry
        try:
            cursor.execute("DELETE FROM whitelist WHERE id = ?", (id,))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(None, f"Deleted whitelist entry: {id}")
            return {"message": "Whitelist entry deleted successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error deleting whitelist entry: {e}")
            response.status = 500
            return {"error": str(e)}

# API for CONST_LOCALHOSTS_DB
@app.route('/api/localhosts', method=['GET', 'POST'])
def localhosts():
    db_name = CONST_LOCALHOSTS_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(None, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'GET':
        try:
            # Fetch all local hosts
            cursor.execute("SELECT * FROM localhosts")
            rows = cursor.fetchall()
            conn.close()
            set_json_response()
            log_info(None, "Fetched all local hosts successfully.")
            return json.dumps([{"ip_address": row[0], "first_seen": row[1], "original_flow": row[2]} for row in rows])
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error fetching local hosts: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'POST':
        # Add a new local host
        data = request.json
        ip_address = data.get('ip_address')
        first_seen = data.get('first_seen')
        original_flow = data.get('original_flow')
        try:
            cursor.execute("INSERT INTO localhosts (ip_address, first_seen, original_flow) VALUES (?, ?, ?)", 
                           (ip_address, first_seen, original_flow))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(None, f"Added new local host: {ip_address}")
            return {"message": "Local host added successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error adding local host: {e}")
            response.status = 500
            return {"error": str(e)}

@app.route('/api/localhosts/<ip_address>', method=['PUT', 'DELETE'])
def modify_localhost(ip_address):
    db_name = CONST_LOCALHOSTS_DB
    conn = connect_to_db(db_name)
    if not conn:
        log_error(None, f"Unable to connect to the database: {db_name}")
        return {"error": "Unable to connect to the database"}

    cursor = conn.cursor()

    if request.method == 'PUT':
        # Update a local host
        data = request.json
        first_seen = data.get('first_seen')
        original_flow = data.get('original_flow')
        try:
            cursor.execute("UPDATE localhosts SET first_seen = ?, original_flow = ? WHERE ip_address = ?", 
                           (first_seen, original_flow, ip_address))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(None, f"Updated local host: {ip_address}")
            return {"message": "Local host updated successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error updating local host: {e}")
            response.status = 500
            return {"error": str(e)}

    elif request.method == 'DELETE':
        # Delete a local host
        try:
            cursor.execute("DELETE FROM localhosts WHERE ip_address = ?", (ip_address,))
            conn.commit()
            conn.close()
            set_json_response()
            log_info(None, f"Deleted local host: {ip_address}")
            return {"message": "Local host deleted successfully"}
        except sqlite3.Error as e:
            conn.close()
            log_error(None, f"Error deleting local host: {e}")
            response.status = 500
            return {"error": str(e)}

# Run the Bottle app
if __name__ == '__main__':
    logger = logging.getLogger(__name__) 
    log_info(logger, "Starting API server...")
    app.run(host=API_LISTEN_ADDRESS, port=API_LISTEN_PORT, debug=False)