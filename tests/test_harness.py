import sqlite3
import logging
from datetime import datetime
import os
from pathlib import Path
import sys
import time
import json

current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import log_info, log_warn, log_error
from integrations.maxmind import load_geolocation_data, create_geolocation_db
from integrations.dns import dns_lookup  # Import the dns_lookup function from dns.py
from integrations.piholedhcp import get_pihole_dhcp_clients
from database import get_localhosts

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from const import (
    CONST_NEWFLOWS_DB, 
    CONST_TEST_SOURCE_DB,
    CONST_ALLFLOWS_DB,
    CONST_ALERTS_DB,
    CONST_WHITELIST_DB,
    CONST_LOCALHOSTS_DB,
    CONST_CONFIG_DB,
    CONST_CREATE_ALLFLOWS_SQL,
    CONST_CREATE_ALERTS_SQL,
    CONST_CREATE_WHITELIST_SQL,
    CONST_CREATE_CONFIG_SQL,
    CONST_CREATE_NEWFLOWS_SQL,
    CONST_CREATE_LOCALHOSTS_SQL,
    CONST_CREATE_GEOLOCATION_SQL,
    CONST_GEOLOCATION_DB
)
from utils import log_info

from database import (
    get_config_settings,
    get_whitelist,
    connect_to_db,
    update_allflows,
    delete_database,
    create_database,
    init_configurations,
    get_row_count,
    get_alerts_summary,
    import_whitelists
)
from detections import (
    update_local_hosts,
    detect_new_outbound_connections,
    router_flows_detection,
    foreign_flows_detection,
    local_flows_detection,
    detect_geolocation_flows,
    remove_whitelist,
    detect_dead_connections,
    detect_unauthorized_ntp,
    detect_unauthorized_dns,
    detect_incorrect_authoritative_dns,
    detect_incorrect_ntp_stratum
)


def copy_flows_to_newflows():
    """
    Copy all flows from source databases defined in CONST_TEST_SOURCE_DB to newflows.db
    """
    logger = logging.getLogger(__name__)

    for source_db in CONST_TEST_SOURCE_DB:
        try:
            if not os.path.exists(source_db):
                log_warn(logger, f"[WARN] Database not found: {source_db}")
                continue

            # Connect to source database
            source_conn = sqlite3.connect(source_db)
            source_cursor = source_conn.cursor()

            log_info(logger, f"[INFO] Copying flows from {source_db} to {CONST_NEWFLOWS_DB}")       

            # Get all flows from source
            source_cursor.execute("SELECT * FROM flows")
            rows = source_cursor.fetchall()
            
            log_info(logger, f"[INFO] Fetched {len(rows)} rows from {source_db}")
            # Connect to newflows database
            newflows_conn = sqlite3.connect(CONST_NEWFLOWS_DB)
            newflows_cursor = newflows_conn.cursor()

            log_info(logger, f"[INFO] Preparing to insert flows into {CONST_NEWFLOWS_DB}")
            # Insert flows into newflows
            for row in rows:
                newflows_cursor.execute('''
        INSERT INTO flows (
            src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes, flow_start, flow_end, last_seen, times_seen
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(src_ip, dst_ip, src_port, dst_port, protocol)
        DO UPDATE SET 
            packets = packets + excluded.packets,
            bytes = bytes + excluded.bytes,
            flow_end = excluded.flow_end,
            last_seen = excluded.last_seen,
            times_seen = times_seen + 1
                ''', row)
                
            newflows_conn.commit()
            log_info(logger, f"[INFO] Copied {len(rows)} flows from {source_db}")
            
        except sqlite3.Error as e:
            log_info(logger, f"[ERROR] Database error processing {source_db}: {e}")
        finally:
            if 'source_conn' in locals():
                source_conn.close()
            if 'newflows_conn' in locals():
                newflows_conn.close()

