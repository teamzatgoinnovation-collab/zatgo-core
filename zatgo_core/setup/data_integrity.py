"""Read-only data integrity report for zatgo_core's DocTypes (Phase 4).

    bench --site X execute zatgo_core.setup.data_integrity.report

For every non-single DocType the app ships, it counts:
- rows
- mandatory fields left empty
- Link values that point at a record that no longer exists
- duplicate values in unique fields (and in `zatgo_client_id` where the column exists)
- child rows whose parent is gone

It changes nothing, takes no locks beyond plain SELECTs, and only interpolates identifiers that come from the DocType
meta (table and column names), never a value. Run it before and after a migration (MIGRATION_PLAN.md) and compare.
"""

from __future__ import annotations

from typing import Any

import frappe

APP = "zatgo_core"
_SKIP_FIELDTYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading", "Table",
                    "Table MultiSelect", "Check", "Read Only"}


def _q(identifier: str) -> str:
    """A table or column name from the meta, back-quoted (identifiers never come from input)."""
    if "`" in identifier:
        raise ValueError(f"unexpected identifier {identifier!r}")
    return f"`{identifier}`"


def _scalar(sql: str, values: tuple = ()) -> int:
    return int(frappe.db.sql(sql, values)[0][0] or 0)


def app_doctypes() -> list[str]:
    modules = frappe.get_all("Module Def", filters={"app_name": APP}, pluck="name")
    return frappe.get_all("DocType", filters={"module": ["in", modules], "issingle": 0}, pluck="name", order_by="name")


def check_doctype(doctype: str) -> dict[str, Any]:
    meta = frappe.get_meta(doctype)
    table = _q(f"tab{doctype}")
    found: dict[str, Any] = {"doctype": doctype, "rows": _scalar(f"select count(*) from {table}")}
    if not found["rows"]:
        return found
    fields = [df for df in meta.fields if df.fieldtype not in _SKIP_FIELDTYPES and frappe.db.has_column(doctype, df.fieldname)]

    missing = {}
    for df in fields:
        if df.reqd:
            col = _q(df.fieldname)
            n = _scalar(f"select count(*) from {table} where {col} is null or {col} = ''")
            if n:
                missing[df.fieldname] = n
    dangling = {}
    for df in fields:
        if df.fieldtype == "Link" and df.options and frappe.db.exists("DocType", df.options) \
                and not frappe.get_meta(df.options).issingle:
            col, target = _q(df.fieldname), _q(f"tab{df.options}")
            n = _scalar(f"select count(*) from {table} t left join {target} r on r.name = t.{col} "
                        f"where t.{col} is not null and t.{col} != '' and r.name is null")
            if n:
                dangling[df.fieldname] = n
    duplicates = {}
    unique_cols = [df.fieldname for df in fields if df.unique]
    if frappe.db.has_column(doctype, "zatgo_client_id") and "zatgo_client_id" not in unique_cols:
        unique_cols.append("zatgo_client_id")
    for fieldname in unique_cols:
        col = _q(fieldname)
        n = _scalar(f"select count(*) from (select {col} from {table} where {col} is not null and {col} != '' "
                    f"group by {col} having count(*) > 1) d")
        if n:
            duplicates[fieldname] = n
    orphans = 0
    if meta.istable:
        orphans = _scalar(f"select count(*) from {table} c where c.parenttype is not null and c.parenttype != '' and not exists "
                          f"(select 1 from information_schema.TABLES s where s.TABLE_SCHEMA = database() "
                          f"and s.TABLE_NAME = concat('tab', c.parenttype))")
        for parenttype in frappe.db.sql_list(f"select distinct parenttype from {table} where parenttype is not null and parenttype != ''"):
            if frappe.db.exists("DocType", parenttype) and not frappe.get_meta(parenttype).issingle:
                orphans += _scalar(f"select count(*) from {table} c left join {_q('tab' + parenttype)} p on p.name = c.parent "
                                   "where c.parenttype = %s and p.name is null", (parenttype,))
    for key, value in (("missing_mandatory", missing), ("dangling_links", dangling), ("duplicates", duplicates)):
        if value:
            found[key] = value
    if orphans:
        found["orphan_child_rows"] = orphans
    return found


def report(doctypes: list[str] | None = None) -> dict[str, Any]:
    """{"problems": [...], "checked": n, "rows": total}: one entry per DocType with a problem (read-only)."""
    checked, problems, total = 0, [], 0
    for doctype in doctypes or app_doctypes():
        try:
            found = check_doctype(doctype)
        except Exception as exc:  # a table missing mid-migration is itself worth reporting
            problems.append({"doctype": doctype, "error": str(exc)[:200]})
            continue
        checked += 1
        total += found["rows"]
        if len(found) > 2:
            problems.append(found)
    result = {"checked": checked, "rows": total, "problems": problems}
    print(frappe.as_json(result))
    return result
