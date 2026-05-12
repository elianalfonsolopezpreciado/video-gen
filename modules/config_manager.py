"""
modules/config_manager.py - Carga y gestion de config.json.
API key se carga desde .secrets (nunca en texto plano en config.json).
"""

import json
import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_BASE, "config.json")

_config: dict = {}


def load_config() -> dict:
    global _config
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = json.load(f)
    else:
        _config = {}

    from modules.secrets_manager import load_api_key
    key = load_api_key()
    if key:
        _config["api_key"] = key

    return _config


def save_config(cfg: dict):
    global _config
    to_save = {k: v for k, v in cfg.items() if k != "api_key"}
    _config = cfg
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)


def get_config() -> dict:
    if not _config:
        load_config()
    return _config
