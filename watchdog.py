#!/usr/bin/env python3
import psutil
import time
from datetime import datetime
from utils import log_error, log_info
import logging

# List of required Python script names
required_scripts = ["processor.py", "detections.py", "api.py", "collector.py"]

def is_script_running(script_name):
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and isinstance(cmdline, list):
                cmdline_str = " ".join(cmdline)
                if script_name in cmdline_str:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False

def check_scripts():
    logger = logging.getLogger(__name__)
    missing = [script for script in required_scripts if not is_script_running(script)]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if missing:
        log_error(logger,f"[ERROR] Missing python processes: {', '.join(missing)}. Please restart container and check configuration, errors. ")
    else:
        log_info(logger,"[INFO] All required python processes are running")

if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    log_info(logger,"[INFO] Starting health monitor... (checks every 60 seconds)")
    while True:
        check_scripts()
        time.sleep(60)
