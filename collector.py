from const import VERSION, CONST_LISTEN_ADDRESS, CONST_LISTEN_PORT, IS_CONTAINER
from database import delete_newflowsdb, init_newflows_db, init_config_db
from netflow import handle_netflow_v5
from utils import log_info

# Entry point
if __name__ == "__main__":
    log_info(None, f"[INFO] Starting NetFlow v5 collector {VERSION}")
    delete_newflowsdb()
    init_newflows_db()
    init_config_db()
    handle_netflow_v5()
