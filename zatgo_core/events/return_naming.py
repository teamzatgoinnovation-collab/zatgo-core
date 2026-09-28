"""Sales/Purchase Invoice: auto-pick the return-marked naming series.

ERPNext never switches a document's naming series based on `is_return` --
the "-RET-" option is just one more choice in the Select dropdown, so a
return created without manually changing the Series field silently
continues the plain invoice counter (e.g. kasibasia's SINV-00008 return,
which just followed SINV-00007 instead of starting SINV-RET-00001).

Must run in before_insert: Frappe resolves the document name from
naming_series in set_new_name(), which insert() calls before validate()
fires -- a validate-time fix would be too late to affect the name.
"""

from __future__ import annotations

from frappe.model.naming import get_default_naming_series

from zatgo_core.services.naming_series import get_naming_series_options, resolve_series_for_return_state


def sync_naming_series(doc, method=None) -> None:
    current = (doc.get("naming_series") or "").strip()
    if not current:
        current = get_default_naming_series(doc.doctype) or ""
    if not current:
        return

    options = get_naming_series_options(doc.doctype)
    if not options:
        return

    new_series = resolve_series_for_return_state(current, options, bool(doc.get("is_return")))
    if new_series:
        doc.naming_series = new_series
