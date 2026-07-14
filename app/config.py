# app/config.py
"""
Config file read/write. Isolated so any module can import it without
pulling in UI.
"""
import json
import os

from app.constants import CONFIG_PATH


def _load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}


def _save_config(data: dict) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save config to {CONFIG_PATH}: {e}")

