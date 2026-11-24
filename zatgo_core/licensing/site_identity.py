"""Site identity a licence binds to (decision D5): a UUID in the site's `site_config.json` plus the site name.

The UUID (`zg_site_id`) lives in site_config -- a file only the bench user writes, never copied by a database
backup -- so restoring a backup onto another site does not carry the licence's binding with it. It is created
the first time something asks for it (the Licence page, an import), not on migrate, so upgrading a site writes
nothing to its config.

Offline binding is tamper-evident, not tamper-proof: someone with shell access to the bench can copy both the
UUID and the site name. That is documented, not hidden (docs/licensing.md).
"""

from __future__ import annotations

import uuid

import frappe

CONF_KEY = "zg_site_id"


def site_id(create: bool = False) -> str | None:
    value = frappe.conf.get(CONF_KEY)
    if value or not create:
        return value or None
    from frappe.installer import update_site_config

    value = str(uuid.uuid4())
    update_site_config(CONF_KEY, value)
    frappe.local.conf[CONF_KEY] = value
    from zatgo_core.licensing import audit

    audit.log("site_identity_created", "ZG Licence Config", "site_id", {"site_id": value, "site": site_name()})
    return value


def site_name() -> str:
    return frappe.local.site


def identity(create: bool = False) -> dict[str, str | None]:
    from zatgo_core import __version__
    from zatgo_core.licensing import edition_config, registry

    return {
        "site_id": site_id(create=create),
        "site_name": site_name(),
        "product_id": edition_config.PRODUCT_ID,
        "app_version": __version__,
        "registry_hash": registry.registry_hash(),
    }
