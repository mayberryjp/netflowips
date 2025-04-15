from const import VERSION, CONST_CONFIG_DB, CONST_NEWFLOWS_DB, CONST_ALERTS_DB
from database import  init_newflows_db, init_config_db, delete_database
from netflow import handle_netflow_v5
from utils import log_info

# Entry point
if __name__ == "__main__":
    log_info(None, f"[INFO] Starting NetFlow v5 collector {VERSION}")
    delete_database(CONST_ALERTS_DB)
    delete_database(CONST_NEWFLOWS_DB)
    init_newflows_db()
    delete_database(CONST_CONFIG_DB)
    init_config_db()
    handle_netflow_v5()
