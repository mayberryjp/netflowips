import sqlite3
import json
import requests
from const import CONST_TELEGRAM_BOT_TOKEN, CONST_TELEGRAM_CHAT_ID, IS_CONTAINER
from utils import log_info  # Assuming log_info is defined in utils
import os

if (IS_CONTAINER):
    TELEGRAM_CHAT_ID = os.getenv("CONST_TELEGRAM_CHAT_ID", CONST_TELEGRAM_CHAT_ID)
    TELEGRAM_BOT_TOKEN = os.getenv("CONST_TELEGRAM_BOT_TOKEN", CONST_TELEGRAM_BOT_TOKEN)


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

