import logging
import os
from datetime import datetime

from app.config.config import LOGS_DIR

os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, f"log_{datetime.now().strftime('%Y-%m-%d')}.log")

_root = logging.getLogger("medibot")
if not _root.handlers:
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    _root.addHandler(file_handler)
    _root.addHandler(console_handler)
    _root.setLevel(logging.INFO)
    _root.propagate = False


def get_logger(name):
    return _root.getChild(name)
