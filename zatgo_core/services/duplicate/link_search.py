"""Smart Link search: standard `frappe.desk.search.search_link`, plus the business identifiers.

The core function runs first and its results are kept as they are (title, ID and search-field hits). For a
DocType with a duplicate rule we then (1) add records whose tax ID / phone / e-mail / barcode / code equals
what was typed, and (2) append the rule's identifying details to each description, e.g.
"ABC Trading — VAT: 310000000000003". Any problem here returns the core results untouched.
Registered in hooks.py `override_whitelisted_methods` -- deliberately outside the gated `api/` tree so Link
fields keep working when the app is switched off."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.desk.search import search_link as _core_search_link

from zatgo_core.services.duplicate import config, matcher, normalizers

_MIN_TEXT = 3


def _plausible(kind: str, txt: str) -> bool:
    if kind == "Email":
        return "@" in txt and len(txt) >= 5
    if kind in ("Phone", "Tax ID"):
        return len([c for c in normalizers.tax_id(txt) if c.isdigit()]) >= 6
    return len(txt) >= _MIN_TEXT  # Code


def _identifier_values(rule: dict[str, Any], txt: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for spec in rule["fields"]:
        if spec["role"] == "Name" or not _plausible(spec["kind"], txt):
            continue
        if spec["source"] == "Child Table":
            values.setdefault(spec["child_table"], []).append({spec["fieldname"]: txt})
        else:
            values[spec["fieldname"]] = txt
    return values


def _details(doctype: str, rule: dict[str, Any], names: list[str]) -> dict[str, str]:
    meta = frappe.get_meta(doctype)
    fields = [s for s in rule["fields"] if s["show"] and s["source"] == "Document" and s["role"] != "Name"
              and meta.has_field(s["fieldname"]) and meta.get_field(s["fieldname"]).fieldtype not in frappe.model.table_fields]
    if not fields or not names:
        return {}
    wanted = list(dict.fromkeys(s["fieldname"] for s in fields))
    rows = frappe.get_list(doctype, filters={"name": ["in", names]}, fields=["name", *wanted], limit_page_length=len(names))
    labels = {f.fieldname: f.label for f in meta.fields}
    short = {"Tax ID": "VAT", "Phone": "Mobile", "Email": "Email", "Code": None}
    out = {}
    for row in rows:
        parts = []
        for s in fields:
            value = row.get(s["fieldname"])
            if value:
                parts.append(f"{short.get(s['kind']) or labels.get(s['fieldname'], s['fieldname'])}: {value}")
        out[row["name"]] = " | ".join(parts)
    return out


@frappe.whitelist()
def search_link(*args, **kwargs):
    results = _core_search_link(*args, **kwargs)
    try:
        return _enhance(results, *args, **kwargs)
    except Exception:
        frappe.log_error(title="Duplicate prevention link search enhancement failed")
        return results


def _enhance(results, doctype=None, txt=None, query=None, *_, page_length=10, **__):
    doctype = doctype or __.get("doctype")
    rule = config.rule_for(doctype) if doctype else None
    txt = (txt or "").strip()
    if not rule or query or not config.settings()["live_lookup"]:
        return results
    results = list(results or [])
    seen = {r.get("value") for r in results}
    values = _identifier_values(rule, txt) if len(txt) >= _MIN_TEXT else {}
    extra: list[str] = []
    if values:
        shown = matcher.present(doctype, matcher.find_matches(doctype, values, rule=rule, limit=int(page_length or 10)), rule)
        extra = [m["name"] for m in shown if not m["restricted"] and m["name"] not in seen]
    detail = _details(doctype, rule, [r["value"] for r in results] + extra)
    meta = frappe.get_meta(doctype)
    title_field = meta.title_field if meta.title_field and meta.has_field(meta.title_field) else None
    titles = dict(frappe.get_list(doctype, filters={"name": ["in", extra]}, fields=["name", title_field], as_list=True)) if extra and title_field else {}
    added = [{"value": n, "description": " — ".join(p for p in (titles.get(n), detail.get(n)) if p)} for n in extra]
    for r in results:
        if detail.get(r["value"]):
            r["description"] = " — ".join(p for p in (r.get("description"), detail[r["value"]]) if p)
    return (added + results)[: max(int(page_length or 10), len(results))]
