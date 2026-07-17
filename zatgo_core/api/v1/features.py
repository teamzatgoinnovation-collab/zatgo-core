"""Feature flag APIs."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.services.feature_flag_service import FeatureFlagService
from zatgo_core.utils.logging import log_api


@frappe.whitelist()
def get_feature_flags() -> dict[str, Any]:
    """Return all feature flags."""
    log_api("get_feature_flags", user=frappe.session.user)
    return ok(FeatureFlagService.get_all())


@frappe.whitelist()
def is_feature_enabled(
    flag_key: str,
    company: str | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    """Evaluate a single feature flag."""
    log_api("is_feature_enabled", user=frappe.session.user, flag_key=flag_key)
    return ok(
        {
            "flag_key": flag_key,
            "enabled": FeatureFlagService.is_enabled(
                flag_key, company=company, branch=branch
            ),
        }
    )
