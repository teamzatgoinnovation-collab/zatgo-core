"""ZG Sales Invoice Naming Settings controller — user-wise Sales Invoice
naming series. Enforcement lives in zatgo_core.services.sales_invoice_naming
(Sales Invoice before_insert); this only validates the configuration."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.services.naming_series import get_naming_series_options
from zatgo_core.services.sales_invoice_naming import validate_rules


class ZGSalesInvoiceNamingSettings(Document):
    def onload(self) -> None:
        # Options for the rule grid's series Selects. Sent from here rather than
        # read from Sales Invoice meta in the browser, which a naming manager
        # without Sales Invoice access couldn't load.
        self.set_onload("sales_invoice_series", get_naming_series_options("Sales Invoice"))

    def validate(self) -> None:
        validate_rules(self.rules)
