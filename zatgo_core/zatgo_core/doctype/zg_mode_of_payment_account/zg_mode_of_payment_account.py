"""ZG Mode of Payment Account child table controller.

The set of ledger accounts a Mode of Payment may post to, per company (the
native Mode of Payment Account table allows only one per company). Rows are
validated as a set by the parent -- see
zatgo_core.services.payment_allocation.validate_mode_of_payment.
"""

from __future__ import annotations

from frappe.model.document import Document


class ZGModeofPaymentAccount(Document):
    pass
