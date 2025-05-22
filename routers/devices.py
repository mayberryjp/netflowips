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
import json
from init import *
from src.devicecategories import CONST_DEVICE_CATEGORIES
app = Bottle()

def setup_devices_routes(app):
    """
    Set up routes for device categories.
    
    Args:
        app: The Bottle application object
    """
    
    @app.route('/api/devices', method=['GET'])
    def get_device_categories():
        """
        API endpoint to get all device categories.

        Returns:
            JSON array containing only the category names without icons.
        """
        logger = logging.getLogger(__name__)
        
        try:
            # Extract only the category names from the device categories
            category_names = [item["category"] for item in CONST_DEVICE_CATEGORIES]
            
            response.content_type = 'application/json'
            log_info(logger, f"[INFO] Fetched {len(category_names)} device category names successfully")
            return json.dumps(category_names, indent=2)
            
        except Exception as e:
            log_error(logger, f"[ERROR] Failed to fetch device categories: {e}")
            response.status = 500
            return {"error": str(e)}