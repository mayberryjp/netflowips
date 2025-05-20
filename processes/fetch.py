
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
import time
import logging
from integrations.tor import update_tor_nodes
from integrations.geolocation import create_geolocation_db
from src.client import upload_all_client_definitions, upload_configuration
from integrations.reputation import import_reputation_list
from integrations.piholedns import get_pihole_ftl_logs
from integrations.services import create_services_db
from src.const import CONST_REINITIALIZE_DB, CONST_CONSOLIDATED_DB, IS_CONTAINER
from init import *

if (IS_CONTAINER):
    REINITIALIZE_DB=os.getenv("REINITIALIZE_DB", CONST_REINITIALIZE_DB)

def main():
    """
    Main program to fetch and update external data at a fixed interval.
    """
    logger = logging.getLogger(__name__)
    log_info(logger, "[INFO] Starting external data fetcher")
    config_dict = get_config_settings()
    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        exit(1)

    fetch_interval = config_dict.get('IntegrationFetchInterval',3600)
    # Fixed interval in seconds (e.g., 24 hours = 86400 seconds)

    while True:

        delete_old_traffic_stats()

        config_dict = get_config_settings()
        if not config_dict:
            log_error(logger, "[ERROR] Failed to load configuration settings")
            exit(1)
        # Call the update_tor_nodes function

        try: 
            if config_dict.get('TorFlowDetection',0) > 0:
                log_info(logger, "[INFO] Fetching and updating Tor node list...")
                update_tor_nodes(config_dict)
                log_info(logger, "[INFO] Tor node list update finished.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")

        try: 
            if config_dict.get('GeolocationFlowsDetection',0) > 0:
                log_info(logger, "[INFO] Fetching and updating geolocation data..")
                create_geolocation_db()
                log_info(logger, "[INFO] Geolocation update finished.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")

        try: 
            if config_dict.get('ReputationListDetection', 0) > 0:
                log_info(logger, "[INFO] Fetching and updating reputation list...")
                import_reputation_list(config_dict)
                log_info(logger, "[INFO] Reputation list update finished.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")

        try: 
            if config_dict.get('StorePiHoleDnsQueryHistory', 0) > 0:
                log_info(logger, "[INFO] Fetching pihole dns query history...")
                get_pihole_ftl_logs(50000,config_dict)
                log_info(logger, "[INFO] Pihole dns query history finished.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")

        try: 
            if config_dict.get('SendDeviceClassificationsToHomelabApi', 0) > 0:
                log_info(logger, "[INFO] Sending device classifications to Homelab API...")
                upload_all_client_definitions()
                log_info(logger, "[INFO] Device classification upload finished.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")

        try: 
            if config_dict.get('SendConfigurationToCloudApi', 0) > 0:
                log_info(logger, "[INFO] Sending instance configuration to Homelab API...")
                upload_configuration()
                log_info(logger, "[INFO] Instance configuration upload finished.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")

        try: 
            if config_dict.get('ImportServicesList', 0) > 0:
                log_info(logger, "[INFO] Fetching and updating services list...")
                create_services_db()
                log_info(logger, "[INFO] Services list download finished.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")


        # Wait for the next interval
        log_info(logger, f"[INFO] Sleeping for {fetch_interval} seconds before the next fetch.")
        time.sleep(fetch_interval)

if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    STARTUP_DELAY = 5
    log_info(logger,f"[INFO] Starting fetcher, waiting {STARTUP_DELAY} seconds before starting processing")
    time.sleep(STARTUP_DELAY)
    main()