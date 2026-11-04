"""Where a MyBis notification lands: a Notification Log row (the bell in Desk and the Alerts tab of the app) and, when asked, e-mail.

Push (FCM) is not wired here: `api/v1/devices.send_to_user` only lets a user notify themselves, and these are sent by the system
on someone else's action. The same row is what a push channel would carry later.
"""

from __future__ import annotations

from typing import Any

import frappe

# Notification Log subjects of MyBis start with this, which is how the app tells its own rows from the rest of the bell.
TAG = "MyBis · "


def notify(user: str, subject: str, body: str, doctype: str | None = None, name: str | None = None) -> bool:
    """Write one Notification Log row for `user`; False when it could not (never raises: a notification is never worth a failure)."""
    try:
        frappe.get_doc(
            {
                "doctype": "Notification Log",
                "subject": TAG + subject,
                "email_content": body,
                "for_user": user,
                "type": "Alert",
                "document_type": doctype,
                "document_name": name,
                "from_user": frappe.session.user,
            }
        ).insert(ignore_permissions=True)
        return True
    except Exception:
        frappe.log_error(title="MyBis notification failed", message=frappe.get_traceback())
        return False


def already_sent(user: str, subject: str) -> bool:
    return bool(frappe.db.exists("Notification Log", {"for_user": user, "subject": TAG + subject}))


def email(user: str, subject: str, html: str) -> None:
    try:
        frappe.sendmail(recipients=[user], subject=TAG + subject, message=html, delayed=True)
    except Exception:
        frappe.log_error(title="MyBis e-mail failed", message=frappe.get_traceback())


def mine(limit: int = 30) -> list[dict[str, Any]]:
    """The caller's MyBis notifications, newest first."""
    return frappe.get_all(
        "Notification Log",
        filters={"for_user": frappe.session.user, "subject": ("like", TAG + "%")},
        fields=["name", "subject", "email_content", "document_type", "document_name", "read", "creation"],
        order_by="creation desc",
        limit_page_length=max(1, min(int(limit), 100)),
    )
