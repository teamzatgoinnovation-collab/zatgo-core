"""Setup for ZatGo Space (formerly the zatgo_space app) — run by
services/bundled_apps.py where ZG System Settings -> Enable ZatGo Space is on."""

from __future__ import annotations

import json

import frappe

DEFAULT_RAM_POOL_MB = 10240  # 10 GB
DEFAULT_DISK_POOL_MB = 102400  # 100 GB

MOCK_PLANS = [
	{
		"code": "basic",
		"title": "Basic",
		"mock_price": "$0 / mo (mock)",
		"sort_order": 1,
		"ram_limit_mb": 1024,
		"disk_limit_mb": 5120,
		"features": ["1 site", "ERPNext core", "1 GB RAM", "5 GB disk", "Community support"],
	},
	{
		"code": "pro",
		"title": "Pro",
		"mock_price": "$49 / mo (mock)",
		"sort_order": 2,
		"ram_limit_mb": 3072,
		"disk_limit_mb": 15360,
		"features": ["1 site", "ERPNext + HRMS", "3 GB RAM", "15 GB disk", "Priority email support"],
	},
	{
		"code": "enterprise",
		"title": "Enterprise",
		"mock_price": "$199 / mo (mock)",
		"sort_order": 3,
		"ram_limit_mb": 5120,
		"disk_limit_mb": 30720,
		"features": ["Multi-site ready", "Custom apps", "5 GB RAM", "30 GB disk", "Dedicated onboarding"],
	},
]


def bootstrap():
	seed_settings()
	seed_plans()


def seed_settings():
	if not frappe.db.exists("DocType", "Space Settings"):
		return
	doc = frappe.get_single("Space Settings")
	changed = False
	if not doc.ram_pool_mb:
		doc.ram_pool_mb = DEFAULT_RAM_POOL_MB
		changed = True
	if not doc.disk_pool_mb:
		doc.disk_pool_mb = DEFAULT_DISK_POOL_MB
		changed = True
	if changed:
		doc.save(ignore_permissions=True)
		frappe.db.commit()


def seed_plans():
	if not frappe.db.exists("DocType", "Space Plan"):
		return
	for plan in MOCK_PLANS:
		if frappe.db.exists("Space Plan", plan["code"]):
			doc = frappe.get_doc("Space Plan", plan["code"])
			doc.title = plan["title"]
			doc.mock_price = plan["mock_price"]
			doc.sort_order = plan["sort_order"]
			doc.is_active = 1
			doc.ram_limit_mb = plan["ram_limit_mb"]
			doc.disk_limit_mb = plan["disk_limit_mb"]
			doc.features = json.dumps(plan["features"])
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(
				{
					"doctype": "Space Plan",
					"code": plan["code"],
					"title": plan["title"],
					"mock_price": plan["mock_price"],
					"sort_order": plan["sort_order"],
					"is_active": 1,
					"ram_limit_mb": plan["ram_limit_mb"],
					"disk_limit_mb": plan["disk_limit_mb"],
					"features": json.dumps(plan["features"]),
				}
			).insert(ignore_permissions=True)
	frappe.db.commit()
