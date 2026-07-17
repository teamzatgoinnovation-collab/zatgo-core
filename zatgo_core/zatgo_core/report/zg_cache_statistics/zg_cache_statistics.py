"""Script Report: ZG Cache Statistics."""

from __future__ import annotations

import frappe


def execute(filters=None):
    columns = [
        {"label": "Key", "fieldname": "cache_key", "fieldtype": "Data", "width": 280},
        {"label": "Present", "fieldname": "present", "fieldtype": "Check", "width": 100},
    ]
    from zatgo_core.cache.manager import cache_manager
    from zatgo_core.constants.settings import CACHE_KEYS

    keys = [
        CACHE_KEYS["SYSTEM"],
        CACHE_KEYS["FEATURE_FLAGS"],
        CACHE_KEYS["APP_REGISTRY"],
        CACHE_KEYS["INTEGRATIONS"],
        CACHE_KEYS["PRINTERS"],
    ]
    data = []
    for key in keys:
        present = 1 if cache_manager.get(key) is not None else 0
        data.append({"cache_key": key, "present": present})
    return columns, data

