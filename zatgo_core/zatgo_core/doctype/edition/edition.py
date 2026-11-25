"""Edition -- a commercial edition (licensing/edition_config.py, docs/licensing.md).

Rules enforced here, so the Desk form, REST and the edition builder are all bound:
- written on the licence issuer site only, by a System Manager (licensing/issuer.py);
- features must be live registry features, not foundation ones, with actions the feature can grant;
- an **Active** edition has no missing dependency -- nothing is ever added for it;
- the version goes up whenever what the edition grants changes;
- an Archived edition cannot change until it is set back to Draft, and only a Draft can be deleted.
Field changes are written to Audit Log by the mixin; feature-table changes by `on_update` below.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document

from zatgo_core.licensing import edition_config, inspector, issuer, registry
from zatgo_core.mixins.auditable import AuditableMixin


def _is_single(doctype: str) -> bool:
    return bool(frappe.db.get_value("DocType", doctype, "issingle"))


class Edition(AuditableMixin, Document):
    # -- the canonical form -----------------------------------------------------------------------------------

    def features_map(self) -> dict[str, list[str]]:
        return edition_config.normalise_features(
            {row.feature: _split(row.actions) for row in self.get("features") or [] if row.feature}
        )

    def to_config(self) -> dict:
        return edition_config.build_config(
            edition_id=self.edition_id,
            edition_name=self.edition_name,
            description=self.description or "",
            version=self.version or 1,
            status=self.status or "Draft",
            preset=self.preset,
            platforms={"desk": self.platform_desk, "desktop": self.platform_desktop, "mobile": self.platform_mobile},
            licence_defaults={
                "licence_type": self.licence_type, "duration_days": self.duration_days or 0,
                "trial_days": self.trial_days or 0, "max_users": self.max_users or 0,
                "max_companies": self.max_companies or 0,
            },
            default_roles=[r.strip() for r in (self.default_roles or "").splitlines() if r.strip()],
            features=self.features_map(),
        )

    def inspect(self) -> dict:
        cfg = self.to_config()
        return inspector.inspect(cfg["features"], platforms=cfg["platforms"], installed=frappe.get_installed_apps(),
                                 is_single=_is_single)

    # -- lifecycle --------------------------------------------------------------------------------------------

    def validate(self) -> None:
        issuer.require_issuer_manager()
        before = self.get_doc_before_save()
        if before is not None and before.status == "Archived" and self.status == "Archived":
            if edition_config.grant_hash(before.to_config()) != edition_config.grant_hash(self.to_config()):
                frappe.throw(_("Set an archived edition back to Draft before changing it."))

        seen = set()
        for row in self.get("features") or []:
            if row.feature in seen:
                frappe.throw(_("Feature {0} is listed twice.").format(row.feature))
            seen.add(row.feature)
            feature = registry.get_feature(row.feature)
            row.module = feature.module if feature else None
            row.actions = ", ".join(edition_config.normalise_features({row.feature: _split(row.actions)})[row.feature])

        config = self.to_config()
        problems = edition_config.validate_config(config)
        if problems:
            frappe.throw("<br>".join(frappe.utils.escape_html(p) for p in problems[:10]),
                         title=_("Edition is not valid"))

        report = self.inspect()
        if self.status == "Active" and report["missing"]:
            frappe.throw(
                _("An active edition cannot miss what its features need. Add them or keep it as a Draft:")
                + "<br>" + "<br>".join(frappe.utils.escape_html(w) for w in report["warnings"] if w.startswith("Missing")),
                title=_("Missing dependencies"),
            )

        new_hash = edition_config.grant_hash(config)
        if before is not None and before.grant_hash and before.grant_hash != new_hash:
            self.version = (before.version or 1) + 1
        self.version = self.version or 1
        self.grant_hash = new_hash
        self.registry_hash = registry.registry_hash()
        self.module_count = report["counts"]["modules"]
        self.feature_count = report["counts"]["features"]
        self.missing_count = len(report["missing"])
        self.dependency_report = json.dumps(report, indent=1, sort_keys=True)

    # Derived fields change on almost every save; the audit log records what a person changed.
    _AUDIT_SKIP = frozenset({"dependency_report", "registry_hash", "grant_hash", "module_count", "feature_count",
                             "missing_count"})

    def _write_audit_entries(self) -> None:
        self._zg_audit_skip = True
        try:
            super()._write_audit_entries()
        finally:
            self._zg_audit_skip = False

    def has_value_changed(self, fieldname):
        if getattr(self, "_zg_audit_skip", False) and fieldname in self._AUDIT_SKIP:
            return False
        return super().has_value_changed(fieldname)

    def on_update(self) -> None:
        super().on_update()
        before = self.get_doc_before_save()
        old = before.features_map() if before is not None else {}
        new = self.features_map()
        if old != new and not self.flags.ignore_zg_audit:
            self._insert_audit_row(
                fieldname="features",
                old_value=json.dumps(old, sort_keys=True) if before is not None else None,
                new_value=json.dumps(new, sort_keys=True),
                ip_address=None, browser="", when=frappe.utils.now_datetime(),
            )

    def on_trash(self) -> None:
        issuer.require_issuer_manager()
        if self.status != "Draft":
            frappe.throw(_("Only a Draft edition can be deleted. Archive {0} instead.").format(self.edition_name))


def _split(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).replace("\n", ",").split(",") if part.strip()]
