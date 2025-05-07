from const import CONST_CREATE_GEOLOCATION_SQL, CONST_CREATE_REPUTATIONLIST_SQL, CONST_CREATE_TORNODES_SQL, CONST_CREATE_PIHOLE_SQL, CONST_CREATE_LOCALHOSTS_SQL, CONST_CREATE_ALLFLOWS_SQL, CONST_CREATE_ALERTS_SQL, CONST_CREATE_TRAFFICSTATS_SQL, CONST_CONSOLIDATED_DB, CONST_CREATE_CUSTOMTAGS_SQL, CONST_CREATE_WHITELIST_SQL, VERSION, CONST_CREATE_NEWFLOWS_SQL, IS_CONTAINER, CONST_SITE, CONST_CREATE_CONFIG_SQL
from database import delete_all_records, import_custom_tags, create_table, get_whitelist,init_configurations_from_variable,store_machine_unique_identifier,import_whitelists, delete_database, create_table, get_config_settings, init_configurations_from_sitepy
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
 
    site_config_path = os.path.join("/database/", f"{SITE}.py")
    
    if not os.path.exists(CONST_CONSOLIDATED_DB):
        log_info(logger, f"[INFO] Consolidated database not found, creating at {CONST_CONSOLIDATED_DB}. We assume this is a first time install. ")
        create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_CUSTOMTAGS_SQL)
        log_info(logger, f"[INFO] No site-specific configuration found at {site_config_path}. This is OK. ")    
        config_dict = init_configurations_from_variable()

    if os.path.exists(site_config_path):
        log_info(logger, f"[INFO] Loading site-specific configuration from {site_config_path}. Leaving this file will overwrite the config database every time, so be careful. It's usually only meant for a one time bootstrapping of a new site with a full config.")
        delete_all_records(CONST_CONSOLIDATED_DB, "configuration")
        config_dict = init_configurations_from_sitepy()
        create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_WHITELIST_SQL)
        create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_CUSTOMTAGS_SQL)
        import_whitelists(config_dict)
        import_custom_tags(config_dict)
    else:
        log_info(logger, f"[INFO] No site-specific configuration found at {site_config_path}. This is OK. ")

    store_machine_unique_identifier()

    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_CONFIG_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_WHITELIST_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_CUSTOMTAGS_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_TRAFFICSTATS_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_ALERTS_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_ALLFLOWS_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_NEWFLOWS_SQL)
    delete_all_records(CONST_CONSOLIDATED_DB,"flows")
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_LOCALHOSTS_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_GEOLOCATION_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_REPUTATIONLIST_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_TORNODES_SQL)
    create_table(CONST_CONSOLIDATED_DB, CONST_CREATE_PIHOLE_SQL)

    config_dict = get_config_settings()

    if not config_dict:
        log_error(logger, "[ERROR] Failed to load configuration settings")
        exit(1)

    log_info(logger, f"[INFO] Current configuration at start, config will refresh automatically every time processor runs:\n {dump_json(config_dict)}")
    log_info(logger, f"[INFO] Starting NetFlow v5 collector {VERSION} at {SITE}")
    if config_dict['StartCollector'] == 1:
        # Start the collector
        handle_netflow_v5()
