"""Bundled Phase-1 manifests (POS, Delivery, Kitchen)."""

from __future__ import annotations

from zatgo_core.plugins.manifests.delivery import MANIFEST as DELIVERY
from zatgo_core.plugins.manifests.kitchen import MANIFEST as KITCHEN
from zatgo_core.plugins.manifests.zatgo_pos import MANIFEST as ZATGO_POS

BUNDLED_MANIFESTS = (ZATGO_POS, DELIVERY, KITCHEN)

__all__ = ["BUNDLED_MANIFESTS", "ZATGO_POS", "DELIVERY", "KITCHEN"]
