from const import VERSION, CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL, IS_CONTAINER, CONST_SITE, CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL
from database import delete_database, create_database, get_config_settings, init_configurations
from netflow import handle_netflow_v5
from utils import log_info, log_error, dump_json
import logging
import os
import sys
sys.path.insert(0, "/database")

if (IS_CONTAINER):
    SITE = os.getenv("SITE", CONST_SITE)

# Entry point
if __name__ == "__main__":

    logger = logging.getLogger(__name__) 

    # Check if a site-specific configuration file exists
    site_config_path = os.path.join("/database", f"{SITE}.py")
    if os.path.exists(site_config_path):
        log_info(logger, f"[INFO] Loading site-specific configuration from {site_config_path}")
        delete_database(CONST_CONFIG_DB)
        create_database(CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL)
        init_configurations()
    else:
        log_info(logger, f"[INFO] No site-specific configuration found at {site_config_path}")

    config_dict = get_config_settings()

    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        exit(1)

    log_info(logger, f"Current configuration at start, config will refresh automatically every time processor runs:\n {dump_json(config_dict)}")
    log_info(logger, f"[INFO] Starting NetFlow v5 collector {VERSION} at {SITE}")
    delete_database(CONST_NEWFLOWS_DB)
    create_database(CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL)
    if config_dict['StartCollector'] == 1:
        # Start the collector
        handle_netflow_v5()
