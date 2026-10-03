"""ZG Payment Allocation child table controller (Payment Entry
`custom_payment_details`).

Which Mode of Payment + ledger account each part of a Payment Entry's money
was actually received into / paid from. Validated and posted by
zatgo_core.services.payment_allocation (rows) and
zatgo_core.overrides.payment_entry (GL split) -- see those modules.
"""

from __future__ import annotations

from frappe.model.document import Document


class ZGPaymentAllocation(Document):
    pass
