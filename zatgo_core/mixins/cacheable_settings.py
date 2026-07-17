"""Mixin to invalidate Redis/memory cache when settings change."""

from __future__ import annotations

from zatgo_core.cache.invalidation import invalidate_settings_cache


class CacheableSettingsMixin:
    """Clear related cache keys after settings mutations."""

    def on_update(self) -> None:
        invalidate_settings_cache(self.doctype, getattr(self, "name", None))
        try:
            super().on_update()
        except AttributeError:
            pass

    def on_trash(self) -> None:
        invalidate_settings_cache(self.doctype, getattr(self, "name", None))
        try:
            super().on_trash()
        except AttributeError:
            pass
