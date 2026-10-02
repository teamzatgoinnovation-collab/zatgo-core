"""ZG Sales Invoice Naming Rule child table controller.

Rows are validated as a set by the parent (duplicates, counter collisions);
see zatgo_core.services.sales_invoice_naming.validate_rules.
"""

from __future__ import annotations

from frappe.model.document import Document


class ZGSalesInvoiceNamingRule(Document):
    pass
