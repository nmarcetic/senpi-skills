"""moth_config.py — SDK boilerplate for MOTH producer.

Loads config from config/moth-config.json relative to this script's location.
Exposes load_config() used by moth-producer.py.
"""
import json
from pathlib import Path


_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "moth-config.json"


def load_config() -> dict:
    """Load and return operator config. Returns defaults if file missing."""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    return {}
