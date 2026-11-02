"""Duplicate matching: find existing records that look like the one being entered.

`find_matches` sees every record (a duplicate you may not read still is a duplicate); `present` is the only
thing that turns matches into something shown to a user, and it goes through `frappe.get_list`, so User
Permissions and field-level read permissions apply and a record the viewer cannot read is reported as
"restricted" without its ID or details.

Levels: strong (exact unique identifier, or several identifiers), possible (name alone, or a phone / email
that records legitimately share), suggest (fuzzy name similarity -- never blocks).
"""

from __future__ import annotations

import re
from typing import Any

import frappe
from frappe.utils import cint

from zatgo_core.services.duplicate import config, normalizers

STRONG, POSSIBLE, SUGGEST = "strong", "possible", "suggest"
_RANK = {STRONG: 3, POSSIBLE: 2, SUGGEST: 1}
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CANDIDATE_CAP = 200


def _col(name: str) -> str:
    if not _IDENT.match(name or ""):
        frappe.throw(f"Invalid field name in duplicate rule: {name!r}")
    return f"`{name}`"


def _table_rows(doctype: str) -> int:
    rows = frappe.db.sql(
        "select table_rows from information_schema.tables where table_schema = database() and table_name = %s",
        (f"tab{doctype}",),
    )
    return cint(rows[0][0]) if rows else 0


def _small(doctype: str, limit: int) -> bool:
    return limit > 0 and _table_rows(doctype) <= limit


def _inputs(spec: dict[str, Any], values: dict[str, Any]) -> list[str]:
    """Raw non-empty input values for one field spec."""
    if spec["source"] == "Child Table":
        rows = values.get(spec["child_table"]) or []
        raw = [(r.get(spec["fieldname"]) if isinstance(r, dict) else getattr(r, spec["fieldname"], None)) for r in rows]
    else:
        raw = [values.get(spec["fieldname"])]
    return [str(v).strip() for v in raw if v is not None and str(v).strip()]


def _variants(kind: str, raw: str) -> list[str]:
    if kind == "Phone":
        return normalizers.phone_variants(raw)
    key = normalizers.normalize(kind, raw)
    return sorted({raw, key} - {""})


def _lookup_document(doctype: str, spec: dict, raw: str, scan_ok: bool, exclude: str | None, fresh: bool = False, only: tuple | None = None) -> dict[str, str]:
    """name -> stored value, for records that may hold `raw` in the field (verified by the caller)."""
    col, kind, table = _col(spec["fieldname"]), spec["kind"], f"`tab{doctype}`"
    extra, args = (" and `name` != %s", [exclude]) if exclude else ("", [])
    if only is not None:  # later members of a compound identifier: only inside what the first one found
        extra, args = extra + " and `name` in %s", [*args, only]
    sql = f"select `name`, {col} from {table} where "
    if kind in ("Name", "Text"):
        norm = normalizers.name(raw)
        first = norm.split(" ")[0] if norm else ""
        clauses, params = [f"{col} = %s"], [raw]
        if first:
            clauses.append(f"{col} like %s")
            params.append(first[:4] + "%")
        if scan_ok and first:
            clauses.append(f"{col} like %s")
            params.append("%" + max(norm.split(" "), key=len) + "%")
        found = frappe.db.sql(sql + "(" + " or ".join(clauses) + ")" + extra + f" limit {_CANDIDATE_CAP}", [*params, *args])
        return {n: v for n, v in found if normalizers.name(v) == norm}
    variants = _variants(kind, raw)
    lock = " for update" if fresh else ""  # locking read: sees rows committed after this transaction's snapshot
    found = frappe.db.sql(sql + f"{col} in %s" + extra + f" limit {_CANDIDATE_CAP}" + lock, [tuple(variants), *args]) if variants else ()
    key = normalizers.normalize(kind, raw)
    out = {n: v for n, v in found if normalizers.normalize(kind, v) == key}
    if not out and scan_ok and kind in ("Phone", "Tax ID"):
        # Stored with spaces / dashes: strip them in SQL (a scan -- only on tables under the scan limit).
        stripped = f"replace(replace(replace(replace(replace({col},' ',''),'-',''),'(',''),')',''),'.','')"
        found = frappe.db.sql(
            sql + f"{stripped} like %s" + extra + f" limit {_CANDIDATE_CAP}",
            ["%" + re.sub(r"\D", "", key)[-9:] + "%" if kind == "Phone" else "%" + key[-9:] + "%", *args],
        )
        out = {n: v for n, v in found if normalizers.normalize(kind, v) == key}
    return out


