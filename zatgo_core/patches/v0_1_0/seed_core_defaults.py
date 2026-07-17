"""Ensure singletons and defaults after model sync."""

from __future__ import annotations

from zatgo_core.setup.ensure_roles import ensure_roles
from zatgo_core.setup.seed_defaults import (
    seed_feature_flags,
    seed_number_series,
    seed_singletons,
)


def execute() -> None:
    ensure_roles()
    seed_singletons()
    seed_number_series()
    seed_feature_flags()
