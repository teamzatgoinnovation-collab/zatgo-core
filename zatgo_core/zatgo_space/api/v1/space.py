"""Public / provisioner APIs for ZatGo Space."""

from __future__ import annotations

import json
import re
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from zatgo_core.zatgo_space.api.response import fail, ok
from zatgo_core.zatgo_space.install import DEFAULT_DISK_POOL_MB, DEFAULT_RAM_POOL_MB, MOCK_PLANS

DOMAIN_SUFFIX = "zatgo.online"
SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED = {
	"www",
	"erp",
	"space",
	"bench",
	"api",
	"mail",
	"ftp",
	"ns1",
	"ns2",
	"cdn",
	"admin",
	"status",
	"docs",
	"app",
	"apps",
	"portal",
}

DEFAULT_APPS = [
	{"package": "frappe", "title": "Frappe Framework", "required": True},
	{"package": "erpnext", "title": "ERPNext", "required": False},
	{"package": "hrms", "title": "HRMS", "required": False},
]

APP_TITLE_OVERRIDES = {
	"frappe": "Frappe Framework",
	"erpnext": "ERPNext",
	"hrms": "HRMS",
	"zatgo_core": "ZatGo Core",
	"zatgo_space": "ZatGo Space",
	"chat_ai": "Chat AI",
}

# Statuses that count toward soft pool allocation
POOL_STATUSES = ("Draft", "Provisioning", "Active")


def _parse_features(raw: str | None) -> list[str]:
	if not raw:
		return []
	try:
		data = json.loads(raw)
		if isinstance(data, list):
			return [str(x) for x in data]
	except Exception:
		pass
	return [line.strip() for line in raw.splitlines() if line.strip()]


def _app_title(package: str) -> str:
	if package in APP_TITLE_OVERRIDES:
		return APP_TITLE_OVERRIDES[package]
	try:
		mod = frappe.get_module(f"{package}.hooks")
		title = getattr(mod, "app_title", None)
		if title:
			return str(title)
	except Exception:
		pass
	return package.replace("_", " ").title()


def _list_bench_apps() -> list[dict[str, Any]]:
	"""Apps available on this Docker bench (from get-app / apps/), not a hardcode."""
	packages: list[str] = []
	try:
		packages = [p for p in frappe.get_all_apps(with_internal_apps=False) if p]
	except Exception:
		packages = []

	if not packages:
		# Fallback: scan apps directory on the bench
		import os

		try:
			from frappe.utils import get_bench_path

			apps_dir = os.path.join(get_bench_path(), "apps")
			if os.path.isdir(apps_dir):
				for name in sorted(os.listdir(apps_dir)):
					path = os.path.join(apps_dir, name)
					if os.path.isdir(path) and re.match(r"^[a-z][a-z0-9_]*$", name):
						packages.append(name)
		except Exception:
			pass

	if not packages:
		return list(DEFAULT_APPS)

	# Stable order: frappe → erpnext → rest A–Z
	priority = {"frappe": 0, "erpnext": 1}
	packages = sorted(set(packages), key=lambda p: (priority.get(p, 50), p))

	apps = []
	for pkg in packages:
		apps.append(
			{
				"package": pkg,
				"title": _app_title(pkg),
				"required": pkg == "frappe",
			}
		)
	return apps


def _assert_internal_token():
	expected = frappe.conf.get("space_internal_token") or ""
	provided = frappe.get_request_header("X-Space-Token") or frappe.form_dict.get("token") or ""
	if not expected or provided != expected:
		frappe.throw(_("Invalid space internal token"), frappe.PermissionError)


def _pool_limits() -> tuple[int, int]:
	"""Return (ram_pool_mb, disk_pool_mb) from Space Settings or site_config fallbacks."""
	ram = DEFAULT_RAM_POOL_MB
	disk = DEFAULT_DISK_POOL_MB
	if frappe.db.exists("DocType", "Space Settings"):
		try:
			settings = frappe.get_single("Space Settings")
			if settings.ram_pool_mb:
				ram = int(settings.ram_pool_mb)
			if settings.disk_pool_mb:
				disk = int(settings.disk_pool_mb)
		except Exception:
			pass
	# site_config overrides (optional ops knobs)
	if frappe.conf.get("space_ram_pool_mb"):
		ram = int(frappe.conf.get("space_ram_pool_mb"))
	if frappe.conf.get("space_disk_pool_mb"):
		disk = int(frappe.conf.get("space_disk_pool_mb"))
	return ram, disk


