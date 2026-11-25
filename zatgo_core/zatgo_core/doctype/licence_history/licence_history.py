"""Licence History -- the issuer's record of a signed licence.

Written only by licensing/issuing.py; nobody edits it by hand, System Manager and Administrator included.
"""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.licensing.licences import refuse_manual_change


class LicenceHistory(Document):
    def validate(self):
        refuse_manual_change(self)

    def on_trash(self):
        refuse_manual_change(self)
