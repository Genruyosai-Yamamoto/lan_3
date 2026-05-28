from flask import request
from datetime import datetime

LOG_FILE = "logs/activity.log"

def log_activity(action, filename=""):
    ip = request.remote_addr
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(LOG_FILE, "a") as log:
        log.write(f"[{timestamp}] {ip} | {action} | {filename}\n")

           