"""Feature flag evaluation service."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.cache.manager import cache_manager
from zatgo_core.constants.settings import CACHE_KEYS, DOCTYPES
from zatgo_core.permissions.guards import assert_can_read_settings


class FeatureFlagService:
    """Resolve feature flags for runtime consumers."""

    ENABLED_STATUSES = {"Enabled", "Experimental", "Beta", "Internal"}

    @classmethod
    def get_all(cls) -> list[dict[str, Any]]:
        assert_can_read_settings("features")

        def _load() -> list[dict[str, Any]]:
            return frappe.get_all(
                DOCTYPES["FEATURE_FLAG"],
                fields=[
                    "name",
                    "flag_key",
                    "title",
                    "status",
                    "app_name",
                    "company",
                    "branch",
                    "rollout_percent",
                    "description",
                ],
                order_by="flag_key asc",
                limit_page_length=1000,
            )

        return cache_manager.get_or_set(CACHE_KEYS["FEATURE_FLAGS"], _load)

    @classmethod
    def is_enabled(
        cls,
        flag_key: str,
        *,
        company: str | None = None,
        branch: str | None = None,
    ) -> bool:
        flags = cls.get_all()
        for flag in flags:
            if flag.get("flag_key") != flag_key:
                continue
            if flag.get("company") and company and flag["company"] != company:
                continue
            if flag.get("branch") and branch and flag["branch"] != branch:
                continue
            status = flag.get("status")
            if status == "Hidden":
                return False
            if status == "Disabled":
                return False
            return status in cls.ENABLED_STATUSES
        return False
