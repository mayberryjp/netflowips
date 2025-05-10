# 1. dump my localhosts
# 2. send my localhosts to one of the two APIs for /classification
# 3. get the classification results 
# 4. add to a new object with classification results for test harness logging

import logging
import os
import sys
import json
from pathlib import Path
import requests

current_dir = Path(__file__).resolve().parent
parent_dir = str(current_dir.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
src_dir = f"{parent_dir}/src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
    
from src.database import get_localhosts
from src.client import export_client_definition
from src.utils import dump_json, log_error, log_info

# Configure logging
logger = logging.getLogger(__name__)

# Folder to save client definitions
OUTPUT_FOLDER = "tests/client_definitions"

def save_client_data(ip_address, data):
    """
    Save client data to a JSON file.

    Args:
        ip_address (str): The IP address used as the filename.
        data (dict): The client data to save.
    """
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    file_path = os.path.join(OUTPUT_FOLDER, f"{ip_address}.json")
    try:
        with open(file_path, "w") as file:
            json.dump(data, file, indent=4)
        logging.info(f"Saved client data for {ip_address} to {file_path}")
    except IOError as e:
        logging.error(f"Failed to save client data for {ip_address}: {e}")




def classify_client(machine_identifier, client_data):
    """
    Send client data to the classification API and get classification results.
    
    Args:
        machine_identifier (str): Unique identifier for the machine
        client_data (dict): Client data JSON to be classified
        
    Returns:
        dict: Classification response or None if request failed
    """
    api_url = f"http://api.homelabids.com:8044/api/classify/{machine_identifier}"
    
    try:
        log_info(logger, f"[INFO] Sending client data to classification API for machine {machine_identifier}")
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Make the API request
        response = requests.post(
            api_url,
            json=client_data,
            headers=headers,
            timeout=30  # Timeout after 30 seconds
        )
        
        # Check for successful response
        response.raise_for_status()
        
        # Parse the JSON response
        classification_result = response.json()
        log_info(logger, f"[INFO] Successfully received classification for machine {machine_identifier}")
        
        return classification_result
        
    except requests.exceptions.HTTPError as e:
        log_error(logger, f"[ERROR] HTTP error when classifying machine {machine_identifier}: {e}")
        log_error(logger, f"[ERROR] Response content: {e.response.text if hasattr(e, 'response') else 'No response'}")
    except requests.exceptions.ConnectionError as e:
        log_error(logger, f"[ERROR] Connection error when classifying machine {machine_identifier}: {e}")
    except requests.exceptions.Timeout as e:
        log_error(logger, f"[ERROR] Timeout when classifying machine {machine_identifier}: {e}")
    except requests.exceptions.RequestException as e:
        log_error(logger, f"[ERROR] Request error when classifying machine {machine_identifier}: {e}")
    except json.JSONDecodeError as e:
        log_error(logger, f"[ERROR] Invalid JSON in classification response for machine {machine_identifier}: {e}")
    except Exception as e:
        log_error(logger, f"[ERROR] Unexpected error when classifying machine {machine_identifier}: {e}")
    
    return None

def get_master_classification(ip_address):
    """
    Retrieves the expected classification category for a given IP address
    from the master classification data.
    
    Args:
        ip_address (str): The IP address to lookup
        
    Returns:
        str: The expected category or None if not found
    """
    try:
        # Import the master classification data
        from local_descriptions_object import LOCAL_DESCRIPTIONS
        
        # Search for the IP address in the master data
        for entry in LOCAL_DESCRIPTIONS:
            if entry["ip_address"] == ip_address:
                return entry["category"]
        
        # If no match was found
        log_info(logger, f"[INFO] No master classification found for IP {ip_address}")
        return None
        
    except ImportError as e:
        log_error(logger, f"[ERROR] Failed to import master classification data: {e}")
        return None
    except Exception as e:
        log_error(logger, f"[ERROR] Error retrieving master classification: {e}")
        return None

def main():
    # Statistics tracking
    total_clients = 0
    classified_clients = 0
    master_data_matches = 0
    master_data_mismatches = 0
    classification_details = []

    # Get all localhost data
    localhosts = get_localhosts()
    
    print("\n===== STARTING CLASSIFICATION TEST =====")
    
    for eachip in localhosts:
        total_clients += 1
        client_data = export_client_definition(eachip)
        save_client_data(eachip, client_data)
        
        if client_data:
            print(f"Client data retrieved for {eachip}")
            result = classify_client("TESTPPE", client_data)
            
            if result:
                classified_clients += 1
                
                # Get API classification result
                api_category = result.get("best_match", "UNKNOWN")[0]
                
                # Get expected classification from master data
                expected_category = get_master_classification(eachip)
                
                if expected_category:
                    # Compare API result with expected result
                    if api_category == expected_category:
                        master_data_matches += 1
                        match_status = "MATCH ✓"
                    else:
                        master_data_mismatches += 1
                        match_status = "MISMATCH ✗"
                        
                    print(f"Client {eachip}: API: {api_category}, Expected: {expected_category} - {match_status}")
                    
                    # Store the comparison result for summary
                    classification_details.append({
                        "ip": eachip,
                        "api": api_category,
                        "expected": expected_category,
                        "match": api_category == expected_category
                    })
                else:
                    print(f"Client {eachip}: API: {api_category}, No expected classification available")
                    classification_details.append({
                        "ip": eachip,
                        "api": api_category,
                        "expected": "N/A",
                        "match": None
                    })
            else:
                print(f"Failed to classify client {eachip}")
        else:
            print(f"Failed to fetch client data for {eachip}")

    # Calculate statistics
    accuracy = 0
    if master_data_matches + master_data_mismatches > 0:
        accuracy = (master_data_matches / (master_data_matches + master_data_mismatches)) * 100
    
    # Print comprehensive summary
    print("\n" + "="*50)
    print("         CLASSIFICATION TEST RESULTS         ")
    print("="*50)
    print(f"Total clients processed:     {total_clients}")
    print(f"Successfully classified:     {classified_clients}")
    print(f"Clients with master data:    {master_data_matches + master_data_mismatches}")
    print(f"Correct classifications:     {master_data_matches}")
    print(f"Incorrect classifications:   {master_data_mismatches}")
    print(f"Classification accuracy:     {accuracy:.2f}%")
    print("-"*50)
    
    # Print a table of results if there are any
    if classification_details:
        print("\nDETAILED CLASSIFICATION RESULTS:")
        print("-"*75)
        print(f"{'IP ADDRESS':<20} {'API RESULT':<20} {'EXPECTED':<20} {'MATCH':<10}")
        print("-"*75)
        
        for detail in classification_details:
            match_symbol = "✓" if detail["match"] == True else "✗" if detail["match"] == False else "-"
            print(f"{detail['ip']:<20} {detail['api']:<20} {detail['expected']:<20} {match_symbol:<10}")
        
        print("-"*75)
    
    print("\nClassification test completed.")

if __name__ == "__main__":
    main()