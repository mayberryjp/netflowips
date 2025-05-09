from bottle import Bottle
from apifunctions import (
    configurations,
    get_traffic_stats,
    update_action_acknowledged_api,
    insert_action_api,
    get_actions,
)
from const import IS_CONTAINER, CONST_API_LISTEN_ADDRESS, CONST_API_LISTEN_PORT
from utils import log_info
import os
import logging

# Initialize the Bottle app
app = Bottle()

if IS_CONTAINER:
    API_LISTEN_ADDRESS = os.getenv("API_LISTEN_ADDRESS", CONST_API_LISTEN_ADDRESS)
    API_LISTEN_PORT = os.getenv("API_LISTEN_PORT", CONST_API_LISTEN_PORT)

# Route Definitions
app.route("/api/configurations", method=["GET", "POST"], callback=configurations)
app.route("/api/trafficstats/<ip_address>", method="GET", callback=get_traffic_stats)
app.route(
    "/api/actions/<action_id>/acknowledge",
    method="PUT",
    callback=update_action_acknowledged_api,
)
app.route("/api/actions", method="POST", callback=insert_action_api)
app.route("/api/actions", method="GET", callback=get_actions)

# Run the Bottle app
if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    log_info(logger, "Starting API server...")
    app.run(host=API_LISTEN_ADDRESS, port=API_LISTEN_PORT, debug=False)