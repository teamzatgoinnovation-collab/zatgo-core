from frappe.model.document import Document


class DuplicateOverrideLog(Document):
    """Append-only audit of a saved override (written by services/duplicate/enforcement.py)."""
