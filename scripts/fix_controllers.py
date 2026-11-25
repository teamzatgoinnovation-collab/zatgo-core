#!/usr/bin/env python3
"""Rewrite DocType controllers with clean indentation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "zatgo_core" / "zatgo_core" / "doctype"

CONTROLLERS: dict[str, str] = {
    "zg_system_settings": '''\
"""ZatGo System Settings controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class ZatGoSystemSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Global ERP foundation settings for the ZatGo ecosystem."""

    def validate(self) -> None:
        self._validate_defaults()

    def _validate_defaults(self) -> None:
        if self.default_warehouse and self.default_company:
            warehouse_company = frappe.db.get_value(
                "Warehouse", self.default_warehouse, "company"
            )
            if warehouse_company and warehouse_company != self.default_company:
                frappe.throw(
                    frappe._("Default Warehouse must belong to Default Company")
                )
''',
    "zg_company_settings": '''\
"""Company Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.company_settings import validate_company_settings


class CompanySettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Company-scoped configuration for ZatGo apps."""

    def validate(self) -> None:
        validate_company_settings(self)
''',
    "zg_branch_settings": '''\
"""Branch Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.branch_settings import validate_branch_settings


class BranchSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Branch-scoped operational configuration."""

    def validate(self) -> None:
        validate_branch_settings(self)
''',
    "zg_application_registry": '''\
"""Application Registry controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.app_registry import validate_app_registry


class ApplicationRegistry(AuditableMixin, CacheableSettingsMixin, Document):
    """Installed ZatGo application registry row."""

    def validate(self) -> None:
        validate_app_registry(self)
''',
    "zg_feature_flag": '''\
"""Feature Flag controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.feature_flags import validate_feature_flag


class FeatureFlag(AuditableMixin, CacheableSettingsMixin, Document):
    """Runtime feature toggle without code changes."""

    def validate(self) -> None:
        validate_feature_flag(self)
''',
    "zg_integration_settings": '''\
"""Integration Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.integrations import validate_integration_settings


class IntegrationSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """External integration credentials and toggles."""

    def validate(self) -> None:
        validate_integration_settings(self)
''',
    "zg_printer_settings": '''\
"""Printer Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class PrinterSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Global printer defaults for POS / kitchen / labels."""

    pass
''',
    "zg_payment_settings": '''\
"""Payment Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class PaymentSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Payment method and surcharge configuration."""

    pass
''',
    "zg_notification_settings": '''\
"""ZatGo Notification Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class ZatGoNotificationSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Notification channel configuration."""

    pass
''',
    "zg_storage_settings": '''\
"""Storage Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class StorageSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """File storage and backup provider configuration."""

    pass
''',
    "zg_security_settings": '''\
"""ZatGo Security Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.security import validate_security_settings


class ZatGoSecuritySettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Password, session, and access-control policy."""

    def validate(self) -> None:
        validate_security_settings(self)
''',
    "zg_sync_settings": '''\
"""Sync Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class SyncSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Offline sync and queue configuration."""

    pass
''',
    "zg_number_series_item": '''\
"""Number Series Item child table controller."""

from __future__ import annotations

from frappe.model.document import Document


class NumberSeriesItem(Document):
    """Child row defining a document numbering series."""

    pass
''',
    "zg_number_series_settings": '''\
"""Number Series Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.number_series import validate_number_series


class NumberSeriesSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Central numbering series registry for all ZatGo documents."""

    def validate(self) -> None:
        validate_number_series(self)
''',
    "zg_audit_log": '''\
"""Audit Log controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class AuditLog(Document):
    """Immutable audit trail entry (no client edits expected)."""

    def on_trash(self) -> None:
        if "System Manager" not in frappe.get_roles():
            frappe.throw(frappe._("Only System Manager can delete audit logs"))
''',
    "zg_user_preferences": '''\
"""User Preferences controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class UserPreferences(AuditableMixin, CacheableSettingsMixin, Document):
    """Per-user desk preferences for ZatGo applications."""

    pass
''',
}


def main() -> None:
    for slug, content in CONTROLLERS.items():
        path = ROOT / slug / f"{slug}.py"
        path.write_text(content, encoding="utf-8")
        print(f"Fixed {slug}")


if __name__ == "__main__":
    import sys

    if "--i-know-this-overwrites" not in sys.argv:
        sys.exit(
            "Refusing to run: this script OVERWRITES DocType files that have since been edited by hand "
            "(its templates are stale -- e.g. it would reduce zg_system_settings.py to a stub). "
            "Edit the DocType JSON / controller directly; pass --i-know-this-overwrites only if you mean it."
        )
    main()
