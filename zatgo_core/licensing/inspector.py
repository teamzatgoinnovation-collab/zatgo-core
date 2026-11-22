"""Edition Dependency Inspector: what a set of features needs and touches.

Given an edition's features (and platforms), it reports:
- **missing**: features they require that the edition does not include -- with the module each belongs to.
  Nothing is ever added: a paid module is an explicit edition decision.
- **doctypes / reports / pages / workspaces / api_prefixes**: everything the edition (foundation included) maps.
- **settings**: the Single DocTypes the edition lets users change.
- **posting**: for each transaction DocType it allows, the ledgers ERPNext writes on submit and the background
  jobs that keep them right. Those ledgers are never gated (registry.NEVER_GATE): they are listed so a reader can
  see that, e.g., a Sales-only edition still writes GL Entry.
- **warnings**: features this site cannot run (their app is not installed), features no edition platform can
  reach, retired / unknown ids.

Pure: the caller passes the installed apps and a Single-DocType test, so tests and the issuer site share it.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from zatgo_core.licensing import edition_config, registry

REPOST_JOBS = (
    "erpnext.stock.doctype.repost_item_valuation.repost_item_valuation.repost_entries (hourly maintenance)",
    "erpnext.stock.doctype.repost_item_valuation.repost_item_valuation.run_parallel_reposting (every 15 minutes)",
)
_STOCK = ("Stock Ledger Entry", "GL Entry (perpetual inventory)", "Repost Item Valuation (back-dated entries)")
_MONEY = ("GL Entry", "Payment Ledger Entry")

# What ERPNext writes itself when these are submitted (ERPNext 16 controllers), and the jobs that follow up.
POSTING_EFFECTS: dict[str, dict[str, tuple[str, ...]]] = {
    "Sales Invoice": {"ledgers": _MONEY + ("Stock Ledger Entry (with Update Stock)",), "jobs": REPOST_JOBS},
    "Purchase Invoice": {"ledgers": _MONEY + ("Stock Ledger Entry (with Update Stock)",), "jobs": REPOST_JOBS},
    "Delivery Note": {"ledgers": _STOCK, "jobs": REPOST_JOBS},
    "Purchase Receipt": {"ledgers": _STOCK, "jobs": REPOST_JOBS},
    "Stock Entry": {"ledgers": _STOCK, "jobs": REPOST_JOBS},
    "Stock Reconciliation": {"ledgers": _STOCK, "jobs": REPOST_JOBS},
    "Landed Cost Voucher": {"ledgers": _STOCK, "jobs": REPOST_JOBS},
    "Payment Entry": {"ledgers": _MONEY, "jobs": ()},
    "Journal Entry": {"ledgers": _MONEY, "jobs": ()},
    "Period Closing Voucher": {"ledgers": ("GL Entry", "Account Closing Balance"), "jobs": ()},
    "POS Invoice": {"ledgers": ("consolidated into Sales Invoices by the POS Closing Entry",), "jobs": ()},
    "POS Closing Entry": {"ledgers": ("POS Invoice Merge Log", "Sales Invoice (consolidated)"), "jobs": ()},
    "Expense Claim": {"ledgers": _MONEY, "jobs": ()},
    "Payroll Entry": {"ledgers": ("Journal Entry (salary accrual)",) + _MONEY, "jobs": ()},
}
ZATCA_EFFECT = "ZATCA Invoice + ZATCA Submission Log (zatca_integration)"


def inspect(
    features: Mapping[str, Iterable[str]] | Iterable[str],
    *,
    platforms: Mapping[str, Any] | None = None,
    installed: Iterable[str] | None = None,
    is_single: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    selected = edition_config.normalise_features(features)
    installed = set(installed) if installed is not None else None
    platforms = platforms or {p: 1 for p in registry.PLATFORMS}
    on_platforms = {p for p, v in platforms.items() if v}
    deps = registry.resolve_requirements(selected)

    rows, unavailable, platform_mismatch = [], [], []
    doctypes: dict[str, dict[str, Any]] = {}
    reports, pages, workspaces, prefixes, modules = set(), set(), set(), set(), {}

    def take(feature: registry.Feature, narrowed: Iterable[str]) -> None:
        acts = set(edition_config.effective_actions(feature, narrowed))
        for g in feature.doctypes:
            entry = doctypes.setdefault(g.doctype, {"doctype": g.doctype, "actions": set(), "features": [],
                                                    "match": []})
            entry["actions"].update(a for a in g.actions if a in acts)
            entry["features"].append(feature.id)
            if g.match:
                entry["match"].append({"feature": feature.id, **{k: (list(v) if isinstance(v, tuple) else v)
                                                                  for k, v in g.match}})
        reports.update(feature.reports)
        pages.update(feature.pages)
        workspaces.update(feature.workspaces)
        prefixes.update(feature.api_prefixes)

    for feature in registry.foundation_features():
        take(feature, ())
    for fid, narrowed in selected.items():
        feature = registry.get_feature(fid)
        if feature is None or feature.retired:
            continue
        take(feature, narrowed)
        available = installed is None or feature.source_app in installed
        reachable = bool(on_platforms & set(feature.platforms))
        if not available:
            unavailable.append({"feature": fid, "source_app": feature.source_app})
        if not reachable:
            platform_mismatch.append({"feature": fid, "platforms": list(feature.platforms)})
        module = registry.get_module(feature.module)
        modules.setdefault(feature.module, {"id": feature.module, "label": module.label if module else feature.module,
                                            "features": 0})
        modules[feature.module]["features"] += 1
        rows.append({
            "id": fid, "label": feature.label, "module": feature.module,
            "actions": list(edition_config.effective_actions(feature, narrowed)),
            "narrowed": bool(narrowed), "available": available, "platform_ok": reachable,
        })

    allowed_doctypes = sorted(doctypes.values(), key=lambda d: d["doctype"])
    for entry in allowed_doctypes:
        entry["actions"] = [a for a in registry.ACTIONS if a in entry["actions"]]

    zatca = "tax.zatca" in selected
    posting = []
    for entry in allowed_doctypes:
        effect = POSTING_EFFECTS.get(entry["doctype"])
        if effect and "submit" in entry["actions"]:
            ledgers = list(effect["ledgers"])
            if zatca and entry["doctype"] == "Sales Invoice":
                ledgers.append(ZATCA_EFFECT)
            posting.append({"doctype": entry["doctype"], "ledgers": ledgers, "jobs": list(effect["jobs"])})

    settings = [d["doctype"] for d in allowed_doctypes if is_single and is_single(d["doctype"])]
    warnings = [
        f"Missing {m['feature']} ({m['module'] or 'unknown module'}), needed by {m['needed_by']}"
        + (f" for {', '.join(m['actions'])}" if m["actions"] else "")
        for m in deps["missing"]
    ]
    warnings += [f"{u['feature']} needs the {u['source_app']} app, which is not installed on this site" for u in unavailable]
    warnings += [f"{p['feature']} runs on {', '.join(p['platforms'])}, none of the edition's platforms"
                 for p in platform_mismatch]
    warnings += [f"Unknown feature {fid}" for fid in deps["unknown"]]
    warnings += [f"Retired feature {fid}" for fid in deps["retired"]]
    return {
        "ok": not (deps["missing"] or deps["unknown"] or deps["retired"]),
        "features": sorted(rows, key=lambda r: r["id"]),
        "foundation": deps["foundation"],
        "modules": sorted(modules.values(), key=lambda m: m["id"]),
        "missing": deps["missing"],
        "unknown": deps["unknown"],
        "retired": deps["retired"],
        "unavailable": unavailable,
        "platform_mismatch": platform_mismatch,
        "doctypes": allowed_doctypes,
        "reports": sorted(reports),
        "pages": sorted(pages),
        "workspaces": sorted(workspaces),
        "api_prefixes": sorted(prefixes),
        "settings": settings,
        "posting": posting,
        "warnings": warnings,
        "counts": {"modules": len(modules), "features": len(rows), "doctypes": len(allowed_doctypes),
                   "reports": len(reports)},
    }
