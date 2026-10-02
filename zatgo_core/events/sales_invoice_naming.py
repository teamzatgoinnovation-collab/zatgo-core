"""Sales Invoice before_insert: pick the naming series before Frappe names it.

before_insert is the last point where naming_series still decides the name:
Document.insert() calls set_new_name() right after it, so a validate-time
change would be too late.

Order: the session user's rule (services/sales_invoice_naming.py) wins; a user
without one keeps ERPNext's normal behaviour plus the generic "-RET-" switch
for returns (events/return_naming.py), unless the settings block unmapped users.
"""

from __future__ import annotations

from zatgo_core.events.return_naming import sync_naming_series
from zatgo_core.services.sales_invoice_naming import enforce_user_series


def set_naming_series(doc, method=None) -> None:
    if doc.get("amended_from"):
        # Frappe names an amendment after the cancelled original (S1-05-1),
        # never from naming_series, so there is nothing to choose here.
        return
    if not enforce_user_series(doc):
        sync_naming_series(doc)
