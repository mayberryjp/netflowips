import os
import json
import logging
import requests
import re
from datetime import datetime
from difflib import get_close_matches
from bottle import Bottle, request, response, run

# Set up logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Configuration 
class Config:
    API_BASE_URL = "http://localhost:8044/api"
    OPENAI_API_KEY = None  # Set to None to disable OpenAI
    OPENAI_MODEL = "gpt-3.5-turbo"

app = Bottle()

# Define available API endpoints and their descriptions
API_ENDPOINTS = [
    # Alert management endpoints
    {
        "name": "delete_all_alerts",
        "endpoint": "/alerts/delete/all",
        "method": "DELETE",
        "description": "Delete all alerts from the database",
        "keywords": ["delete", "remove", "clear", "alerts", "all"],
        "params": []
    },
    {
        "name": "get_recent_alerts",
        "endpoint": "/alerts/recent",
        "method": "GET",
        "description": "Get the most recent alerts",
        "keywords": ["get", "recent", "alerts", "latest"],
        "params": []
    },
    {
        "name": "get_alerts_by_category",
        "endpoint": "/alerts/category/{category_name}",
        "method": "GET",
        "description": "Get alerts filtered by a specific category",
        "keywords": ["category", "alerts", "filter", "type"],
        "params": ["category_name"]
    },
    {
        "name": "get_alerts_by_ip",
        "endpoint": "/alerts/{ip_address}",
        "method": "GET",
        "description": "Get all alerts for a specific IP address",
        "keywords": ["get", "alerts", "ip", "address", "filter"],
        "params": ["ip_address"]
    },
    {
        "name": "get_recent_alerts_by_ip",
        "endpoint": "/alerts/recent/{ip_address}",
        "method": "GET",
        "description": "Get recent alerts for a specific IP address",
        "keywords": ["recent", "alerts", "ip", "address"],
        "params": ["ip_address"]
    },
    {
        "name": "update_alert",
        "endpoint": "/alerts/{id}",
        "method": "PUT",
        "description": "Update an alert's acknowledged status",
        "keywords": ["update", "acknowledge", "alert"],
        "params": ["id", "acknowledged"]
    },
    {
        "name": "delete_alert",
        "endpoint": "/alerts/{id}",
        "method": "DELETE",
        "description": "Delete a specific alert by ID",
        "keywords": ["delete", "remove", "alert", "id"],
        "params": ["id"]
    },
    {
        "name": "get_alerts_summary",
        "endpoint": "/alerts/summary",
        "method": "GET",
        "description": "Get a summary of alerts by IP address",
        "keywords": ["summary", "alerts", "overview"],
        "params": []
    },
    {
        "name": "get_alerts_summary_by_ip",
        "endpoint": "/alerts/summary/{ip_address}",
        "method": "GET",
        "description": "Get a summary of alerts for a specific IP address",
        "keywords": ["summary", "alerts", "ip", "address"],
        "params": ["ip_address"]
    },
    
    # Client/Host information endpoints
    {
        "name": "get_client_info",
        "endpoint": "/client/{ip_address}",
        "method": "GET",
        "description": "Get detailed information about a client with the given IP address",
        "keywords": ["client", "info", "details", "host", "ip"],
        "params": ["ip_address"]
    },
    {
        "name": "get_traffic_stats",
        "endpoint": "/trafficstats/{ip_address}",
        "method": "GET",
        "description": "Get traffic statistics for a specific IP address",
        "keywords": ["traffic", "stats", "bandwidth", "ip", "data"],
        "params": ["ip_address"]
    },
    {
        "name": "get_localhosts",
        "endpoint": "/localhosts",
        "method": "GET",
        "description": "Get all devices on the local network",
        "keywords": ["local", "hosts", "devices", "list"],
        "params": []
    },
    {
        "name": "get_localhost_by_ip",
        "endpoint": "/localhosts/{ip_address}",
        "method": "GET",
        "description": "Get details for a specific local host",
        "keywords": ["local", "host", "device", "details", "ip"],
        "params": ["ip_address"]
    },
    {
        "name": "update_localhost",
        "endpoint": "/localhosts/{ip_address}",
        "method": "PUT",
        "description": "Update information for a local host",
        "keywords": ["update", "edit", "local", "host", "device"],
        "params": ["ip_address", "local_description", "icon", "acknowledged"]
    },
    {
        "name": "delete_localhost",
        "endpoint": "/localhosts/{ip_address}",
        "method": "DELETE",
        "description": "Delete a local host from the database",
        "keywords": ["delete", "remove", "local", "host", "device"],
        "params": ["ip_address"]
    },
    
    # Classification endpoint
    {
        "name": "classify_device",
        "endpoint": "/classify",
        "method": "POST",
        "description": "Classify a device based on DNS query or IP address",
        "keywords": ["classify", "identify", "device", "ip", "dns", "domain"],
        "params": ["identifier"]
    },
    
    # Configuration endpoints
    {
        "name": "get_configurations",
        "endpoint": "/configurations",
        "method": "GET",
        "description": "Get all system configurations",
        "keywords": ["configurations", "settings", "options", "get"],
        "params": []
    },
    {
        "name": "add_configuration",
        "endpoint": "/configurations",
        "method": "POST",
        "description": "Add a new configuration setting",
        "keywords": ["add", "create", "configuration", "setting"],
        "params": ["key", "value"]
    },
    {
        "name": "update_configuration",
        "endpoint": "/configurations/{key}",
        "method": "PUT",
        "description": "Update a configuration setting",
        "keywords": ["update", "edit", "change", "configuration", "setting"],
        "params": ["key", "value"]
    },
    {
        "name": "delete_configuration",
        "endpoint": "/configurations/{key}",
        "method": "DELETE",
        "description": "Delete a configuration setting",
        "keywords": ["delete", "remove", "configuration", "setting"],
        "params": ["key"]
    },
    
    # Whitelist endpoints
    {
        "name": "get_whitelist",
        "endpoint": "/whitelist",
        "method": "GET",
        "description": "Get all whitelist entries",
        "keywords": ["whitelist", "allowed", "trusted", "get"],
        "params": []
    },
    {
        "name": "add_whitelist_entry",
        "endpoint": "/whitelist",
        "method": "POST",
        "description": "Add a new whitelist entry",
        "keywords": ["add", "create", "whitelist", "allow", "trust"],
        "params": ["whitelist_id", "src_ip", "dst_ip", "dst_port", "protocol"]
    },
    {
        "name": "update_whitelist_entry",
        "endpoint": "/whitelist/{id}",
        "method": "PUT",
        "description": "Update a whitelist entry",
        "keywords": ["update", "edit", "whitelist", "entry"],
        "params": ["id", "src_ip", "dst_ip", "dst_port", "protocol"]
    },
    {
        "name": "delete_whitelist_entry",
        "endpoint": "/whitelist/{id}",
        "method": "DELETE",
        "description": "Delete a whitelist entry",
        "keywords": ["delete", "remove", "whitelist", "entry"],
        "params": ["id"]
    },
    
    # Status and statistics endpoints
    {
        "name": "get_database_counts",
        "endpoint": "/quickstats",
        "method": "GET",
        "description": "Get quick statistics about the database (alert counts, host counts, etc.)",
        "keywords": ["stats", "statistics", "counts", "dashboard", "overview"],
        "params": []
    },
    {
        "name": "get_homeassistant_stats",
        "endpoint": "/homeassistant",
        "method": "GET",
        "description": "Get statistics for Home Assistant integration",
        "keywords": ["homeassistant", "home", "assistant", "integration", "stats"],
        "params": []
    },
    
    # Action endpoints
    {
        "name": "get_actions",
        "endpoint": "/actions",
        "method": "GET",
        "description": "Get all available actions",
        "keywords": ["actions", "tasks", "get", "list"],
        "params": []
    },
    {
        "name": "insert_action",
        "endpoint": "/actions",
        "method": "POST",
        "description": "Create a new action",
        "keywords": ["create", "add", "new", "action", "task"],
        "params": ["action_data"]
    },
    {
        "name": "acknowledge_action",
        "endpoint": "/actions/{action_id}/acknowledge",
        "method": "PUT",
        "description": "Acknowledge an action",
        "keywords": ["acknowledge", "confirm", "action", "task"],
        "params": ["action_id"]
    },
# Add this to the API_ENDPOINTS list
    {
        "name": "investigate_ip",
        "endpoint": "/investigate/{ip_address}",
        "method": "GET",
        "description": "Investigate an IP address with DNS and geolocation lookups",
        "keywords": ["investigate", "lookup", "trace", "check", "ip", "country", "dns", "location", "geo"],
        "params": ["ip_address"]
    }
]

