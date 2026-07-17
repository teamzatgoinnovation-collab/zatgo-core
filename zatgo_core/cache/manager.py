"""Redis + in-process cache manager."""

from __future__ import annotations

from typing import Any, Callable

import frappe

from zatgo_core.constants.settings import CACHE_TTL_SECONDS


class CacheManager:
    """Thin wrapper around frappe.cache with typed helpers."""

    def __init__(self, namespace: str = "zg_core") -> None:
        self.namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> Any:
        return frappe.cache().get_value(self._key(key))

    def set(self, key: str, value: Any, expires_in_sec: int = CACHE_TTL_SECONDS) -> None:
        frappe.cache().set_value(self._key(key), value, expires_in_sec=expires_in_sec)

    def delete(self, key: str) -> None:
        frappe.cache().delete_value(self._key(key))

    def get_or_set(
        self,
        key: str,
        producer: Callable[[], Any],
        expires_in_sec: int = CACHE_TTL_SECONDS,
    ) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        self.set(key, value, expires_in_sec=expires_in_sec)
        return value

    def delete_keys(self, *keys: str) -> None:
        for key in keys:
            self.delete(key)


cache_manager = CacheManager()
