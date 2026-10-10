Desk UI assets ship via Frappe `public/` (no Vite/Node build):

- `chat_ai/public/js/vendor/vue.global.prod.js` — Vue 3
- `chat_ai/public/js/chat_ai_vue.js` — `chat_ai.vue.ensure` / `mount`
- `chat_ai/public/js/chat_ai_sidebar_app.js` — Vue slide-out
- `chat_ai/public/css/chat_ai_sidebar.css`

Wired in `hooks.py` as `app_include_js` / `app_include_css`.

On frappe_docker, run `deploy/sync_frontend_assets.sh` after pull so nginx can serve `/assets/zatgo_core/chat_ai/*`.
