from const import CONST_WHITELIST_DB, CONST_CREATE_WHITELIST_SQL, VERSION, CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL, IS_CONTAINER, CONST_SITE, CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL
from database import get_whitelist,init_configurations_from_variable,store_machine_unique_identifier,import_whitelists, delete_database, create_database, get_config_settings, init_configurations_from_sitepy
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
        log_info(logger, f"[INFO] Loading site-specific configuration from {site_config_path}. Leaving this file will overwrite the config database every time, so be careful. It's usually only meant for a one time bootstrapping of a new site with a full config.")
        delete_database(CONST_CONFIG_DB)
        create_database(CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL)
        create_database(CONST_WHITELIST_DB, CONST_CREATE_WHITELIST_SQL)
        config_dict = init_configurations_from_sitepy()
        store_machine_unique_identifier()
        import_whitelists(config_dict)
    else:
        log_info(logger, f"[INFO] No site-specific configuration found at {site_config_path}. This is OK. ")

    if not os.path.exists(CONST_CONFIG_DB) and not os.path.exists(site_config_path):
        log_info(logger, f"[INFO] Config database not found, creating at {CONST_CONFIG_DB}. We assume this is a first time install with no config so we're importing a basic default config with everything turned off. ")
        create_database(CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL)
        create_database(CONST_WHITELIST_DB, CONST_CREATE_WHITELIST_SQL)
        config_dict = init_configurations_from_variable()
        store_machine_unique_identifier()

    config_dict = get_config_settings()

    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        exit(1)

    log_info(logger, f"[INFO] Current configuration at start, config will refresh automatically every time processor runs:\n {dump_json(config_dict)}")
    log_info(logger, f"[INFO] Starting NetFlow v5 collector {VERSION} at {SITE}")
    delete_database(CONST_NEWFLOWS_DB)
    create_database(CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL)
    if config_dict['StartCollector'] == 1:
        # Start the collector
        handle_netflow_v5()
