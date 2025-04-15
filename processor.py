import sqlite3  # Import the sqlite3 module
from database import connect_to_db, update_allflows, delete_all_records_from_newflows, get_config_settings, init_alerts_db # Import from database.py
from detections import update_local_hosts  # Import update_local_hosts from detections.py
#from maxmind import create_geolocation_db  # Import the function from maxmind.py
from utils import log_info  # Import log_info from utils
from const import CONST_PROCESSING_INTERVAL, IS_CONTAINER,CONST_NEWFLOWS_DB  # Import PROCESSING_INTERVAL from const
import schedule
import time
import logging
import os

# Initialize logger
logger = logging.getLogger(__name__)

if (IS_CONTAINER):
    PROCESSING_INTERVAL=os.getenv("PROCESSING_INTERVAL", CONST_PROCESSING_INTERVAL)

# Function to process data
def process_data():
    config_dict=get_config_settings()
    init_alerts_db()
    """Read data from the database and process it."""
    conn = connect_to_db(CONST_NEWFLOWS_DB)
    if conn:
        try:
            cursor = conn.cursor()
            # Fetch all rows from the flows table
            cursor.execute("SELECT * FROM flows")  # Replace 'flows' with your table name
            rows = cursor.fetchall()
            # Delete all records from newflows.db after processing
            delete_all_records_from_newflows()
            # Log the number of rows fetched
            log_info(logger, f"[INFO] Fetched {len(rows)} rows from the database.")

            # Pass the rows to update_local_hosts
            update_local_hosts(rows,config_dict)

            # Pass the rows to update_all_flows
            update_allflows(rows, config_dict)

        except sqlite3.Error as e:
            log_info(logger, f"[ERROR] Error reading from database: {e}")
        finally:
            conn.close()

# Schedule the task to run every 60 seconds
schedule.every(PROCESSING_INTERVAL).seconds.do(process_data)

if __name__ == "__main__":
    log_info(logger, "[INFO] Processor started.")
    while True:
        schedule.run_pending()
        time.sleep(1)