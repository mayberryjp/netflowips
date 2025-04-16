import sqlite3
import json
import requests
from const import CONST_TELEGRAM_BOT_TOKEN, CONST_TELEGRAM_CHAT_ID, IS_CONTAINER, VERSION, CONST_SITE
from utils import log_info  # Assuming log_info is defined in utils
import os

if (IS_CONTAINER):
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", CONST_TELEGRAM_CHAT_ID)
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", CONST_TELEGRAM_BOT_TOKEN)
    SITE = os.getenv("SITE", CONST_SITE)


def send_telegram_message(message):
    """
    Sends a message to a Telegram group chat.

    Args:
        message (str): The message to send.
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            log_info(None, "[INFO] Telegram message sent successfully.")
        else:
            log_info(None, f"[ERROR] Failed to send Telegram message. Status code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        log_info(None, f"[ERROR] Exception occurred while sending Telegram message: {e}")


def send_test_telegram_message():
    """
    Sends a test message to a Telegram group chat at startup if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set.
    """
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            message = f"HomelabIDS is online - running version {VERSION} at {SITE}."
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                log_info(None, "[INFO] Test Telegram message sent successfully.")
            else:
                log_info(None, f"[ERROR] Failed to send test Telegram message. Status code: {response.status_code}, Response: {response.text}")
        except Exception as e:
            log_info(None, f"[ERROR] Exception occurred while sending test Telegram message: {e}")
    else:
        log_info(None, "[WARN] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set. Skipping test Telegram message.")

