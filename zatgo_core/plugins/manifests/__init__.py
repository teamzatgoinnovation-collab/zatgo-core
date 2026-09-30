"""Bundled manifests (POS, Delivery, Kitchen, VanSaleX)."""

from __future__ import annotations

from zatgo_core.plugins.manifests.delivery import MANIFEST as DELIVERY
from zatgo_core.plugins.manifests.kitchen import MANIFEST as KITCHEN
from zatgo_core.plugins.manifests.vansalex import MANIFEST as VANSALEX
from zatgo_core.plugins.manifests.zatgo_pos import MANIFEST as ZATGO_POS

BUNDLED_MANIFESTS = (ZATGO_POS, DELIVERY, KITCHEN, VANSALEX)

__all__ = ["BUNDLED_MANIFESTS", "ZATGO_POS", "DELIVERY", "KITCHEN", "VANSALEX"]
