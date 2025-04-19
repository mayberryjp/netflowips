from const import VERSION, CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL, IS_CONTAINER, CONST_START_COLLECTOR
from database import delete_database, create_database
from netflow import handle_netflow_v5
from utils import log_info
import logging
import os

if (IS_CONTAINER):
    START_COLLECTOR = os.getenv("START_COLLECTOR", CONST_START_COLLECTOR)

# Entry point
if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    log_info(logger, f"[INFO] Starting NetFlow v5 collector {VERSION}")
    delete_database(CONST_NEWFLOWS_DB)
    create_database(CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL)
    handle_netflow_v5()
