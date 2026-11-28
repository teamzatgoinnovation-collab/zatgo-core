"""Licence events in Audit Log (brief Part 17): imported, replaced, verification failed, revoked, issued.

One row per event: `doctype_name` = the DocType concerned, `fieldname` = the event, `new_value` = a JSON
summary. Never a key, never a whole licence file -- ids, numbers, hashes and reasons only.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from zatgo_core.services.core import audit


def log(event: str, doctype: str, name: str | None, details: Mapping[str, Any], reason: str = "",
        durable: bool = False) -> None:
    """`durable`: the caller is about to raise, and Frappe rolls the request back on an error -- commit this row
    on its own so a refused import is still on record (only inside a web request; never in tests or jobs)."""
    audit.record(doctype, name, event, None, json.dumps(dict(details), sort_keys=True, default=str),
                 reason=reason, durable=durable)
