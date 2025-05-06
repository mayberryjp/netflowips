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

sys.path.insert(0, "/database")

from utils import log_info, log_warn, log_error, calculate_broadcast
from integrations.maxmind import load_geolocation_data, create_geolocation_db
from integrations.dns import dns_lookup  # Import the dns_lookup function from dns.py
from integrations.piholedhcp import get_pihole_dhcp_leases, get_pihole_network_devices
from integrations.nmap_fingerprint import os_fingerprint
from integrations.reputation import import_reputation_list, load_reputation_data
from integrations.tor import update_tor_nodes
from integrations.piholedns import get_pihole_ftl_logs
from database import get_localhosts, update_localhosts, import_custom_tags, get_custom_tags

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
    CONST_GEOLOCATION_DB,
    CONST_CREATE_REPUTATIONLIST_SQL,
    CONST_CREATE_CUSTOMTAGS_SQL,
    VERSION,
    CONST_DNSQUERIES_DB
)
from utils import log_info

from database import (
    get_config_settings,
    get_whitelist,
    connect_to_db,
    update_allflows,
    delete_database,
    create_database,
    init_configurations_from_sitepy,
    get_row_count,
    get_alerts_summary,
    import_whitelists,
    store_machine_unique_identifier
)

from tags import apply_tags

