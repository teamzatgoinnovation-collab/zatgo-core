"""Is a ZatGo app or industry available on this site, and if not, why not (ADR-003).

One answer built from the layers that already decide it; this module reads them and changes none:

| layer     | apps (services/app_catalog.py)            | industries (industries/registry.py)          |
|-----------|--------------------------------------------|----------------------------------------------|
| known     | a catalog entry                            | a registry entry                             |
| installed | always (they ship inside zatgo_core)       | implemented in this release                  |
| enabled   | its switch (`app_state.switch_on`)         | its row in ZatGo System Settings             |
| module    | a module covering it is on (Module Settings, `module_settings.app_allowed`) | same, `industry_allowed` |
| licensed  | `licensing.gate.app_licensed`              | `licensing.gate.industry_licensed`           |

Modules themselves (`module(id)`, the licensing registry's modules) have installed (their app), enabled (their Module
Settings row) and licensed (a licensed feature of theirs, or no licence enforced).

`available` = all of them, the same rule `app_state.is_on` and `industries.gate.is_enabled` apply. `explain` also
lists what an app or industry requires that is not on (reported, never switched on).

Per-user authorization is not a layer here: roles, DocPerms and User Permissions decide it per document, and a
Module Settings role list arrives in Phase 5. Visibility (sidebar, folder) is computed from availability and the
user's permissions, never the other way round.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

KIND_APP = "app"
KIND_INDUSTRY = "industry"
KIND_MODULE = "module"


@dataclass(frozen=True)
class Availability:
    key: str
    kind: str | None
    known: bool
    installed: bool
    enabled: bool
    licensed: bool
    missing_requirements: tuple[str, ...] = field(default=())
    module_enabled: bool = True

    @property
    def available(self) -> bool:
        return self.known and self.installed and self.enabled and self.module_enabled and self.licensed

    @property
    def reason(self) -> str | None:
        """The first layer that says no, as a short sentence; None when available."""
        if not self.known:
            return f"{self.key} is not a ZatGo app or industry"
        if not self.installed:
            return f"{self.key} is not available in this release"
        if not self.enabled:
            return f"{self.key} is switched off on this site"
        if not self.module_enabled:
            return f"the module of {self.key} is switched off on this site (Module Settings)"
        if not self.licensed:
            return f"{self.key} is not included in this site's licence"
        return None

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["missing_requirements"] = list(self.missing_requirements)
        out["available"] = self.available
        out["reason"] = self.reason
        return out


def _unknown(key: str) -> Availability:
    return Availability(key, None, False, False, False, False)


def app(key: str) -> Availability:
    """A catalog app (`vansalex`, `zatgo_pos`, `chat_ai`, ...)."""
    from zatgo_core.licensing.gate import app_licensed
    from zatgo_core.services import app_catalog, app_state, module_settings

    entry = app_catalog.get(key)
    if entry is None:
        return _unknown(key)
    missing = tuple(dep for dep in entry.get("requires") or () if not app_state.is_on(dep))
    return Availability(
        key=key,
        kind=KIND_APP,
        known=True,
        installed=True,
        enabled=app_state.switch_on(key),
        licensed=app_licensed(key),
        missing_requirements=missing,
        module_enabled=module_settings.app_allowed(key),
    )


def industry(key: str) -> Availability:
    """An industry of industries/registry.py (`restaurant`, `gym`, ...)."""
    from zatgo_core.industries import gate, registry
    from zatgo_core.licensing.gate import industry_licensed
    from zatgo_core.services import module_settings

    entry = registry.get(key)
    if entry is None:
        return _unknown(key)
    on = gate.switched_on_keys()
    missing = tuple(dep for dep in entry.requires_industries if dep not in on)
    return Availability(
        key=key,
        kind=KIND_INDUSTRY,
        known=True,
        installed=bool(entry.implemented),
        enabled=key in on,
        licensed=industry_licensed(key),
        missing_requirements=missing,
        module_enabled=module_settings.industry_allowed(key),
    )


def module(module_id: str) -> Availability:
    """A licensing-registry module (`sales`, `pos`, `vansalex`, ...) as Module Settings and the licence have it."""
    from zatgo_core.licensing import entitlement, registry
    from zatgo_core.services import module_settings

    entry = registry.get_module(module_id)
    if entry is None:
        return _unknown(module_id)
    active = entitlement.active()
    features = [f.id for f in registry.features_of_module(module_id) if not f.retired]
    licensed = active is None or module_id in module_settings.ALWAYS_ON or any(f in active.feature_ids for f in features)
    enabled = module_settings.is_enabled(module_id)
    missing = tuple(sorted(m for m in module_settings.dependencies().get(module_id, set()) if not module_settings.is_enabled(m)))
    return Availability(
        key=module_id,
        kind=KIND_MODULE,
        known=True,
        installed=module_settings.is_installed(module_id),
        enabled=enabled,
        licensed=licensed,
        missing_requirements=missing,
    )


def of(key: str) -> Availability:
    """An app if the catalog knows `key`, else an industry."""
    found = app(key)
    return found if found.known else industry(key)


def is_available(key: str) -> bool:
    return of(key).available


def explain(key: str) -> dict[str, Any]:
    return of(key).as_dict()


def summary() -> dict[str, dict[str, Any]]:
    """Every app and industry: key -> explain(). For the hub, health checks and support (modules:
    services/module_settings.status)."""
    from zatgo_core.industries import registry
    from zatgo_core.services import app_catalog

    out = {a["key"]: app(a["key"]).as_dict() for a in app_catalog.catalog()}
    for key in registry.INDUSTRIES:
        out.setdefault(key, industry(key).as_dict())
    return out