class NLPProcessor:
    def __init__(self, config, api_endpoints):
        self.config = config
        self.api_endpoints = api_endpoints
        self.openai_client = None  # Always set to None to disable OpenAI
        
    def extract_intent_and_params(self, text):
        """Use NLP to determine the intent and extract parameters from text"""
        # Always use basic NLP without trying OpenAI
        return self.extract_with_basic_nlp(text)
    
    def extract_with_basic_nlp(self, text):
        """Use advanced NLP techniques to determine intent and extract parameters without OpenAI"""
        text = text.lower()
        
        # 1. First approach: Weighted keyword matching
        endpoint_scores = []
        for endpoint in self.api_endpoints:
            # Base score from exact keyword matches
            keyword_score = sum(3 for keyword in endpoint["keywords"] if keyword.lower() in text)
            
            # Bonus for verb matching (get, delete, update)
            method_verb = endpoint["method"].lower()
            method_verbs = {
                "get": ["get", "show", "display", "list", "view", "find", "search", "what"],
                "delete": ["delete", "remove", "clear", "erase"],
                "put": ["update", "change", "modify", "edit", "set"],
                "post": ["add", "create", "insert", "new"]
            }
            
            if method_verb in method_verbs:
                verb_score = sum(2 for verb in method_verbs[method_verb] if verb in text)
                keyword_score += verb_score
            
            # Bonus for relevant entity presence
            if any(param in ["ip_address", "identifier"] for param in endpoint["params"]):
                if re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text):  # IP address
                    keyword_score += 3
                    
            if "domain" in endpoint["description"].lower() or "dns" in endpoint["description"].lower():
                if re.search(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b', text):
                    keyword_score += 3
            
            # 2. Context matching using word proximity
            context_score = 0
            for i, keyword1 in enumerate(endpoint["keywords"]):
                if keyword1 in text:
                    # Find other keywords nearby (within 5 words)
                    keyword_pos = text.find(keyword1)
                    nearby_text = text[max(0, keyword_pos-30):min(len(text), keyword_pos+30)]
                    for keyword2 in endpoint["keywords"][i+1:]:
                        if keyword2 in nearby_text:
                            context_score += 1
            
            total_score = keyword_score + context_score
            endpoint_scores.append((endpoint, total_score))
        
        # Sort by score in descending order
        endpoint_scores.sort(key=lambda x: x[1], reverse=True)
        
        # If top two scores are close, use more heuristics to decide
        if len(endpoint_scores) > 1 and endpoint_scores[0][1] > 0:
            if endpoint_scores[0][1] - endpoint_scores[1][1] < 2:
                # Check parameter presence for tiebreaking
                top_endpoints = [endpoint_scores[0][0], endpoint_scores[1][0]]
                for endpoint in top_endpoints:
                    for param in endpoint["params"]:
                        param_patterns = {
                            "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
                            "identifier": r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b',
                            "id": r'\b(?:id|alert|entry)[\s:]?([a-zA-Z0-9_-]+)\b',
                            "category_name": r'\bcategory[\s:]?([a-zA-Z0-9_-]+)\b'
                        }
                        
                        if param in param_patterns and re.search(param_patterns[param], text):
                            if endpoint == endpoint_scores[1][0]:
                                # Swap positions if second endpoint's param is found
                                endpoint_scores[0], endpoint_scores[1] = endpoint_scores[1], endpoint_scores[0]
        
        # If no good match, return empty
        if not endpoint_scores or endpoint_scores[0][1] == 0:
            return {"endpoint": None, "params": {}}
        
        # Get the best matching endpoint
        best_endpoint = endpoint_scores[0][0]
        logger.info(f"Selected intent: {best_endpoint['name']} with score: {endpoint_scores[0][1]}")
        
        # Extract parameters (enhanced)
        params = {}
        for param in best_endpoint["params"]:
            # Look for IP addresses
            if param == "ip_address" or param == "identifier":
                ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text)
                if ip_match:
                    params[param] = ip_match.group(0)
                    continue
                    
            # Look for domains
            if param == "identifier" or param == "domain":
                domain_match = re.search(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b', text)
                if domain_match:
                    params[param] = domain_match.group(0)
                    continue
            
            # Look for action IDs
            if param == "action_id":
                action_match = re.search(r'\b(?:action|task)[\s:]?([a-zA-Z0-9_-]+)\b', text)
                if action_match:
                    params[param] = action_match.group(1)
                    continue

            # Look for alert IDs
            if param == "id":
                id_match = re.search(r'\b(?:alert|id)[\s:]?([a-zA-Z0-9_-]+)\b', text)
                if id_match:
                    params[param] = id_match.group(1)
                    continue
                    
            # Look for categories
            if param == "category_name":
                cat_match = re.search(r'\b(?:category|type)[\s:]?([a-zA-Z0-9_-]+)\b', text)
                if cat_match:
                    params[param] = cat_match.group(1)
                    continue
            
            # General parameter extraction (looking for patterns like "param: value" or "param=value")
            param_match = re.search(f'{param}[:\s=]+([^\s,]+)', text)
            if param_match:
                params[param] = param_match.group(1)
        
        return {
            "endpoint": best_endpoint["name"],
            "params": params
        }
    
    def execute_api_call(self, endpoint_name, params):
        """Execute the appropriate API call and apply post-processing if needed"""
        # Find the endpoint definition
        endpoint_def = next((e for e in self.api_endpoints if e["name"] == endpoint_name), None)
        if not endpoint_def:
            return {"success": False, "message": f"Unknown endpoint: {endpoint_name}"}
        
        # Construct the URL, replacing parameter placeholders
        url = self.config.API_BASE_URL + endpoint_def["endpoint"]
        for param_name, param_value in params.items():
            if "{" + param_name + "}" in url:
                url = url.replace("{" + param_name + "}", param_value)
        
        # Make the API call
        method = endpoint_def["method"].upper()
        try:
            if method == "GET":
                response = requests.get(url)
            elif method == "POST":
                response = requests.post(url, json=params)
            elif method == "PUT":
                response = requests.put(url, json=params)
            elif method == "DELETE":
                response = requests.delete(url)
            else:
                return {"success": False, "message": f"Unsupported method: {method}"}
            
            # Handle response
            if response.status_code >= 200 and response.status_code < 300:
                try:
                    result = response.json()
                    
                    # Apply custom summarization for investigation endpoint
                    if endpoint_name == "investigate_ip":
                        return self.summarize_investigation_data(result)
                    
                    # Apply custom summarization for localhost endpoint  
                    if endpoint_name == "get_localhost_by_ip":
                        return self.summarize_localhost_data(result)
                    
                    return result
                except json.JSONDecodeError:
                    return {"success": True, "message": response.text}
            else:
                return {"success": False, "message": f"API call failed with status {response.status_code}: {response.text}"}
                
        except Exception as e:
            logger.error(f"Error executing API call: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}

    def summarize_localhost_data(self, data):
        """Create a human-readable summary of localhost data"""
        try:
            # Return both original data and a summary
            summary = ""
            
            # Basic device info
            ip = data.get("ip_address", "Unknown IP")
            hostname = data.get("dhcp_hostname", "unnamed device")
            if not hostname or hostname == "":
                hostname = "unnamed device"
            
            # Device identity
            summary += f"Device {hostname} ({ip}) "
            
            # Hardware info
            mac = data.get("mac_address", "")
            vendor = data.get("mac_vendor", "")
            if mac and vendor:
                summary += f"has MAC address {mac} (vendor: {vendor}). "
            elif mac:
                summary += f"has MAC address {mac}. "
            else:
                summary += ". "
            
            # Time information
            first_seen = data.get("first_seen", "")
            last_seen = data.get("last_seen", "")
            if first_seen and last_seen:
                summary += f"First seen on {first_seen} and last active on {last_seen}. "
            
            # Description
            description = data.get("local_description", "")
            if description:
                summary += f"User description: {description}. "
            
            # Network activity
            times_seen = data.get("times_seen", 0)
            if times_seen:
                summary += f"Device has connected {times_seen} times. "
            
            # Alert information
            alerts = data.get("alerts", 0)
            if alerts:
                summary += f"Has generated {alerts} security alerts. "
            
            # If any attributes are missing, add a note
            if not summary:
                summary = f"Limited information available for device at {ip}."
            
            return {
                "original_data": data,
                "summary": summary.strip()
            }
        except Exception as e:
            logger.error(f"Error summarizing localhost data: {e}")
            return {
                "original_data": data,
                "summary": f"Error creating summary: {str(e)}"
            }
    
    def summarize_investigation_data(self, data):
        """Create a human-readable summary of IP investigation data"""
        try:
            # Return both original data and a summary
            summary = ""
            
            # Basic IP info
            ip = data.get("ip_address", "Unknown IP")
            dns = data.get("dns")
            country = data.get("country")
            
            # Build summary
            summary += f"IP address {ip} "
            
            if dns:
                summary += f"resolves to hostname {dns}. "
            else:
                summary += "has no reverse DNS record. "
                
            if country:
                summary += f"This IP is located in {country}. "
            else:
                summary += "The country could not be determined. "
                
            # Additional context
            if country and country != "United States" and country != "Canada":
                summary += "Foreign IPs should be monitored carefully if connecting to sensitive systems."
            
            return {
                "original_data": data,
                "summary": summary.strip()
            }
        except Exception as e:
            logger.error(f"Error summarizing investigation data: {e}")
            return {
                "original_data": data,
                "summary": f"Error creating summary: {str(e)}"
            }
    
    def process_request(self, text):
        """Process a natural language request and execute the appropriate action"""
        logger.info(f"Processing request: {text}")
        
        # Extract intent and parameters
        intent_result = self.extract_intent_and_params(text)
        endpoint = intent_result.get("endpoint")
        params = intent_result.get("params", {})
        
        # If no intent found, return error
        if not endpoint:
            return {"success": False, "message": "Could not determine intent from your request"}
        
        logger.info(f"Detected intent: {endpoint} with params: {params}")
        
        # Execute the API call
        return self.execute_api_call(endpoint, params)

# Initialize the NLP processor
nlp_processor = NLPProcessor(Config, API_ENDPOINTS)

@app.post('/api/process-request')
def process_request():
    """Process a natural language request"""
    data = request.json
    if not data or 'text' not in data:
        response.status = 400
        return {"success": False, "message": "Missing text parameter"}
    
    text = data['text']
    result = nlp_processor.process_request(text)
    return result

def start_interactive_cli():
    """Start an interactive command-line interface"""
    logger.info("Starting interactive CLI mode...")
    print("\n=== NetFlowIPS AI Agent CLI ===")
    print("Type 'exit' or 'quit' to exit, 'help' for available commands.")
    
    # Start API server in a separate thread
    import threading
    server_thread = threading.Thread(
        target=lambda: run(app, host='0.0.0.0', port=5000, quiet=True),
        daemon=True
    )
    server_thread.start()
    
    while True:
        try:
            # Get user input
            user_input = input("\n> ")
            
            # Handle exit commands
            if user_input.lower() in ['exit', 'quit']:
                print("Exiting...")
                break
                
            # Handle help command
            elif user_input.lower() == 'help':
                print("\nAvailable endpoints:")
                for endpoint in API_ENDPOINTS:
                    params = ", ".join(endpoint["params"]) if endpoint["params"] else "none"
                    print(f"- {endpoint['name']}: {endpoint['description']} (Parameters: {params})")
                continue
                
            # Process the request
            if user_input.strip():
                print("\nProcessing request...")
                result = nlp_processor.process_request(user_input)
                
                # Format and display the result
                print("\n=== Result ===")
                if isinstance(result, dict):
                    if result.get("success") is False:
                        print(f"Error: {result.get('message', 'Unknown error')}")
                    else:
                        # Pretty print JSON result
                        print(json.dumps(result, indent=2))
                else:
                    print(result)
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {str(e)}")

if __name__ == "__main__":
    logger.info("Starting NLP Agent with built-in processing only (OpenAI disabled)")
    
    # Check if we should start in CLI mode
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        start_interactive_cli()
    else:
        # Start in server mode by default
        print("Server running at http://0.0.0.0:5000/")
        print("Use --cli argument to start in CLI mode")
        run(app, host='0.0.0.0', port=5000)