def _plan_quotas(plan_code: str) -> tuple[int, int]:
	"""Return (ram_limit_mb, disk_limit_mb) for a plan code."""
	if frappe.db.exists("Space Plan", plan_code):
		row = frappe.db.get_value(
			"Space Plan",
			plan_code,
			["ram_limit_mb", "disk_limit_mb"],
			as_dict=True,
		)
		if row:
			return int(row.ram_limit_mb or 0), int(row.disk_limit_mb or 0)
	for p in MOCK_PLANS:
		if p["code"] == plan_code:
			return int(p["ram_limit_mb"]), int(p["disk_limit_mb"])
	return 0, 0


def _allocated_pool(exclude_order: str | None = None) -> dict[str, Any]:
	"""Sum soft RAM/disk for Draft + Provisioning + Active orders."""
	ram_pool, disk_pool = _pool_limits()
	allocated_ram = 0
	allocated_disk = 0
	used_ram = 0
	used_disk = 0
	count = 0

	if not frappe.db.exists("DocType", "Space Order"):
		return {
			"ramPoolMb": ram_pool,
			"diskPoolMb": disk_pool,
			"allocatedRamMb": 0,
			"allocatedDiskMb": 0,
			"usedRamMb": 0,
			"usedDiskMb": 0,
			"freeRamMb": ram_pool,
			"freeDiskMb": disk_pool,
			"siteCount": 0,
		}

	filters: dict[str, Any] = {"status": ["in", list(POOL_STATUSES)]}
	orders = frappe.get_all(
		"Space Order",
		filters=filters,
		fields=["name", "plan", "ram_used_mb", "disk_used_mb", "status"],
	)
	for order in orders:
		if exclude_order and order.name == exclude_order:
			continue
		plan_ram, plan_disk = _plan_quotas(order.plan)
		allocated_ram += plan_ram
		allocated_disk += plan_disk
		used_ram += int(order.ram_used_mb or 0)
		used_disk += int(order.disk_used_mb or 0)
		count += 1

	return {
		"ramPoolMb": ram_pool,
		"diskPoolMb": disk_pool,
		"allocatedRamMb": allocated_ram,
		"allocatedDiskMb": allocated_disk,
		"usedRamMb": used_ram,
		"usedDiskMb": used_disk,
		"freeRamMb": max(0, ram_pool - allocated_ram),
		"freeDiskMb": max(0, disk_pool - allocated_disk),
		"siteCount": count,
	}


def _serialize_plan(row_or_dict) -> dict[str, Any]:
	if isinstance(row_or_dict, dict):
		code = row_or_dict.get("code")
		title = row_or_dict.get("title")
		mock_price = row_or_dict.get("mock_price")
		features = row_or_dict.get("features")
		ram = int(row_or_dict.get("ram_limit_mb") or 0)
		disk = int(row_or_dict.get("disk_limit_mb") or 0)
		if isinstance(features, list):
			feat_list = [str(x) for x in features]
		else:
			feat_list = _parse_features(features)
	else:
		code = row_or_dict.code
		title = row_or_dict.title
		mock_price = row_or_dict.mock_price
		feat_list = _parse_features(row_or_dict.features)
		ram = int(getattr(row_or_dict, "ram_limit_mb", 0) or 0)
		disk = int(getattr(row_or_dict, "disk_limit_mb", 0) or 0)

	return {
		"code": code,
		"title": title,
		"mock_price": mock_price,
		"features": feat_list,
		"ramLimitMb": ram,
		"diskLimitMb": disk,
	}


@frappe.whitelist(allow_guest=True)
def list_catalog():
	"""Plans + installable app catalog for the Space wizard."""
	plans = []
	if frappe.db.exists("DocType", "Space Plan"):
		rows = frappe.get_all(
			"Space Plan",
			filters={"is_active": 1},
			fields=["code", "title", "mock_price", "features", "sort_order", "ram_limit_mb", "disk_limit_mb"],
			order_by="sort_order asc",
		)
		for row in rows:
			plans.append(_serialize_plan(row))
	else:
		for p in MOCK_PLANS:
			plans.append(_serialize_plan(p))

	suffix = frappe.conf.get("space_domain_suffix") or DOMAIN_SUFFIX
	pool = _allocated_pool()
	return ok(
		{
			"domainSuffix": suffix,
			"apps": _list_bench_apps(),
			"plans": plans,
			"pool": {
				"ramPoolMb": pool["ramPoolMb"],
				"diskPoolMb": pool["diskPoolMb"],
				"allocatedRamMb": pool["allocatedRamMb"],
				"allocatedDiskMb": pool["allocatedDiskMb"],
				"freeRamMb": pool["freeRamMb"],
				"freeDiskMb": pool["freeDiskMb"],
				"siteCount": pool["siteCount"],
			},
		}
	)


