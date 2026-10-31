"""What each settings DocType does today, for the Settings Map: scope, status and who reads it.

Built from docs/settings_scope.md. A DocType has a default `scope` / `status` / `enforced_by`; `fields` overrides one field.
Status: "enforced" (server code reads it and acts), "read" (served to a client that uses it), "info" (stored, no code acts on
it), "unwired" (served or stored, and neither a client nor the server uses it yet -- a gap, not a feature).
`enforced_by` is a path relative to the package (optionally `path::symbol`); tests/unit/test_settings_map.py checks that every
field and path named here exists, so an entry cannot rot silently. A DocType without an entry is shown as "info".
"""

from __future__ import annotations

from typing import Any

STATUSES = ("enforced", "read", "info", "unwired")

CHAT = "chat_ai/core/quota.py"

DOCTYPES: dict[str, dict[str, Any]] = {
    "ZG System Settings": {
        "status": "info",
        # A tab shown under another app (or None: only switches, they are the app cards' switches).
        "tabs": {"industries_tab": "industries", "apps_tab": None},
        "fields": {
            "enable_ifrs_reports": {"status": "enforced", "enforced_by": "services/report_templates.py"},
            "autofill_source_warehouse": {"status": "enforced", "enforced_by": "events/default_source_warehouse.py"},
            "autofill_payment_entry_account": {"status": "enforced", "enforced_by": "services/payment_entry_accounts.py"},
            "stock_summary_live_only": {"status": "enforced", "enforced_by": "events/stock_summary.py"},
            "autofill_payment_accounts": {"status": "read", "enforced_by": "events/boot.py", "note": "Sent to the Desk invoice forms."},
            "maintenance_mode": {"status": "read", "enforced_by": "events/boot.py"},
        },
    },
    "ZG Application Settings": {
        "status": "info",
        "note": "Advisory: clients_require_auth and block_disabled_clients are not read.",
    },
    "ZG Integration Settings": {"status": "info"},
    "ZG Storage Settings": {"status": "info"},
    "ZG Security Settings": {"status": "info", "note": "Floors are checked, not wired to Frappe's own password / session policy."},
    "ZG Payment Settings": {"status": "info"},
    "ZG Printer Settings": {"status": "info", "note": "No client reads these yet; the apps keep printers on the device."},
    "ZG Notification Settings": {
        "status": "info",
        "fields": {
            "push_enabled": {"status": "enforced", "enforced_by": "api/v1/devices.py"},
            "fcm_server_key": {"status": "enforced", "enforced_by": "api/v1/devices.py"},
        },
    },
    "ZG Sync Settings": {"status": "info"},
    "ZG Number Series Settings": {"status": "info"},
    "ZG Sales Invoice Naming Settings": {
        "status": "enforced",
        "enforced_by": "services/sales_invoice_naming.py",
        "scope": "user",
        "note": "Rules map user + company to a series; the site-wide fallback is below.",
        "fields": {"unmapped_user_behavior": {"scope": "site"}},
    },
    "VanSaleX Settings": {
        "status": "enforced",
        "enforced_by": "services/vansalex_settings.py",
        "fields": {
            **{
                f: {"scope": "user", "note": "A user's ZG Van Sale Profile can override this."}
                for f in (
                    "default_payment_type",
                    "allow_credit_sales",
                    "allow_bank_payment",
                    "show_payment_type_on_invoice",
                    "show_warehouse_on_invoice",
                    "allow_warehouse_change",
                    "restrict_collections_to_route",
                )
            },
            "default_cash_account": {"scope": "user", "note": "A user's profile can set its own account."},
            "default_bank_account": {"scope": "user", "note": "A user's profile can set its own account."},
            "max_adjust_qty": {"enforced_by": "services/vansalex_stock_rules.py"},
            "config_version": {"status": "info", "note": "Counts changes to Modules & Features."},
        },
    },
    "ZG POS Settings": {
        "status": "unwired",
        "note": "Only POS Type has an effect today; the rest is served by pos_settings.get but no client reads it.",
        "fields": {
            "pos_type": {"status": "enforced", "enforced_by": "services/pos_settings.py", "note": "Picks the restaurant or retail engine and switches its industry on."},
        },
    },
    "ZG Theme Settings": {"status": "read", "enforced_by": "services/ui_settings.py", "note": "Sent to the Desk with the boot data."},
    "ZG Language Settings": {"status": "info", "note": "Each user's language stays on their Frappe User."},
    "ZG MyBis Settings": {
        "status": "read",
        "enforced_by": "api/v1/mybis/context.py",
        "fields": {"default_preset": {"status": "unwired", "note": "The app ignores it today."}},
    },
    "Chat AI Settings": {"status": "enforced", "enforced_by": CHAT},
    "Tracker Settings": {"status": "enforced", "enforced_by": "tracker/services/activity.py"},
    "Space Settings": {"status": "info", "note": "Soft pools: stored and shown, not a hard limit."},
}


def doctype(name: str) -> dict[str, Any]:
    return DOCTYPES.get(name) or {}


def field(name: str, fieldname: str) -> dict[str, Any]:
    """Merged notes of one field: the DocType defaults, then the field's own."""
    d = doctype(name)
    out = {
        "scope": d.get("scope", "site"),
        "status": d.get("status", "info"),
        "enforced_by": d.get("enforced_by"),
        "note": None,
    }
    out.update((d.get("fields") or {}).get(fieldname, {}))
    return out