from detections import (
    update_local_hosts,
    detect_new_outbound_connections,
    router_flows_detection,
    foreign_flows_detection,
    local_flows_detection,
    detect_geolocation_flows,
    detect_dead_connections,
    detect_unauthorized_ntp,
    detect_unauthorized_dns,
    detect_incorrect_authoritative_dns,
    detect_incorrect_ntp_stratum,
    detect_reputation_flows,
    detect_vpn_traffic, detect_high_risk_ports,
    detect_many_destinations,
    detect_port_scanning,
    detect_tor_traffic,
    detect_high_bandwidth_flows,
    detect_custom_tag
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
            src_ip, dst_ip, src_port, dst_port, protocol, packets, bytes, flow_start, flow_end, last_seen, times_seen, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            log_error(logger, f"[ERROR] Database error processing {source_db}: {e}")
        finally:
            if 'source_conn' in locals():
                source_conn.close()
            if 'newflows_conn' in locals():
                newflows_conn.close()

def log_test_results(start_time, end_time, duration, total_rows, filtered_rows, detection_durations, tag_distribution):
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
            "version": VERSION,
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
                "geolocation": get_row_count(CONST_GEOLOCATION_DB, 'geolocation'),
                "dnsqueries": get_row_count(CONST_DNSQUERIES_DB, "pihole"),
                "reputationlist": get_row_count(CONST_GEOLOCATION_DB, "reputationlist"),
                "tornodes": get_row_count(CONST_GEOLOCATION_DB, "tornodes")
            },
            "tag_distribution": tag_distribution,
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
    create_database(CONST_GEOLOCATION_DB, CONST_CREATE_REPUTATIONLIST_SQL)
    create_database(CONST_WHITELIST_DB, CONST_CREATE_CUSTOMTAGS_SQL)

    init_configurations_from_sitepy()

    config_dict = get_config_settings()
    store_machine_unique_identifier()
    copy_flows_to_newflows()

    conn = connect_to_db(CONST_NEWFLOWS_DB)

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flows")
    rows = cursor.fetchall()
    rows = [list(row) for row in rows]

    log_info(logger, f"[INFO] Fetched {len(rows)} rows from {CONST_NEWFLOWS_DB}")

    import_whitelists(config_dict)
    import_custom_tags(config_dict)

    whitelist_entries = get_whitelist()
    customtag_entries = get_custom_tags()


    LOCAL_NETWORKS = set(config_dict['LocalNetworks'].split(','))

    # Calculate broadcast addresses for all local networks
    broadcast_addresses = set()
    for network in LOCAL_NETWORKS:
        broadcast_ip = calculate_broadcast(network)
        if broadcast_ip:
            broadcast_addresses.add(broadcast_ip)

    # Convert rows to dictionaries for input into apply_tags
    column_names = [desc[0] for desc in cursor.description]  # Get column names from the cursor
    rows_as_dicts = [dict(zip(column_names, row)) for row in rows]

    # Add a 'tags' dictionary value to every row
    for row in rows_as_dicts:
        row['tags'] = ""  # Initialize an empty string for tags

    # Apply tags
    tagged_rows_as_dicts = [apply_tags(row, whitelist_entries, broadcast_addresses, customtag_entries) for row in rows_as_dicts]

    # Convert back to arrays for use in update_allflows
    tagged_rows = [[row[col] if col in row else None for col in column_names] for row in tagged_rows_as_dicts]

    update_allflows(tagged_rows, config_dict)

    filtered_rows = [row for row in tagged_rows if 'Whitelist' not in str(row[11])]
    log_info(logger, f"[INFO] Finished removing IgnoreList flows - processing flow count is {len(filtered_rows)}")

    filtered_rows = [row for row in filtered_rows if 'Broadcast' not in str(row[11])]
    log_info(logger, f"[INFO] Finished removing Broadcast flows - processing flow count is {len(filtered_rows)}")

    filtered_rows = [row for row in filtered_rows if 'Multicast' not in str(row[11])]
    log_info(logger, f"[INFO] Finished removing Multicast flows - processing flow count is {len(filtered_rows)}")


    # Dictionary to store durations for each detection function
    detection_durations = {}

    # Run detection functions and calculate durations
    start = datetime.now()
    update_local_hosts(filtered_rows, config_dict)
    detection_durations['update_local_hosts'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_new_outbound_connections(filtered_rows, config_dict)
    detection_durations['detect_new_outbound_connections'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    router_flows_detection(filtered_rows, config_dict)
    detection_durations['router_flows_detection'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    foreign_flows_detection(filtered_rows, config_dict)
    detection_durations['foreign_flows_detection'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    local_flows_detection(filtered_rows, config_dict)
    detection_durations['local_flows_detection'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_dead_connections(config_dict)
    detection_durations['detect_dead_connections'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_unauthorized_dns(filtered_rows, config_dict)
    detection_durations['detect_unauthorized_dns'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_unauthorized_ntp(filtered_rows, config_dict)
    detection_durations['detect_unauthorized_ntp'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_incorrect_ntp_stratum(filtered_rows, config_dict)
    detection_durations['detect_incorrect_ntp_stratum'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_incorrect_authoritative_dns(filtered_rows, config_dict)
    detection_durations['detect_incorrect_authoritative_dns'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_vpn_traffic(filtered_rows, config_dict)
    detection_durations['detect_vpn_traffic'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_many_destinations(filtered_rows, config_dict)
    detection_durations['detect_many_destinations'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_high_risk_ports(filtered_rows, config_dict)
    detection_durations['detect_high_risk_ports'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_port_scanning(filtered_rows, config_dict)
    detection_durations['detect_port_scanning'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_many_destinations(filtered_rows, config_dict)
    detection_durations['detect_many_destinations'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    update_tor_nodes(config_dict)
    detect_tor_traffic(filtered_rows, config_dict)
    detection_durations['detect_tor_traffic'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_high_bandwidth_flows(filtered_rows, config_dict)
    detection_durations['detect_high_bandwidth_flows'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    detect_custom_tag(filtered_rows, config_dict)
    detection_durations['detect_custom_tag'] = (datetime.now() - start).total_seconds()

    log_info(logger, "[INFO] Preparing to detect geolocation flows...")
    start = datetime.now()
    create_geolocation_db()
    geolocation_data = load_geolocation_data()
    detect_geolocation_flows(filtered_rows, config_dict, geolocation_data)
    detection_durations['detect_geolocation_flows'] = (datetime.now() - start).total_seconds()

    log_info(logger, "[INFO] Preparing to download pihole dns query logs...")
    start = datetime.now()
    get_pihole_ftl_logs(10000,config_dict)
    detection_durations['retrieve_pihole_dns_query_logs'] = (datetime.now() - start).total_seconds()

    log_info(logger, "[INFO] Preparing to detect reputation list flows...")
    start = datetime.now()
    import_reputation_list(config_dict)
    reputation_data = load_reputation_data(config_dict)
    detect_reputation_flows(filtered_rows, config_dict, reputation_data)
    detection_durations['detect_reputationlist_flows'] = (datetime.now() - start).total_seconds()

    combined_results = {}
    localhosts = get_localhosts()

    start = datetime.now()
    dns_results = dns_lookup(localhosts, config_dict['ApprovedLocalDnsServersList'].split(','), config_dict)
    log_info(logger,f"[INFO] DNS Results: {json.dumps(dns_results)}")
    for result in dns_results:
        ip = result["ip"]
        combined_results[ip] = {
            "dns_hostname": result.get("dns_hostname", None),
        }
    detection_durations['discovery_dns'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    dl_results = get_pihole_dhcp_leases(localhosts, config_dict)
    log_info(logger,f"[INFO] Pihole DHCP Lease Results: {json.dumps(dl_results)}")
    for result in dl_results:
        ip = result["ip"]
        if ip not in combined_results:
            combined_results[ip] = {}
        combined_results[ip].update({
            "lease_hostname": result.get("lease_hostname", combined_results[ip].get("lease_hostname")),
            "lease_hwaddr": result.get("lease_hwaddr", combined_results[ip].get("lease_hwaddress")),
            "lease_clientid": result.get("lease_clientid", combined_results[ip].get("lease_clientid")),
        })
    detection_durations['discovery_pihole_dhcp_leases'] = (datetime.now() - start).total_seconds()

    start = datetime.now()
    nd_results = get_pihole_network_devices(localhosts, config_dict)
    log_info(logger,f"[INFO] Pihole Network Device Results: {json.dumps(nd_results)}")
    for result in nd_results:
        ip = result["ip"]
        if ip not in combined_results:
            combined_results[ip] = {}
        combined_results[ip].update({
            "dhcp_hostname": result.get("dhcp_hostname", combined_results[ip].get("dhcp_hostname")),
            "mac_address": result.get("mac_address", combined_results[ip].get("mac_address")),
            "mac_vendor": result.get("mac_vendor", combined_results[ip].get("mac_vendor")),
        })
    detection_durations['discovery_pihole_network_devices'] = (datetime.now() - start).total_seconds()   

    start = datetime.now()

    # Limit the list of localhosts to the first 3 entries
    sub_localhosts = list(localhosts)[:1]   # Slice the list to include only the first 3 hosts
    nmap_results = os_fingerprint(sub_localhosts, config_dict)

    log_info(logger, f"[INFO] Nmap Results: {json.dumps(nmap_results)}")

    for result in nmap_results:
        ip = result["ip"]
        if ip not in combined_results:
            combined_results[ip] = {}
        combined_results[ip].update({
            "os_fingerprint": result.get("os_fingerprint", combined_results[ip].get("os_fingerprint")),
        })
    detection_durations['discovery_nmap_os_fingerprint'] = (datetime.now() - start).total_seconds()

    # Query to count rows grouped by tags
    try:
        conn = connect_to_db(CONST_ALLFLOWS_DB)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) as count, tags 
            FROM allflows 
            GROUP BY tags;
        """)

        tag_counts = cursor.fetchall()
        conn.close()

        # Prepare the tags_distribution dictionary
        tags_distribution = {tag: count for count, tag in tag_counts}

        log_info(logger, f"[INFO] Tags distribution: {tags_distribution}")

    except sqlite3.Error as e:
        log_error(logger, f"[ERROR] Failed to fetch tag counts from allflows: {e}")
        tags_distribution = {}


    for ip, data in combined_results.items():
        update_localhosts(
            ip_address=ip,
            mac_address=data.get("mac_address"),
            mac_vendor=data.get("mac_vendor"),
            dhcp_hostname=data.get("dhcp_hostname"),
            dns_hostname=data.get("dns_hostname"),
            os_fingerprint=data.get("os_fingerprint"),
            lease_hostname=data.get("lease_hostname"),
            lease_hwaddr=data.get('lease_hwaddr'),
            lease_clientid=data.get('lease_clientid')
        )

    log_info(logger, "[INFO] Processing finished.")
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    log_info(logger, f"[INFO] Total execution time: {duration:.2f} seconds")

    log_test_results(start_time, end_time, duration, len(rows), len(filtered_rows), detection_durations, tags_distribution)

if __name__ == "__main__":
    main()