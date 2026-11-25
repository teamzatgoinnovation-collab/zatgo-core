"""Module -- read-only projection of the licensing registry (zatgo_core/licensing/registry.py).

Written only by licensing/sync.py::sync_registry (on install / migrate); nobody edits it, System Manager and
Administrator included: the code is the truth, and a licence names these ids.
"""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.licensing.sync import refuse_manual_change


class Module(Document):
    def validate(self):
        refuse_manual_change(self)

    def on_trash(self):
        refuse_manual_change(self)
