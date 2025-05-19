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

def setup_trafficstats_routes(app):
        
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
                response.content_type = 'application/json'
                log_info(logger, f"[INFO] Successfully retrieved traffic stats for IP address {ip_address}")
                return json.dumps(traffic_stats, indent=2)
            else:
                response.content_type = 'application/json'
                log_warn(logger, f"[WARN] No traffic stats found for IP address {ip_address}")
                return json.dumps([])  # Return an empty list instead of a 404 error

        except Exception as e:
            log_error(logger, f"[ERROR] Failed to get traffic stats for IP address {ip_address}: {e}")
            response.status = 500
            return {"error": str(e)}