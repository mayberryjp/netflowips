import time
import logging
from integrations.tor import update_tor_nodes
from utils import log_info, log_error
from database import get_config_settings, delete_database, delete_all_records, create_database
from integrations.maxmind import create_geolocation_db
from integrations.reputation import import_reputation_list
from integrations.piholedns import get_pihole_ftl_logs
from const import CONST_REINITIALIZE_DB, CONST_GEOLOCATION_DB, IS_CONTAINER
import os

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

    fetch_interval = config_dict.get('IntegrationFetchInterval',3660)
    # Fixed interval in seconds (e.g., 24 hours = 86400 seconds)

    if (REINITIALIZE_DB):
        delete_database(CONST_GEOLOCATION_DB)

    while True:

        config_dict = get_config_settings()
        if not config_dict:
            log_error(logger, "[ERROR] Failed to load configuration settings")
            exit(1)
        # Call the update_tor_nodes function

        try: 
            if config_dict.get('TorFlowDetection',0) > 0:
                log_info(logger, "[INFO] Fetching and updating Tor node list...")
                update_tor_nodes(config_dict)
                log_info(logger, "[INFO] Tor node list updated successfully.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")

        try: 
            if config_dict.get('GeolocationFlowsDetection',0) > 0:
                log_info(logger, "[INFO] Fetching and updating geolocation data..")
                create_geolocation_db()
                log_info(logger, "[INFO] Geolocation data updated successfully.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")

        try: 
            if config_dict.get('ReputationListDetection', 0) > 0:
                log_info(logger, "[INFO] Fetching and updating reputation list...")
                import_reputation_list(config_dict)
                log_info(logger, "[INFO] Reputation list updated successfully.")
        except Exception as e:
            log_error(logger, f"[ERROR] Error during data fetch: {e}")

        try: 
            if config_dict.get('StorePiHoleDnsQueryHistory', 0) > 0:
                log_info(logger, "[INFO] Fetching pihole dns query history...")
                get_pihole_ftl_logs(10000,config_dict)
                log_info(logger, "[INFO] Pihole dns query history updated successfully.")
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