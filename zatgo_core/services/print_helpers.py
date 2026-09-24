"""Small print-format Jinja helpers that need a real Python import to be
reachable -- `frappe.contacts.doctype.address.address` isn't auto-loaded
onto the `frappe` module object the way `frappe.db`/`frappe.utils` are, so
referencing it as a dotted path directly from a Jinja template fails with
`AttributeError: module 'frappe' has no attribute 'contacts'` unless
something else already happened to import it first in that same request.
"""

from __future__ import annotations

from frappe.contacts.doctype.address.address import get_default_address


def get_party_default_address(party_type: str, party: str | None) -> str | None:
    if not party:
        return None
    return get_default_address(party_type, party)