def log_test_results(start_time, end_time, duration, total_rows, filtered_rows, detection_durations):
    """
    Log test execution results to a new JSON file for each test run.

    Args:
        start_time: Test start timestamp
        end_time: Test end timestamp
        duration: Test duration in seconds
        total_rows: Total number of rows processed
        filtered_rows: Number of rows after whitelist filtering
        detection_durations: Dictionary containing durations for detection functions
    """
    logger = logging.getLogger(__name__)
    try:
        # Get alert categories and counts
        alerts_conn = connect_to_db(CONST_ALERTS_DB)
        alerts_cursor = alerts_conn.cursor()
        alerts_cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM alerts 
            GROUP BY category 
            ORDER BY count DESC
        """)
        categories = {category: count for category, count in alerts_cursor.fetchall()}
        alerts_conn.close()

        # Prepare the test result data
        test_result = {
            "execution_date": datetime.now().strftime("%Y-%m-%d"),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": round(duration, 2),
            "total_rows": total_rows,
            "filtered_rows": filtered_rows,
            "database_counts": {
                "newflows": get_row_count(CONST_NEWFLOWS_DB, 'flows'),
                "allflows": get_row_count(CONST_ALLFLOWS_DB, 'allflows'),
                "alerts": get_row_count(CONST_ALERTS_DB, 'alerts'),
                "whitelist": get_row_count(CONST_WHITELIST_DB, 'whitelist'),
                "localhosts": get_row_count(CONST_LOCALHOSTS_DB, 'localhosts'),
                "configuration": get_row_count(CONST_CONFIG_DB, 'configuration'),
                "geolocation": get_row_count(CONST_GEOLOCATION_DB, 'geolocation')
            },
            "alert_categories": categories,
            "detection_durations": detection_durations
        }

        # Ensure the test_results directory exists
        test_results_dir = Path(__file__).parent / "test_results"
        test_results_dir.mkdir(exist_ok=True)

        # Create a new file for this test run
        filename = f"{start_time.strftime('%Y-%m-%d_%H-%M-%S')}.json"
        results_file = test_results_dir / filename

        # Write the test result to the file in a pretty JSON format
        with open(results_file, 'w') as f:
            json.dump(test_result, f, indent=4)

        log_info(logger, f"[INFO] Test results written to {results_file}")

    except Exception as e:
        log_error(logger, f"[ERROR] Failed to write test results: {e}")

def main():
    """Main function to copy flows from multiple databases"""
    start_time = datetime.now()
    logger = logging.getLogger(__name__)

    delete_database(CONST_ALLFLOWS_DB)
    delete_database(CONST_ALERTS_DB)
    delete_database(CONST_WHITELIST_DB)
    delete_database(CONST_LOCALHOSTS_DB)
    delete_database(CONST_NEWFLOWS_DB)
    delete_database(CONST_CONFIG_DB)
    delete_database(CONST_GEOLOCATION_DB)

    create_database(CONST_ALLFLOWS_DB, CONST_CREATE_ALLFLOWS_SQL)
    create_database(CONST_ALERTS_DB, CONST_CREATE_ALERTS_SQL)
    create_database(CONST_WHITELIST_DB, CONST_CREATE_WHITELIST_SQL)
    create_database(CONST_CONFIG_DB, CONST_CREATE_CONFIG_SQL)
    create_database(CONST_LOCALHOSTS_DB, CONST_CREATE_LOCALHOSTS_SQL)
    create_database(CONST_NEWFLOWS_DB, CONST_CREATE_NEWFLOWS_SQL)
    create_database(CONST_GEOLOCATION_DB, CONST_CREATE_GEOLOCATION_SQL)

    init_configurations()

    config_dict = get_config_settings()
    
    copy_flows_to_newflows()

    conn = connect_to_db(CONST_NEWFLOWS_DB)

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flows")
    rows = cursor.fetchall()

    log_info(logger, f"[INFO] Fetched {len(rows)} rows from {CONST_NEWFLOWS_DB}")

    update_allflows(rows, config_dict)

    import_whitelists(config_dict)

    whitelist_entries = get_whitelist()
    log_info(logger, f"[INFO] Fetched {len(whitelist_entries)} whitelist entries from the database.")
    filtered_rows = remove_whitelist(rows, whitelist_entries)

    # Dictionary to store durations for each detection function
    detection_durations = {}

    # Run detection functions and calculate durations
    start = datetime.now()
    update_local_hosts(filtered_rows, config_dict)
    detection_durations['update_local_hosts'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    #detect_new_outbound_connections(filtered_rows, config_dict)
    detection_durations['detect_new_outbound_connections'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    #router_flows_detection(filtered_rows, config_dict)
    detection_durations['router_flows_detection'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    #foreign_flows_detection(filtered_rows, config_dict)
    detection_durations['foreign_flows_detection'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    #local_flows_detection(filtered_rows, config_dict)
    detection_durations['local_flows_detection'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    #detect_dead_connections(config_dict)
    detection_durations['detect_dead_connections'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    #detect_unauthorized_dns(filtered_rows, config_dict)
    detection_durations['detect_unauthorized_dns'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    #detect_unauthorized_ntp(filtered_rows, config_dict)
    detection_durations['detect_unauthorized_ntp'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    #detect_incorrect_ntp_stratum(filtered_rows, config_dict)
    detection_durations['detect_incorrect_ntp_stratum'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    #detect_incorrect_authoritative_dns(filtered_rows, config_dict)
    detection_durations['detect_incorrect_authoritative_dns'] = (datetime.now() - start).total_seconds()

    create_geolocation_db()
    geolocation_data = load_geolocation_data()

    log_info(logger, "[INFO] Preparing to detect geolocation flows...")
    start = datetime.now()
    #detect_geolocation_flows(filtered_rows, config_dict, geolocation_data)
    detection_durations['detect_geolocation_flows'] = (datetime.now() - start).total_seconds()

    localhosts = get_localhosts()

    start = datetime.now()
    lookup_return = dns_lookup(localhosts, config_dict['ApprovedLocalDnsServersList'].split(','), config_dict)
    log_info(logger,f"[INFO] DNS Results: {json.dumps(lookup_return)}")
    detection_durations['discovery_dns'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    dhcp_return = get_pihole_dhcp_clients(localhosts, config_dict)
    log_info(logger,f"[INFO] Pihole Results: {json.dumps(dhcp_return)}")
    detection_durations['discovery_pihole'] = (datetime.now() - start).total_seconds()


    log_info(logger, "[INFO] Processing finished.")
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    log_info(logger, f"[INFO] Total execution time: {duration:.2f} seconds")



    log_test_results(start_time, end_time, duration, len(rows), len(filtered_rows), detection_durations)

if __name__ == "__main__":
    main()