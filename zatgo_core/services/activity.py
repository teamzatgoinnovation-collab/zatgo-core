"""Last meaningful HUMAN activity on this site -- read by the platform's inactivity clock (Space lifecycle).

Counts: a successful login, a live session's last request, and a document change by a real user. Does not count
(by construction, not by a filter list): health checks and monitors (no session, no login), API-key / bot users,
the scheduler and background jobs (they run as Administrator and never log in; their document changes are
excluded by leaving Administrator out of the Version query -- but an Administrator *login* or *session* is a
person, since the customer's own admin is called Administrator), and system maintenance.

Returns an ISO-8601 UTC string, or None when nothing was ever recorded. A site that cannot answer must be read as
"unknown" by the caller, never as "inactive".
"""

from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

import frappe

_HUMAN = "u.enabled = 1 AND u.name != 'Guest' AND IFNULL(u.api_key, '') = ''"

QUERY = f"""
SELECT MAX(t) FROM (
	SELECT MAX(a.creation) AS t FROM `tabActivity Log` a JOIN `tabUser` u ON u.name = a.user
		WHERE a.operation = 'Login' AND a.status = 'Success' AND {_HUMAN}
	UNION ALL
	SELECT MAX(s.lastupdate) FROM `tabSessions` s JOIN `tabUser` u ON u.name = s.user WHERE {_HUMAN}
	UNION ALL
	SELECT MAX(v.creation) FROM `tabVersion` v JOIN `tabUser` u ON u.name = v.owner
		WHERE {_HUMAN} AND u.name != 'Administrator' AND u.user_type = 'System User'
) x
"""


def last_human_activity() -> str | None:
    row = frappe.db.sql(QUERY)
    value = row[0][0] if row and row[0] else None
    if value is None:
        return None
    zone = ZoneInfo(frappe.utils.get_system_timezone() or "UTC")
    return value.replace(tzinfo=zone).astimezone(timezone.utc).isoformat()
