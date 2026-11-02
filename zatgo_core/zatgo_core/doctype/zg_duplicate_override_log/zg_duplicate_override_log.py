from frappe.model.document import Document


class ZGDuplicateOverrideLog(Document):
    """Append-only audit of a saved override (written by services/duplicate/enforcement.py)."""
