"""Validation for ZG Integration Settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from frappe.model.document import Document


def validate_integration_settings(doc: Document) -> None:
    """Require credentials when a provider is enabled."""
    checks = (
        ("whatsapp_enabled", "whatsapp_api_key", "WhatsApp API Key"),
        ("sms_enabled", "sms_api_key", "SMS API Key"),
        ("firebase_enabled", "firebase_project_id", "Firebase Project ID"),
        ("telegram_enabled", "telegram_bot_token", "Telegram Bot Token"),
        ("slack_enabled", "slack_webhook_url", "Slack Webhook URL"),
        ("google_maps_enabled", "google_maps_api_key", "Google Maps API Key"),
        ("openai_enabled", "openai_api_key", "OpenAI API Key"),
        ("gemini_enabled", "gemini_api_key", "Gemini API Key"),
        ("claude_enabled", "claude_api_key", "Claude API Key"),
        ("deepseek_enabled", "deepseek_api_key", "DeepSeek API Key"),
        ("jwt_enabled", "jwt_secret", "JWT Secret"),
    )
    for enabled_field, credential_field, label in checks:
        if doc.get(enabled_field) and not doc.get(credential_field):
            frappe.throw(frappe._("{0} is required when the integration is enabled").format(label))
