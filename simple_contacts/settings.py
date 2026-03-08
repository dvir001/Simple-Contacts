"""Settings management utilities for SimpleContacts."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from .config import SETTINGS_FILE

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "directoryJsonEnabled": False,
    "directoryJsonFilename": "microsip",
    "directoryXmlEnabled": False,
    "directoryXmlFilename": "yealink",
    "directoryNumberSwaps": [],
    "customDirectoryContacts": "",
    "autoUpdateEnabled": True,
    "updateTime": "20:00",
}


def load_settings() -> Dict[str, Any]:
    """Load settings from disk, merging with defaults."""
    settings = DEFAULT_SETTINGS.copy()
    if SETTINGS_FILE.exists():
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as fh:
                stored = json.load(fh)
                settings.update(stored)
        except Exception as exc:
            logger.error("Error loading settings from %s: %s", SETTINGS_FILE, exc)
    return settings


def save_settings(settings: Dict[str, Any]) -> bool:
    """Persist settings to disk."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged = DEFAULT_SETTINGS.copy()
    merged.update(settings)
    try:
        with SETTINGS_FILE.open("w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
        logger.info("Settings saved to %s", SETTINGS_FILE)
        return True
    except Exception as exc:
        logger.error("Error saving settings to %s: %s", SETTINGS_FILE, exc)
        return False
