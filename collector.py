from const import VERSION, CONST_NEWFLOWS_DB
from database import  init_newflows_db, delete_database
from netflow import handle_netflow_v5
from utils import log_info

# Entry point
if __name__ == "__main__":
    log_info(None, f"[INFO] Starting NetFlow v5 collector {VERSION}")
    delete_database(CONST_NEWFLOWS_DB)
    init_newflows_db()
    handle_netflow_v5()
