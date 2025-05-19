
import sys
import os
from pathlib import Path
current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
sys.path.insert(0, parent_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
src_dir = f"{parent_dir}/src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
from bottle import Bottle, request, response, hook, route
import logging
from init import *
app = Bottle()

def setup_integrations_routes(app):
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
                response.content_type = 'application/json'
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

    @app.route('/api/homeassistant', method=['GET'])
    def get_database_counts():
        """
        API endpoint to get counts from the alerts, localhosts, and ignorelist tables.
        """
        logger = logging.getLogger(__name__)
        try:
            # Call the function to collect database counts
            counts = collect_database_counts()
            response.content_type = 'application/json'
            log_info(logger, "[INFO] Fetched database counts successfully.")
            return json.dumps(counts)
        except Exception as e:
            log_error(logger, f"[ERROR] Failed to fetch database counts: {e}")
            response.status = 500
            return {"error": str(e)}
        

    @app.route('/api/homepage', method=['GET'])
    def get_database_counts():
        """
        API endpoint to get counts from the alerts, localhosts, and ignorelist tables.
        """
        logger = logging.getLogger(__name__)
        try:
            # Call the function to collect database counts
            counts = collect_database_counts()
            response.content_type = 'application/json'
            log_info(logger, "[INFO] Fetched database counts successfully.")
            return json.dumps(counts)
        except Exception as e:
            log_error(logger, f"[ERROR] Failed to fetch database counts: {e}")
            response.status = 500
            return {"error": str(e)}
        
    @app.route('/api/quickstats', method=['GET'])
    def get_database_counts():
        """
        API endpoint to get counts from the alerts, localhosts, and ignorelist tables.
        """
        logger = logging.getLogger(__name__)
        try:
            # Call the function to collect database counts
            counts = collect_database_counts()
            response.content_type = 'application/json'
            log_info(logger, "[INFO] Fetched database counts successfully.")
            return json.dumps(counts)
        except Exception as e:
            log_error(logger, f"[ERROR] Failed to fetch database counts: {e}")
            response.status = 500
            return {"error": str(e)}