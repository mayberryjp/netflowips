import requests
from src.const import IS_CONTAINER, VERSION, CONST_SITE
from database.configuration import get_config_settings
import os
import logging
from src.locallogging import log_info, log_error, log_warn
from database.alerts import log_alert_to_db
from notifications.telegram import send_telegram_message

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