@frappe.whitelist(allow_guest=True)
def list_sites_usage():
	"""Active/provisioning sites with soft quotas and last usage snapshot."""
	pool = _allocated_pool()
	sites = []

	if frappe.db.exists("DocType", "Space Order"):
		orders = frappe.get_all(
			"Space Order",
			filters={"status": ["in", ["Provisioning", "Active"]]},
			fields=[
				"name",
				"slug",
				"hostname",
				"status",
				"plan",
				"desk_url",
				"ram_used_mb",
				"disk_used_mb",
				"usage_updated_at",
			],
			order_by="creation asc",
		)
		for order in orders:
			ram_limit, disk_limit = _plan_quotas(order.plan)
			plan_title = order.plan
			if frappe.db.exists("Space Plan", order.plan):
				plan_title = frappe.db.get_value("Space Plan", order.plan, "title") or order.plan
			sites.append(
				{
					"name": order.name,
					"slug": order.slug,
					"hostname": order.hostname,
					"status": order.status,
					"plan": order.plan,
					"planTitle": plan_title,
					"deskUrl": order.desk_url,
					"ramLimitMb": ram_limit,
					"diskLimitMb": disk_limit,
					"ramUsedMb": int(order.ram_used_mb or 0),
					"diskUsedMb": int(order.disk_used_mb or 0),
					"usageUpdatedAt": str(order.usage_updated_at) if order.usage_updated_at else None,
				}
			)

	return ok({"pool": pool, "sites": sites})


@frappe.whitelist(allow_guest=True)
def create_order(
	slug: str,
	plan: str,
	apps: str | list | None = None,
	payment_method: str = "Mock",
):
	"""Create a Draft Space Order (no admin password stored)."""
	slug = (slug or "").strip().lower()
	if not SLUG_RE.match(slug):
		return fail("INVALID_SLUG", "Invalid subdomain slug")
	if slug in RESERVED:
		return fail("RESERVED_SLUG", f"Subdomain '{slug}' is reserved")

	suffix = frappe.conf.get("space_domain_suffix") or DOMAIN_SUFFIX
	hostname = f"{slug}.{suffix}"

	if frappe.db.exists("Space Order", {"hostname": hostname, "status": ["in", ["Draft", "Provisioning", "Active"]]}):
		return fail("HOSTNAME_TAKEN", f"Hostname already ordered: {hostname}")

	if not frappe.db.exists("Space Plan", plan):
		return fail("INVALID_PLAN", f"Unknown plan: {plan}")

	new_ram, new_disk = _plan_quotas(plan)
	pool = _allocated_pool()
	if pool["allocatedRamMb"] + new_ram > pool["ramPoolMb"]:
		return fail(
			"POOL_RAM_EXCEEDED",
			f"Not enough RAM in the server pool "
			f"({pool['allocatedRamMb']} + {new_ram} MB needed, {pool['ramPoolMb']} MB total).",
		)
	if pool["allocatedDiskMb"] + new_disk > pool["diskPoolMb"]:
		return fail(
			"POOL_DISK_EXCEEDED",
			f"Not enough disk in the server pool "
			f"({pool['allocatedDiskMb']} + {new_disk} MB needed, {pool['diskPoolMb']} MB total).",
		)

	app_list: list[Any] = []
	if isinstance(apps, str):
		try:
			app_list = json.loads(apps)
		except Exception:
			app_list = [a.strip() for a in apps.split(",") if a.strip()]
	elif isinstance(apps, list):
		app_list = apps

	packages = []
	for item in app_list:
		if isinstance(item, dict):
			pkg = item.get("package") or item.get("app_package")
			title = item.get("title") or pkg
		else:
			pkg = str(item)
			title = pkg
		if not pkg or not re.match(r"^[a-z][a-z0-9_]*$", pkg):
			continue
		packages.append({"app_package": pkg, "title": title})

	if not any(p["app_package"] == "frappe" for p in packages):
		packages.insert(0, {"app_package": "frappe", "title": "Frappe Framework"})

	doc = frappe.get_doc(
		{
			"doctype": "Space Order",
			"slug": slug,
			"hostname": hostname,
			"plan": plan,
			"payment_method": payment_method if payment_method in ("Mock", "Stripe", "PayPal") else "Mock",
			"status": "Draft",
			"desk_url": f"https://{hostname}",
			"apps": packages,
		}
	)
	# Guest may create draft orders for the public wizard.
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return ok(
		{
			"name": doc.name,
			"slug": doc.slug,
			"hostname": doc.hostname,
			"status": doc.status,
			"deskUrl": doc.desk_url,
			"plan": doc.plan,
			"ramLimitMb": new_ram,
			"diskLimitMb": new_disk,
			"apps": [{"package": r.app_package, "title": r.title} for r in doc.apps],
		}
	)


