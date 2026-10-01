"""
database.py
Lightweight JSON-file backed persistence for users and recommendation history.

The project spec does not call for a full external database - it works with
in-memory dictionaries (users_db, user_recommendations). To keep data from
disappearing on every server restart (a safe, standard default), those same
dictionaries are loaded from / saved to simple JSON files in ./data.
"""
import json
import os
from threading import Lock

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

_write_lock = Lock()


def _load(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default
    return default


def _save(path: str, data) -> None:
    with _write_lock:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, path)


def load_users() -> dict:
    """username -> user dict (RegisterUser/UserInDB fields)"""
    return _load(USERS_FILE, {})


def save_users(users_db: dict) -> None:
    _save(USERS_FILE, users_db)


def load_history() -> dict:
    """username -> list[HistoryItem dict]"""
    return _load(HISTORY_FILE, {})


def save_history(history_db: dict) -> None:
    _save(HISTORY_FILE, history_db)
