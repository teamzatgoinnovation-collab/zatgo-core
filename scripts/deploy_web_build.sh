#!/usr/bin/env bash
# Builds flutter-vansalex's Flutter web target and deploys it into
# zatgo_core's public/vansalex (assets) and www/vansalex.html (page), so it's
# served same-origin under every ERPNext site zatgo_core is installed on
# (formerly the separate vansalex_web app)
# (fixes the browser Set-Cookie/SameSite session problem a cross-origin
# deployment hits — see session_store.dart in zatgo-dart-sdk).
#
# Cache-busting: every build goes into its own folder,
# public/vansalex/<build-id>/, and the page's <base href> points there.
# Frappe serves /assets with `max-age=43200` (12 h), so a fixed URL like
# .../vansalex/main.dart.js kept drivers on the previous build after a
# deploy; a new build-id means new URLs, so nothing stale can be used. The
# page itself is never cached (www/vansalex.py, no_cache). The current build
# and the one before it are kept (an app opened just before the deploy can
# still load its lazy files); older ones are deleted.
#
# Usage:
#   scripts/deploy_web_build.sh <flutter-vansalex-repo-path> <zatgo-core-repo-dir> <site-base-url>
#
# Example (local dev bench, app installed on site "vansale1"):
#   scripts/deploy_web_build.sh \
#     ~/ZatGoInnovation/flutter/flutter-vansalex \
#     ~/ZatGoInnovation/erpnext/zatgo-core \
#     http://vansale1:8000
#
# After running, `bench build --app zatgo_core` is NOT required — assets
# are served directly from the public/ symlink Frappe already sets up at
# `bench new-app`/`install-app` time. Copy public/vansalex/ and
# www/vansalex.html to wherever the bench's copy of this app lives (a
# container, the server), then clear the old cached page once:
# `bench --site <site> clear-website-cache` (only needed the first time a
# site gets this page — it is never cached). On Hetzner the `frontend`
# container serves /assets from its own copy: mirror public/vansalex/ to
# erpnext-frontend-1:/home/frappe/frappe-bench/assets/zatgo_core/vansalex/.
set -euo pipefail

FLUTTER_VANSALEX_DIR="${1:?Usage: deploy_web_build.sh <flutter-vansalex-repo-path> <zatgo-core-repo-dir> <site-base-url>}"
APP_DIR="${2:?Usage: deploy_web_build.sh <flutter-vansalex-repo-path> <zatgo-core-repo-dir> <site-base-url>}"
SITE_BASE_URL="${3:?Usage: deploy_web_build.sh <flutter-vansalex-repo-path> <zatgo-core-repo-dir> <site-base-url>}"

PUBLIC_DIR="$APP_DIR/zatgo_core/public/vansalex"
WWW_FILE="$APP_DIR/zatgo_core/www/vansalex.html"

# b<UTC time>-<flutter-vansalex commit>[-dirty]: unique per deploy, and says
# which code it is.
REV="$(git -C "$FLUTTER_VANSALEX_DIR" rev-parse --short HEAD 2>/dev/null || echo nogit)"
if [ -n "$(git -C "$FLUTTER_VANSALEX_DIR" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
  REV="$REV-dirty"
fi
BUILD_ID="b$(date -u +%Y%m%dT%H%M%S)-$REV"
BASE_HREF="/assets/zatgo_core/vansalex/$BUILD_ID/"

echo "==> Building flutter-vansalex web $BUILD_ID (base URL: $SITE_BASE_URL)"
(
  cd "$FLUTTER_VANSALEX_DIR"
  flutter build web \
    --dart-define=FRAPPE_BASE_URL="$SITE_BASE_URL" \
    --base-href="$BASE_HREF"
)

echo "==> Deploying assets to $PUBLIC_DIR/$BUILD_ID"
mkdir -p "$PUBLIC_DIR/$BUILD_ID"
( cd "$FLUTTER_VANSALEX_DIR/build/web" && tar --exclude=index.html -cf - . ) | ( cd "$PUBLIC_DIR/$BUILD_ID" && tar -xf - )

echo "==> Deploying page to $WWW_FILE"
mkdir -p "$(dirname "$WWW_FILE")"
cp "$FLUTTER_VANSALEX_DIR/build/web/index.html" "$WWW_FILE"
grep -q "<base href=\"$BASE_HREF\">" "$WWW_FILE" || {
  echo "!! $WWW_FILE does not carry <base href=\"$BASE_HREF\"> — refusing to clean up old builds" >&2
  exit 1
}

echo "==> Removing old builds (keeping $BUILD_ID and the previous one)"
# Unversioned files from deploys before cache-busting, and every b* folder
# except the two newest (build-ids sort chronologically).
find "$PUBLIC_DIR" -mindepth 1 -maxdepth 1 ! -name 'b*' -exec rm -rf {} +
ls -1d "$PUBLIC_DIR"/b*/ 2>/dev/null | sort | head -n -2 | xargs -r rm -rf

echo "==> Done: $BUILD_ID. Served at <site>/vansalex on every zatgo_core site."