def _lookup_child(doctype: str, spec: dict, raw: str, exclude: str | None, fresh: bool = False, only: tuple | None = None) -> dict[str, str]:
    table_field = frappe.get_meta(doctype).get_field(spec["child_table"])
    if not table_field:
        return {}
    col, kind = _col(spec["fieldname"]), spec["kind"]
    variants = _variants(kind, raw)
    if not variants:
        return {}
    extra, args = (" and `parent` != %s", [exclude]) if exclude else ("", [])
    if only is not None:
        extra, args = extra + " and `parent` in %s", [*args, only]
    found = frappe.db.sql(
        f"select `parent`, {col} from `tab{table_field.options}` where `parenttype` = %s and `parentfield` = %s and {col} in %s{extra} limit {_CANDIDATE_CAP}{' for update' if fresh else ''}",
        [doctype, spec["child_table"], tuple(variants), *args],
    )
    key = normalizers.normalize(kind, raw)
    return {n: v for n, v in found if normalizers.normalize(kind, v) == key}


def _lookup_contacts(doctype: str, spec: dict, raw: str, exclude: str | None) -> dict[str, str]:
    """Customers / Suppliers (...) whose linked Contacts hold the e-mail / phone."""
    kind = spec["kind"]
    if kind not in ("Email", "Phone"):
        return {}
    variants = _variants(kind, raw)
    if not variants:
        return {}
    key = normalizers.normalize(kind, raw)
    queries = (
        ("`tabContact Email` x", "x.email_id", "x.parent") if kind == "Email" else ("`tabContact Phone` x", "x.phone", "x.parent"),
    )
    if kind == "Phone":
        queries += (("`tabContact` x", "x.mobile_no", "x.name"),)
    out: dict[str, str] = {}
    for table, col, contact in queries:
        rows = frappe.db.sql(
            f"select dl.link_name, {col} from {table} join `tabDynamic Link` dl on dl.parent = {contact} and dl.parenttype = 'Contact' "
            f"where dl.link_doctype = %s and {col} in %s limit {_CANDIDATE_CAP}",
            (doctype, tuple(variants)),
        )
        out.update({n: v for n, v in rows if n != exclude and normalizers.normalize(kind, v) == key})
    return out


def _docstatus_ok(doctype: str, names: list[str]) -> set[str]:
    """Names that are not cancelled (submittable DocTypes only)."""
    if not names or not frappe.get_meta(doctype).is_submittable:
        return set(names)
    return set(frappe.get_all(doctype, filters={"name": ["in", names], "docstatus": ["<", 2]}, pluck="name"))


def find_matches(
    doctype: str,
    values: dict[str, Any],
    exclude: str | None = None,
    *,
    rule: dict[str, Any] | None = None,
    limit: int | None = None,
    fresh: bool = False,
) -> list[dict[str, Any]]:
    """Existing records of `doctype` that match `values`, strongest first.

    Each item: {name, level, matched_on: [{field, kind, role, value}], score}. `values` maps fieldname ->
    value (child-table rows as a list of dicts under the table's fieldname). `exclude` is the document being
    edited. `fresh` re-reads exact identifiers with locking reads (the save-time re-check after the advisory
    lock, so a concurrent request's committed insert is seen despite this transaction's snapshot)."""
    rule = rule or config.rule_for(doctype)
    if not rule:
        return []
    cfg = config.settings()
    limit = limit or cfg["result_limit"]
    scan_ok = _small(doctype, cfg["scan_limit"])
    meta = frappe.get_meta(doctype)

    # hits[name][spec_index] = list of matched raw values; counts[(spec_index, key)] = #records sharing it
    hits: dict[str, dict[int, str]] = {}
    sharers: dict[tuple[int, str], set[str]] = {}
    members_of: dict[str, list[int]] = {}
    for i, spec in enumerate(rule["fields"]):
        members_of.setdefault(spec["group"] or f"#{i}", []).append(i)
    for members in members_of.values():
        only: tuple | None = None
        for i in members:
            spec = rule["fields"][i]
            if spec["source"] == "Document" and spec["fieldname"] != "name" and not meta.has_field(spec["fieldname"]):
                break  # rule drifted from the DocType (field removed): ignore, never fail a save
            inside: dict[str, str] = {}
            for raw in _inputs(spec, values):
                if spec["source"] == "Child Table":
                    found = _lookup_child(doctype, spec, raw, exclude, fresh, only)
                else:
                    found = _lookup_document(doctype, spec, raw, scan_ok, exclude, fresh, only)
                    if spec["source"] == "Linked Contact" and only is None:
                        found.update(_lookup_contacts(doctype, spec, raw, exclude))
                key = normalizers.normalize(spec["kind"], raw)
                for name, stored in found.items():
                    hits.setdefault(name, {})[i] = stored
                    sharers.setdefault((i, key), set()).add(name)
                inside.update(found)
            if len(members) > 1:
                if not inside:
                    break  # a compound identifier needs every member: nothing more to look up
                only = tuple(inside)

    alive = _docstatus_ok(doctype, list(hits)) if rule["type"] == "Transaction" or meta.is_submittable else set(hits)
    results: list[dict[str, Any]] = []
    for name, matched in hits.items():
        if name not in alive:
            continue
        item = _score(rule, values, name, matched, sharers)
        if item:
            results.append(item)

    if rule["fuzzy"]:
        taken = {r["name"] for r in results}
        results += _fuzzy(doctype, rule, values, exclude, taken, cfg, scan_ok)
    results.sort(key=lambda r: (-_RANK[r["level"]], -r["score"], r["name"]))
    return results[:limit]


