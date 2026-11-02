"""ZG Duplicate Rule controller -- one rule per DocType; validated against the DocType's real fields."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class ZGDuplicateRule(Document):
    def validate(self) -> None:
        if not frappe.db.exists("DocType", self.ref_doctype):
            frappe.throw(f"DocType {self.ref_doctype} does not exist.")
        meta = frappe.get_meta(self.ref_doctype)
        for row in self.fields:
            self._validate_row(meta, row)
        if self.enabled and not [r for r in self.fields if not r.excluded]:
            frappe.throw("An enabled rule needs at least one identifying field that is not excluded.")
        for name in self.display_list():
            if not meta.has_field(name) and name not in ("name", "creation", "modified"):
                frappe.throw(f"Result Details: {self.ref_doctype} has no field {name}.")

    def _validate_row(self, meta, row) -> None:
        if row.source == "Child Table":
            table = meta.get_field(row.child_table or "")
            if not table or table.fieldtype not in ("Table", "Table MultiSelect"):
                frappe.throw(f"Row {row.idx}: {row.child_table or '(empty)'} is not a table field of {self.ref_doctype}.")
            if not frappe.get_meta(table.options).has_field(row.fieldname):
                frappe.throw(f"Row {row.idx}: {table.options} has no field {row.fieldname}.")
        elif row.source == "Document" and not meta.has_field(row.fieldname) and row.fieldname != "name":
            frappe.throw(f"Row {row.idx}: {self.ref_doctype} has no field {row.fieldname}.")

    def display_list(self) -> list[str]:
        return [p.strip() for p in (self.display_fields or "").split(",") if p.strip()]

    def on_update(self) -> None:
        from zatgo_core.services.duplicate import config

        config.clear_cache()

    def on_trash(self) -> None:
        self.on_update()
