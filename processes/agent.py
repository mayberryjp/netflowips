import os
import json
import logging
import requests
import re
from datetime import datetime
from difflib import get_close_matches
from openai import OpenAI  # Updated import
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
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
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
    }
]

class NLPProcessor:
    def __init__(self, config, api_endpoints):
        self.config = config
        self.api_endpoints = api_endpoints
        self.openai_client = None
        if config.OPENAI_API_KEY:
            # Initialize the OpenAI client with new API format
            self.openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
            self.model = config.OPENAI_MODEL
        
    def extract_intent_and_params(self, text):
        """Use NLP to determine the intent and extract parameters from text"""
        # First check if we can use OpenAI for more sophisticated parsing
        if self.openai_client:
            return self.extract_with_openai(text)
        else:
            return self.extract_with_basic_nlp(text)
    
    def extract_with_openai(self, text):
        """Use OpenAI to determine intent and extract parameters"""
        try:
            # Create a prompt that includes all available endpoints
            endpoints_desc = "\n".join([
                f"- {endpoint['name']}: {endpoint['description']} (Params: {', '.join(endpoint['params'])})"
                for endpoint in self.api_endpoints
            ])
            
            prompt = f"""
Given a user request, determine which API endpoint to call and extract any parameters.
Available endpoints:
{endpoints_desc}

User request: "{text}"

Format your response as JSON:
{{
  "endpoint": "endpoint_name",
  "params": {{
    "param1": "value1",
    ...
  }}
}}
"""
            # Updated API call format
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant that extracts API intents and parameters."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            
            # Updated response access
            response_text = response.choices[0].message.content.strip()
            # Extract JSON from the response
            match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                json_str = response_text
                
            # Clean the string and parse as JSON
            json_str = re.sub(r'```', '', json_str)
            result = json.loads(json_str)
            return result
            
        except Exception as e:
            logger.error(f"Error using OpenAI for intent extraction: {e}")
            # Fall back to basic NLP
            return self.extract_with_basic_nlp(text)
    
    def extract_with_basic_nlp(self, text):
        """Use basic NLP techniques to determine intent and extract parameters"""
        text = text.lower()
        
        # Score each endpoint based on keyword matches
        endpoint_scores = []
        for endpoint in self.api_endpoints:
            score = sum(1 for keyword in endpoint["keywords"] if keyword.lower() in text)
            endpoint_scores.append((endpoint, score))
        
        # Sort by score in descending order
        endpoint_scores.sort(key=lambda x: x[1], reverse=True)
        
        # If no good match, return empty
        if endpoint_scores[0][1] == 0:
            return {"endpoint": None, "params": {}}
        
        # Get the best matching endpoint
        best_endpoint = endpoint_scores[0][0]
        
        # Extract parameters
        params = {}
        for param in best_endpoint["params"]:
            # Look for IP addresses
            if param == "ip_address" or param == "identifier":
                ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text)
                if ip_match:
                    params[param] = ip_match.group(0)
                    continue
                    
            # Look for domains
            if param == "identifier":
                domain_match = re.search(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b', text)
                if domain_match:
                    params[param] = domain_match.group(0)
                    continue
            
            # Look for text following "parameter:"
            param_match = re.search(f'{param}[:\s]+([^\s,]+)', text)
            if param_match:
                params[param] = param_match.group(1)
        
        return {
            "endpoint": best_endpoint["name"],
            "params": params
        }
    
    def summarize_with_openai(self, json_data, endpoint_name):
        """Use OpenAI to summarize JSON response in natural language"""
        if not self.openai_client:
            return {"original_data": json_data, "summary": "OpenAI summarization not available"}
        
        try:
            # Construct prompt based on endpoint type
            if endpoint_name == "get_client_info":
                prompt = f"""
Summarize this client information in natural language. 
Focus on key details like:
- Client identity (IP, hostname, etc.)
- Traffic patterns and statistics
- DNS queries and their significance
- Notable or unusual behavior
- Device type and characteristics

JSON data:
{json.dumps(json_data, indent=2)}

Provide a concise, human-readable summary.
"""
            elif endpoint_name == "get_alerts_summary_by_ip":
                prompt = f"""
Summarize these security alerts for this IP address in plain language.
Highlight:
- Alert types and categories
- Frequency and severity
- Notable patterns or trends
- Recommended actions

JSON data:
{json.dumps(json_data, indent=2)}

Give a clear, concise summary that a network administrator would understand.
"""
            else:
                # Generic summary prompt
                prompt = f"""
Summarize this JSON data in natural language:
{json.dumps(json_data, indent=2)}

Provide a concise, human-readable summary.
"""
            
            # Updated API call format
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful network security assistant that explains technical data clearly."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800
            )
            
            # Updated response access
            summary = response.choices[0].message.content.strip()
            return {
                "original_data": json_data,
                "summary": summary
            }
            
        except Exception as e:
            logger.error(f"Error generating summary with OpenAI: {e}")
            return {
                "original_data": json_data,
                "summary": f"Error generating summary: {str(e)}"
            }
    
    def execute_api_call(self, endpoint_name, params):
        """Execute the appropriate API call and apply post-processing if needed"""
        # Find the endpoint definition
        endpoint_def = next((e for e in self.api_endpoints if e["name"] == endpoint_name), None)
        if not endpoint_def:
            return {"success": False, "message": f"Unknown endpoint: {endpoint_name}"}
        
        # List of endpoints to apply AI summarization
        summarize_endpoints = [
            "get_client_info", 
            "get_alerts_summary_by_ip",
            "get_traffic_stats",
            "get_localhost_by_ip"
        ]
        
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
                    
                    # Apply AI summarization for configured endpoints
                    if endpoint_name in summarize_endpoints and self.openai_client:
                        return self.summarize_with_openai(result, endpoint_name)
                    
                    return result
                except json.JSONDecodeError:
                    return {"success": True, "message": response.text}
            else:
                return {"success": False, "message": f"API call failed with status {response.status_code}: {response.text}"}
                
        except Exception as e:
            logger.error(f"Error executing API call: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}
    
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
    if not Config.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY environment variable not set! Using basic NLP only.")
    
    # Check if we should start in CLI mode
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        start_interactive_cli()
    else:
        # Start in server mode by default
        logger.info("Starting NLP Agent server...")
        print("Server running at http://0.0.0.0:5000/")
        print("Use --cli argument to start in CLI mode")
        run(app, host='0.0.0.0', port=5000)