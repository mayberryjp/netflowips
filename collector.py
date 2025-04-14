import sqlite3
from datetime import datetime
import logging
from const import VERSION, CONST_LISTEN_ADDRESS, CONST_LISTEN_PORT, IS_CONTAINER
from database import delete_newflowsdb, init_newflows_db, init_config_db
from netflow import handle_netflow_v5
import os
from utils import log_info

# Entry point
if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    log_info(logger, f"[INFO] Starting NetFlow v5 collector {VERSION}")
    delete_newflowsdb()
    init_newflows_db()
    init_config_db()
    handle_netflow_v5()
