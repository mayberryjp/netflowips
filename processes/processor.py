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
from database.newflows import get_new_flows

if (IS_CONTAINER):
    REINITIALIZE_DB=os.getenv("REINITIALIZE_DB", CONST_REINITIALIZE_DB)

# Function to process data
def process_data():
    logger = logging.getLogger(__name__)

    log_info(logger,f"[INFO] Processing started.") 

    config_dict = get_config_settings()
    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        return

    newflows = get_new_flows()
    """Read data from the database and process it."""

    if config_dict['ScheduleProcessor'] == 1:
        try:

            if len(newflows) > 0:
                # delete newflows so collector can write clean to it again as quickly as possible
                log_info(logger, f"[INFO] Fetched {len(newflows)} rows from the database.")
                if (config_dict['CleanNewFlows'] == 1):
                    delete_all_records(CONST_CONSOLIDATED_DB, "newflows")

                log_info(logger,f"[INFO] Processing {len(newflows)} rows.")

                # Pass the rows to update_all_flows
                update_all_flows(newflows, config_dict)
                update_traffic_stats(newflows, config_dict)

                if config_dict.get('GeolocationFlowsDetection',0) > 0:
                    geolocation_data = load_geolocation_data()

                if config_dict.get('ReputationListDetection', 0) > 0:
                    reputation_data = load_reputation_data()

                # Proper way to check config values with default of 0
                if config_dict.get("NewHostsDetection", 0) > 0:
                    update_local_hosts(newflows, config_dict)
                
                log_info(logger,f"[INFO] Started removing IgnoreList flows")
                # process ignorelisted entries and remove from detection rows
                filtered_rows = [row for row in newflows if 'IgnoreList' not in str(row[11])]
                log_info(logger,f"[INFO] Finished removing IgnoreList flows - processing flow count is {len(filtered_rows)}")

                if config_dict.get('RemoveBroadcastFlows', 0) >0:
                    filtered_rows = [row for row in filtered_rows if 'Broadcast' not in str(row[11])]
                    log_info(logger,f"[INFO] Finished removing Broadcast flows - processing flow count is {len(filtered_rows)}")

                if config_dict.get('RemoveMulticastFlows', 0) >0:
                    filtered_rows = [row for row in filtered_rows if 'Multicast' not in str(row[11])]
                    log_info(logger,f"[INFO] Finished removing Multicast flows - processing flow count is {len(filtered_rows)}")

                if config_dict.get('RemoveLinkLocalFlows', 0) >0:
                    filtered_rows = [row for row in filtered_rows if 'LinkLocal' not in str(row[11])]
                    log_info(logger,f"[INFO] Finished removing LinkLocal flows - processing flow count is {len(filtered_rows)}")



                if config_dict.get("NewOutboundDetection", 0) > 0:
                    detect_new_outbound_connections(filtered_rows, config_dict)

                if config_dict.get("RouterFlowsDetection", 0) > 0:
                    router_flows_detection(filtered_rows, config_dict)

                if config_dict.get("ForeignFlowsDetection", 0) > 0:
                    foreign_flows_detection(filtered_rows, config_dict)

                if config_dict.get("LocalFlowsDetection", 0) > 0:
                    local_flows_detection(filtered_rows, config_dict)

                if config_dict.get("UnauthorizedDNSDetection", 0) > 0:
                    detect_unauthorized_dns(filtered_rows, config_dict)
                
                if config_dict.get("UnauthorizedNTPDetection", 0) > 0:
                    detect_unauthorized_ntp(filtered_rows, config_dict)

                if config_dict.get("IncorrectAuthoritativeDnsDetection", 0) > 0:
                    detect_incorrect_authoritative_dns(filtered_rows, config_dict) 

                if config_dict.get("IncorrectNtpStratumDetection", 0) > 0:
                    detect_incorrect_ntp_stratum(filtered_rows, config_dict)

                if config_dict.get("GeolocationFlowsDetection", 0) > 0:
                    detect_geolocation_flows(filtered_rows, config_dict, geolocation_data)
                
                if config_dict.get("DeadConnectionDetection", 0) > 0:
                    detect_dead_connections(config_dict)

                if config_dict.get("ReputationListDetection", 0) > 0:
                    detect_reputation_flows(filtered_rows, config_dict, reputation_data)

                if config_dict.get("VpnTrafficDetection", 0) > 0:
                    detect_vpn_traffic(filtered_rows, config_dict)
                
                if config_dict.get("HighRiskPortDetection", 0) > 0:
                    detect_high_risk_ports(filtered_rows, config_dict)      

                if config_dict.get("ManyDestinationsDetection", 0) > 0:
                    detect_many_destinations(filtered_rows, config_dict)  

                if config_dict.get("PortScanDetection", 0) > 0:
                    detect_port_scanning(filtered_rows, config_dict)           

                if config_dict.get("TorFlowDetection", 0) > 0:
                    detect_tor_traffic(filtered_rows, config_dict)     

                if config_dict.get("HighBandwidthFlowDetection", 0) > 0:
                    detect_high_bandwidth_flows(filtered_rows, config_dict)     
        
                if config_dict.get("AlertOnCustomTags", 0) > 0:
                    detect_custom_tag(filtered_rows, config_dict)          
  

        except sqlite3.Error as e:
            log_error(logger, f"[ERROR] Error reading from database: {e}")        
    log_info(logger,f"[INFO] Processing finished.") 


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