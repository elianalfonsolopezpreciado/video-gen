"""
modules/secrets_manager.py - Almacenamiento seguro de API keys.
No guarda claves en texto plano. Usa base64 + permisos restrictivos en Linux.
"""

import os
import base64
import json
import stat
import platform

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_FILE = os.path.join(_BASE, ".secrets")


def save_api_key(key: str):
    data = {"api_key": base64.b64encode(key.encode("utf-8")).decode("ascii")}
    with open(SECRETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    if platform.system() != "Windows":
        os.chmod(SECRETS_FILE, stat.S_IRUSR | stat.S_IWUSR)


def load_api_key() -> str:
    if not os.path.exists(SECRETS_FILE):
        return ""
    try:
        with open(SECRETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        encoded = data.get("api_key", "")
        if not encoded:
            return ""
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def has_api_key() -> bool:
    return bool(load_api_key())


def delete_api_key():
    if os.path.exists(SECRETS_FILE):
        os.remove(SECRETS_FILE)
