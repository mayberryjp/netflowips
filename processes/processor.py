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
sys.path.insert(0, "/database")
import sqlite3  # Import the sqlite3 module
from init import *
from src.detections import detect_custom_tag, detect_reputation_flows, update_local_hosts, detect_geolocation_flows, detect_new_outbound_connections, router_flows_detection, local_flows_detection, foreign_flows_detection, detect_unauthorized_dns, detect_unauthorized_ntp, detect_incorrect_authoritative_dns, detect_incorrect_ntp_stratum , detect_dead_connections, detect_vpn_traffic, detect_high_risk_ports, detect_many_destinations, detect_port_scanning, detect_tor_traffic, detect_high_bandwidth_flows
from src.notifications import send_test_telegram_message  # Import send_test_telegram_message from notifications.py
from integrations.geolocation import load_geolocation_data
from integrations.reputation import load_reputation_data
from src.const import CONST_REINITIALIZE_DB, IS_CONTAINER, CONST_CONSOLIDATED_DB
import schedule
import time
import logging
from src.detections import process_data

if (IS_CONTAINER):
    REINITIALIZE_DB=os.getenv("REINITIALIZE_DB", CONST_REINITIALIZE_DB)

if __name__ == "__main__":

    logger = logging.getLogger(__name__)

    STARTUP_DELAY = 30
    log_info(logger,f"[INFO] Processor process pausing {STARTUP_DELAY} seconds before starting up")
    # wait a bit for startup so collector can init configurations
    time.sleep(STARTUP_DELAY)

    config_dict = get_config_settings()

    log_info(logger, f"[INFO] Processor started.")

    send_test_telegram_message()

    while True:

        config_dict = get_config_settings()
        if not config_dict:
            log_error(logger, "[ERROR] Failed to load configuration settings")
            exit(1)

        PROCESS_RUN_INTERVAL = config_dict.get('ProcessRunInterval', 60)
        log_info(logger, f"[INFO] Process run interval set to {PROCESS_RUN_INTERVAL} seconds.")

        process_data()
        time.sleep(PROCESS_RUN_INTERVAL)