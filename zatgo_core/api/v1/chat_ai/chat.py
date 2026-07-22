"""Chat AI session / message APIs — proxy to chat_ai.api.chat.*."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import fail, ok
from zatgo_core.api.validators import require_login


def _ensure_chat_ai() -> dict[str, Any] | None:
    if "chat_ai" not in frappe.get_installed_apps():
        return fail(
            "CHAT_AI_MISSING",
            "chat_ai app is not installed on this site",
        )
    return None


def _wrap(result: Any) -> dict[str, Any]:
    """Convert chat_ai {ok, data|error} into zatgo_core envelope."""
    if not isinstance(result, dict):
        return ok(result)
    if result.get("ok") is True:
        return ok(result.get("data"), meta={k: v for k, v in result.items() if k not in ("ok", "data", "error")})
    error = result.get("error") or "Chat AI request failed"
    if isinstance(error, dict):
        return fail(
            str(error.get("code") or "CHAT_AI_ERROR"),
            str(error.get("message") or error),
            details=error.get("details"),
        )
    return fail("CHAT_AI_ERROR", str(error))


def _call(fn_name: str, **kwargs: Any) -> dict[str, Any]:
    require_login()
    missing = _ensure_chat_ai()
    if missing:
        return missing
    from chat_ai.api import chat as chat_api

    fn = getattr(chat_api, fn_name)
    try:
        return _wrap(fn(**kwargs))
    except frappe.PermissionError:
        raise
    except Exception as exc:
        frappe.log_error(title=f"zatgo_core.chat_ai.{fn_name}")
        return fail("CHAT_AI_ERROR", str(exc))


@frappe.whitelist()
def send(
    session=None,
    message=None,
    client_context=None,
    command=None,
    confirmed=None,
    pending_tool=None,
    pending_args=None,
    plan_confirmed=None,
    confirmation_token=None,
    execution_mode=None,
) -> dict[str, Any]:
    return _call(
        "send",
        session=session,
        message=message,
        client_context=client_context,
        command=command,
        confirmed=confirmed,
        pending_tool=pending_tool,
        pending_args=pending_args,
        plan_confirmed=plan_confirmed,
        confirmation_token=confirmation_token,
        execution_mode=execution_mode,
    )


@frappe.whitelist()
def new_session(title=None, assistant_mode=None, language=None) -> dict[str, Any]:
    return _call(
        "new_session",
        title=title,
        assistant_mode=assistant_mode,
        language=language,
    )


@frappe.whitelist()
def list_sessions(status="Active") -> dict[str, Any]:
    return _call("list_sessions", status=status)


@frappe.whitelist()
def history(session=None, limit=50) -> dict[str, Any]:
    return _call("history", session=session, limit=limit)


@frappe.whitelist()
def set_language(session=None, language=None) -> dict[str, Any]:
    return _call("set_language", session=session, language=language)


@frappe.whitelist()
def set_mode(session=None, assistant_mode=None) -> dict[str, Any]:
    return _call("set_mode", session=session, assistant_mode=assistant_mode)


@frappe.whitelist()
def get_ui_locale() -> dict[str, Any]:
    return _call("get_ui_locale")


@frappe.whitelist()
def rename(session=None, title=None) -> dict[str, Any]:
    return _call("rename", session=session, title=title)


@frappe.whitelist()
def archive(session=None) -> dict[str, Any]:
    return _call("archive", session=session)


@frappe.whitelist()
def delete_session(session=None) -> dict[str, Any]:
    return _call("delete_session", session=session)


@frappe.whitelist()
def clear(session=None) -> dict[str, Any]:
    return _call("clear", session=session)


@frappe.whitelist()
def cancel(session=None) -> dict[str, Any]:
    return _call("cancel", session=session)
