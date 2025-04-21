from const import VERSION, CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL, CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL, IS_CONTAINER, CONST_SITE
from database import delete_database, create_database, get_config_settings, init_configurations
from netflow import handle_netflow_v5
from utils import log_info, log_error
import logging
import os

if (IS_CONTAINER):
    SITE = os.getenv("SITE", CONST_SITE)

# Entry point
if __name__ == "__main__":

    create_database(CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL)
    init_configurations()
    config_dict = get_config_settings()
    logger = logging.getLogger(__name__) 
    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        exit(1)

    log_info(logger, f"[INFO] Starting NetFlow v5 collector {VERSION} at {SITE}")
    delete_database(CONST_NEWFLOWS_DB)
    create_database(CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL)
    if config_dict['StartCollector'] == 1:
        # Start the collector
        handle_netflow_v5()
