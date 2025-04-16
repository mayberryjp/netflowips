from const import VERSION, CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL
from database import   delete_database, create_database
from netflow import handle_netflow_v5
from utils import log_info

# Entry point
if __name__ == "__main__":
    log_info(None, f"[INFO] Starting NetFlow v5 collector {VERSION}")
    delete_database(CONST_NEWFLOWS_DB)
    create_database(CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL)
    handle_netflow_v5()
