from datetime import datetime, timedelta
from database.alerts import log_alert_to_db
from database.allflows import update_tag_to_allflows
from src.notifications import send_telegram_message  # Import notification functions
import logging
from src.const import CONST_CONSOLIDATED_DB
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import time
# Set up path for imports
current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
sys.path.insert(0, "/database")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from locallogging import log_info, log_error, log_warn
from init import * 
from database.newflows import get_new_flows


from detections.detect_custom_tag import detect_custom_tag
from detections.detect_dead_connections import detect_dead_connections
from detections.detect_new_outbound_connections import detect_new_outbound_connections
from detections.detect_new_inbound_connections import detect_new_inbound_connections
from detections.detect_geolocation_flows import detect_geolocation_flows
from detections.detect_router_flows import router_flows_detection
from detections.detect_foreign_flows import foreign_flows_detection


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



def handle_alert(config_dict, detection_key, telegram_message, local_ip, original_flow, alert_category, enrichment_1, enrichment_2, alert_id_hash):
    """
    Handle alerting logic based on the configuration level.

    Args:
        config_dict (dict): Configuration dictionary.
        detection_key (str): The key in the configuration dict for the detection type (e.g., "NewOutboundDetection").
        src_ip (str): Source IP address.
        row (list): The flow data row.
        alert_message (str): The alert message to send.
        dst_ip (str): Destination IP address.
        dst_port (int): Destination port.
        alert_id (str): Unique identifier for the alert.

    Returns:
        str: "insert", "update", or None based on the operation performed.
    """
    logger = logging.getLogger(__name__)

    # Get the detection level from the configuration
    detection_level = config_dict.get(detection_key, 0)

    if detection_level >= 2:
        # Send Telegram alert and log to database
        insert_or_update = log_alert_to_db(local_ip, original_flow, alert_category, enrichment_1, enrichment_2, alert_id_hash, False)
                #insert_or_update = log_alert_to_db(local_ip, original_flow, category, enrichment_1, enrichment_2, alert_id, False)
#                           def log_alert_to_db(ip_address, flow, category, alert_enrichment_1, alert_enrichment_2, alert_id_hash, realert=False):
 
        if insert_or_update == "insert":
            send_telegram_message(telegram_message, original_flow)
        elif insert_or_update == "update" and detection_level == 3:
            send_telegram_message(telegram_message, original_flow)

        return insert_or_update

    elif detection_level == 1:
        # Only log to database
        return log_alert_to_db(local_ip, original_flow, alert_category, enrichment_1, enrichment_2, alert_id_hash, False)

    return None