@frappe.whitelist(allow_guest=True)
def get_order(name: str | None = None, job_id: str | None = None):
	"""Fetch order status for the wizard."""
	filters = {}
	if name:
		filters["name"] = name
	elif job_id:
		filters["job_id"] = job_id
	else:
		return fail("MISSING_ID", "name or job_id required")

	if not frappe.db.exists("Space Order", filters):
		return fail("NOT_FOUND", "Space Order not found")

	doc = frappe.get_doc("Space Order", filters)
	logs = []
	if frappe.db.exists("DocType", "Space Job Log"):
		logs = frappe.get_all(
			"Space Job Log",
			filters={"order": doc.name},
			fields=["stage", "status", "message", "creation"],
			order_by="creation asc",
			limit_page_length=100,
		)

	ram_limit, disk_limit = _plan_quotas(doc.plan)
	return ok(
		{
			"name": doc.name,
			"slug": doc.slug,
			"hostname": doc.hostname,
			"status": doc.status,
			"deskUrl": doc.desk_url,
			"plan": doc.plan,
			"jobId": doc.job_id,
			"error": doc.error_message,
			"ramLimitMb": ram_limit,
			"diskLimitMb": disk_limit,
			"ramUsedMb": int(doc.ram_used_mb or 0),
			"diskUsedMb": int(doc.disk_used_mb or 0),
			"apps": [{"package": r.app_package, "title": r.title} for r in doc.apps],
			"logs": logs,
		}
	)


@frappe.whitelist()
def update_order_status(
	name: str,
	status: str,
	job_id: str | None = None,
	error_message: str | None = None,
	admin_password_set: int | None = None,
	stage: str | None = None,
	stage_status: str | None = None,
	message: str | None = None,
	log_text: str | None = None,
):
	"""Provisioner callback — requires X-Space-Token matching site_config space_internal_token."""
	_assert_internal_token()

	if status not in ("Draft", "Provisioning", "Active", "Failed"):
		return fail("INVALID_STATUS", status)

	doc = frappe.get_doc("Space Order", name)
	doc.status = status
	if job_id:
		doc.job_id = job_id
	if error_message is not None:
		doc.error_message = error_message
	if admin_password_set is not None:
		doc.admin_password_set = 1 if admin_password_set else 0
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)

	if stage:
		frappe.get_doc(
			{
				"doctype": "Space Job Log",
				"order": doc.name,
				"job_id": job_id or doc.job_id or "unknown",
				"stage": stage,
				"status": stage_status or "running",
				"message": message,
				"log_text": log_text,
			}
		).insert(ignore_permissions=True)

	frappe.db.commit()
	return ok({"name": doc.name, "status": doc.status})


@frappe.whitelist()
def update_order_usage(
	name: str,
	ram_used_mb: int | float | None = None,
	disk_used_mb: int | float | None = None,
):
	"""Provisioner/metrics callback — store soft usage snapshot on Space Order."""
	_assert_internal_token()

	if not frappe.db.exists("Space Order", name):
		return fail("NOT_FOUND", "Space Order not found")

	doc = frappe.get_doc("Space Order", name)
	if ram_used_mb is not None:
		doc.ram_used_mb = max(0, int(ram_used_mb))
	if disk_used_mb is not None:
		doc.disk_used_mb = max(0, int(disk_used_mb))
	doc.usage_updated_at = now_datetime()
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return ok(
		{
			"name": doc.name,
			"ramUsedMb": int(doc.ram_used_mb or 0),
			"diskUsedMb": int(doc.disk_used_mb or 0),
			"usageUpdatedAt": str(doc.usage_updated_at),
		}
	)