def _score(rule, values, name, matched, sharers) -> dict[str, Any] | None:
    specs = rule["fields"]
    # An identifier = a lone field, or a whole group whose members all matched this record.
    groups: dict[str, list[int]] = {}
    for i, s in enumerate(specs):
        groups.setdefault(s["group"] or f"#{i}", []).append(i)
    unique = shared_common = named = 0
    shared_values: set[tuple[str, str]] = set()  # one number held in two fields (Contact.mobile_no + phone table) is ONE identifier
    on: list[dict[str, str]] = []
    for members in groups.values():
        if not all(i in matched for i in members):
            continue
        head = specs[members[0]]
        for i in members:
            on.append({"field": specs[i]["fieldname"], "kind": specs[i]["kind"], "role": specs[i]["role"], "value": str(matched[i])})
        if head["role"] == "Name":
            named += 1
        elif head["role"] == "Shared":
            keys = [(i, normalizers.normalize(specs[i]["kind"], matched[i])) for i in members]
            if any(len(sharers.get(k, ())) >= 2 for k in keys):
                shared_common += 1  # several records already share it -- not evidence on its own
            else:
                shared_values.update((specs[i]["kind"], k) for i, k in keys)
        else:
            unique += 1
    shared = len(shared_values)
    if not (unique or shared or shared_common or named):
        return None
    if unique or shared + (1 if named else 0) >= 2 or (named and shared):
        level = STRONG
    else:
        level = POSSIBLE
    return {"name": name, "level": level, "matched_on": on, "score": unique * 10 + shared * 4 + named * 2 + shared_common}


def _fuzzy(doctype, rule, values, exclude, taken, cfg, scan_ok) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in rule["fields"]:
        if spec["kind"] != "Name" or spec["source"] != "Document":
            continue
        for raw in _inputs(spec, values):
            norm = normalizers.name(raw)
            tokens = norm.split(" ")
            if len(norm) < 4:
                continue
            col = _col(spec["fieldname"])
            clauses, params = [f"{col} like %s"], [tokens[0][:3] + "%"]
            if scan_ok:
                clauses.append(f"{col} like %s")
                params.append("%" + max(tokens, key=len) + "%")
            extra, args = (" and `name` != %s", [exclude]) if exclude else ("", [])
            rows = frappe.db.sql(
                f"select `name`, {col} from `tab{doctype}` where (" + " or ".join(clauses) + ")" + extra + f" limit {_CANDIDATE_CAP}",
                [*params, *args],
            )
            for name, stored in rows:
                ratio = normalizers.similarity(norm, normalizers.name(stored))
                if name not in taken and ratio >= cfg["fuzzy_threshold"]:
                    taken.add(name)
                    out.append({"name": name, "level": SUGGEST, "score": round(ratio, 3),
                                "matched_on": [{"field": spec["fieldname"], "kind": "Name", "role": "Similar", "value": str(stored)}]})
    return out


def worst(matches: list[dict[str, Any]]) -> str | None:
    return max((m["level"] for m in matches), key=_RANK.get, default=None)


def present(doctype: str, matches: list[dict[str, Any]], rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Matches as shown to the current user: title + configured details of records they may read; the rest
    as {restricted: True} with the level only."""
    if not matches:
        return []
    meta = frappe.get_meta(doctype)
    title_field = meta.title_field if meta.title_field and meta.has_field(meta.title_field) else None
    wanted = [f for f in dict.fromkeys(rule["display_fields"] + [s["fieldname"] for s in rule["fields"] if s["show"] and s["source"] == "Document"])
              if meta.has_field(f) and f != title_field and meta.get_field(f).fieldtype not in frappe.model.table_fields]
    names = [m["name"] for m in matches]
    try:
        rows = frappe.get_list(doctype, filters={"name": ["in", names]}, fields=["name", *([title_field] if title_field else []), *wanted], limit_page_length=len(names))
    except frappe.PermissionError:
        rows = []  # no read access to the DocType at all: every match is restricted
    readable = {r["name"]: r for r in rows}
    out = []
    for m in matches:
        row = readable.get(m["name"])
        if row is None:
            out.append({"level": m["level"], "restricted": True, "matched_on": [{"field": x["field"], "kind": x["kind"], "role": x["role"]} for x in m["matched_on"]]})
            continue
        labels = {f.fieldname: f.label for f in meta.fields}
        out.append({
            "name": m["name"],
            "title": row.get(title_field) if title_field else m["name"],
            "level": m["level"],
            "matched_on": m["matched_on"],
            "details": [{"fieldname": f, "label": labels.get(f, f), "value": row.get(f)} for f in wanted if row.get(f) not in (None, "")],
            "restricted": False,
        })
    return out
