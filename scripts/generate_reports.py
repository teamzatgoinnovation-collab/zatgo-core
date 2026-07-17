#!/usr/bin/env python3
"""Generate script reports for ZatGo Core."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "zatgo_core" / "zatgo_core" / "report"
MODULE = "ZatGo Core"

REPORTS = {
    "zg_installed_apps": {
        "name": "ZG Installed Apps",
        "ref_doctype": "ZG Application Registry",
        "columns": [
            ("app_name", "Data", 160, "App Name"),
            ("module_name", "Data", 160, "Module"),
            ("version", "Data", 100, "Version"),
            ("enabled", "Check", 80, "Enabled"),
            ("app_status", "Data", 120, "Status"),
            ("developer", "Data", 140, "Developer"),
            ("depends_on", "Data", 180, "Depends On"),
            ("last_update", "Datetime", 160, "Last Update"),
        ],
        "execute": '''\
def execute(filters=None):
    columns = [
        {"label": "App Name", "fieldname": "app_name", "fieldtype": "Data", "width": 160},
        {"label": "Module", "fieldname": "module_name", "fieldtype": "Data", "width": 160},
        {"label": "Version", "fieldname": "version", "fieldtype": "Data", "width": 100},
        {"label": "Enabled", "fieldname": "enabled", "fieldtype": "Check", "width": 80},
        {"label": "Status", "fieldname": "app_status", "fieldtype": "Data", "width": 120},
        {"label": "Developer", "fieldname": "developer", "fieldtype": "Data", "width": 140},
        {"label": "Depends On", "fieldname": "depends_on", "fieldtype": "Data", "width": 180},
        {"label": "Last Update", "fieldname": "last_update", "fieldtype": "Datetime", "width": 160},
    ]
    data = frappe.get_all(
        "ZG Application Registry",
        fields=[
            "app_name", "module_name", "version", "enabled",
            "app_status", "developer", "depends_on", "last_update",
        ],
        order_by="app_name asc",
        limit_page_length=500,
    )
    return columns, data
''',
    },
    "zg_feature_flags": {
        "name": "ZG Feature Flags",
        "ref_doctype": "ZG Feature Flag",
        "execute": '''\
def execute(filters=None):
    columns = [
        {"label": "Flag Key", "fieldname": "flag_key", "fieldtype": "Data", "width": 180},
        {"label": "Title", "fieldname": "title", "fieldtype": "Data", "width": 160},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": "App", "fieldname": "app_name", "fieldtype": "Data", "width": 120},
        {"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
        {"label": "Rollout %", "fieldname": "rollout_percent", "fieldtype": "Int", "width": 100},
    ]
    filters = filters or {}
    data = frappe.get_all(
        "ZG Feature Flag",
        filters=filters,
        fields=["flag_key", "title", "status", "app_name", "company", "rollout_percent"],
        order_by="flag_key asc",
        limit_page_length=1000,
    )
    return columns, data
''',
    },
    "zg_audit_history": {
        "name": "ZG Audit History",
        "ref_doctype": "ZG Audit Log",
        "execute": '''\
def execute(filters=None):
    columns = [
        {"label": "Date", "fieldname": "change_date", "fieldtype": "Date", "width": 110},
        {"label": "Time", "fieldname": "change_time", "fieldtype": "Time", "width": 100},
        {"label": "DocType", "fieldname": "doctype_name", "fieldtype": "Data", "width": 160},
        {"label": "Document", "fieldname": "document_name", "fieldtype": "Data", "width": 160},
        {"label": "Field", "fieldname": "fieldname", "fieldtype": "Data", "width": 120},
        {"label": "Old Value", "fieldname": "old_value", "fieldtype": "Data", "width": 160},
        {"label": "New Value", "fieldname": "new_value", "fieldtype": "Data", "width": 160},
        {"label": "Changed By", "fieldname": "changed_by", "fieldtype": "Link", "options": "User", "width": 140},
        {"label": "IP", "fieldname": "ip_address", "fieldtype": "Data", "width": 120},
        {"label": "App", "fieldname": "app_name", "fieldtype": "Data", "width": 100},
    ]
    filters = filters or {}
    data = frappe.get_all(
        "ZG Audit Log",
        filters=filters,
        fields=[
            "change_date", "change_time", "doctype_name", "document_name", "fieldname",
            "old_value", "new_value", "changed_by", "ip_address", "app_name",
        ],
        order_by="creation desc",
        limit_page_length=1000,
    )
    return columns, data
''',
    },
    "zg_login_activity": {
        "name": "ZG Login Activity",
        "ref_doctype": "Activity Log",
        "execute": '''\
def execute(filters=None):
    columns = [
        {"label": "User", "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 160},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": "IP Address", "fieldname": "ip_address", "fieldtype": "Data", "width": 140},
        {"label": "Operation", "fieldname": "operation", "fieldtype": "Data", "width": 120},
        {"label": "When", "fieldname": "creation", "fieldtype": "Datetime", "width": 160},
    ]
    if not frappe.db.exists("DocType", "Activity Log"):
        return columns, []
    data = frappe.get_all(
        "Activity Log",
        filters={"operation": ("in", ["Login", "Logout"])},
        fields=["user", "status", "ip_address", "operation", "creation"],
        order_by="creation desc",
        limit_page_length=500,
    )
    return columns, data
''',
    },
    "zg_printer_usage": {
        "name": "ZG Printer Usage",
        "ref_doctype": "ZG Printer Settings",
        "execute": '''\
def execute(filters=None):
    columns = [
        {"label": "Printer Role", "fieldname": "role", "fieldtype": "Data", "width": 160},
        {"label": "Device", "fieldname": "device", "fieldtype": "Data", "width": 220},
        {"label": "Configured", "fieldname": "configured", "fieldtype": "Check", "width": 100},
    ]
    if not frappe.db.exists("DocType", "ZG Printer Settings"):
        return columns, []
    doc = frappe.get_single("ZG Printer Settings")
    rows = [
        ("Receipt Printer", doc.receipt_printer),
        ("Kitchen Printer", doc.kitchen_printer),
        ("Barcode Printer", doc.barcode_printer),
        ("Label Printer", doc.label_printer),
        ("A4 Printer", doc.a4_printer),
    ]
    data = [
        {"role": role, "device": device or "", "configured": 1 if device else 0}
        for role, device in rows
    ]
    return columns, data
''',
    },
    "zg_api_usage": {
        "name": "ZG API Usage",
        "ref_doctype": "ZG Audit Log",
        "execute": '''\
def execute(filters=None):
    """Summarize recent API-oriented audit / error activity."""
    columns = [
        {"label": "Metric", "fieldname": "metric", "fieldtype": "Data", "width": 220},
        {"label": "Value", "fieldname": "value", "fieldtype": "Int", "width": 120},
    ]
    audit_count = frappe.db.count("ZG Audit Log") if frappe.db.exists("DocType", "ZG Audit Log") else 0
    error_count = frappe.db.count("Error Log") if frappe.db.exists("DocType", "Error Log") else 0
    data = [
        {"metric": "ZG Audit Log rows", "value": audit_count},
        {"metric": "Error Log rows", "value": error_count},
        {"metric": "Installed apps", "value": len(frappe.get_installed_apps())},
    ]
    return columns, data
''',
    },
    "zg_cache_statistics": {
        "name": "ZG Cache Statistics",
        "ref_doctype": "ZG System Settings",
        "execute": '''\
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
''',
    },
}


def write_report(slug: str, meta: dict) -> None:
    folder = ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "__init__.py").write_text("", encoding="utf-8")
    report_json = {
        "add_total_row": 0,
        "columns": [],
        "creation": "2026-07-16 00:00:00.000000",
        "disabled": 0,
        "docstatus": 0,
        "doctype": "Report",
        "is_standard": "Yes",
        "letter_head": "",
        "modified": "2026-07-16 00:00:00.000000",
        "modified_by": "Administrator",
        "module": MODULE,
        "name": meta["name"],
        "owner": "Administrator",
        "ref_doctype": meta["ref_doctype"],
        "report_name": meta["name"],
        "report_type": "Script Report",
        "roles": [
            {"role": "System Manager"},
            {"role": "ZG Application Admin"},
            {"role": "ZG Company Admin"},
            {"role": "ZG Read Only"},
        ],
    }
    (folder / f"{slug}.json").write_text(json.dumps(report_json, indent=2) + "\n", encoding="utf-8")
    py = f'''"""Script Report: {meta["name"]}."""

from __future__ import annotations

import frappe


{meta["execute"]}
'''
    (folder / f"{slug}.py").write_text(py, encoding="utf-8")
    (folder / f"{slug}.js").write_text(
        f"""frappe.query_reports[\"{meta['name']}\"] = {{\n\tfilters: []\n}};\n""",
        encoding="utf-8",
    )
    print(f"Wrote report {slug}")


def main() -> None:
    for slug, meta in REPORTS.items():
        write_report(slug, meta)


if __name__ == "__main__":
    main()
