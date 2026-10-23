# Naming standard — ZatGo Core

User-facing, the product is **ZatGo**. The backend package is `zatgo_core` and stays that way: it is the
Python import path, the `bench` app name and the prefix of every API method path, so renaming it would break
every client and hook. Users should not meet "zatgo_core" in Desk — see *Branding* below.

| Thing | Standard | Examples |
|---|---|---|
| User-facing product / app title | `ZatGo` | Desk app title, page titles, messages |
| Backend package | `zatgo_core` (never renamed) | `bench --site X install-app zatgo_core` |
| **New DocTypes** | `ZG <Name>` — prefix, never suffix | `ZG System Settings`, `ZG Metal Rate` |
| Custom fields on ERPNext DocTypes | `zg_<name>` | `zg_vansalex_selectable` |
| Roles ZatGo creates | `ZG <Role>` | `ZG Company Admin` |
| Desk workspace / rail icon of an app | `ZatGo <App>` | `ZatGo VanSaleX`, `ZatGo AI`, `ZatGo Tracker` |
| Whitelisted API methods | `zatgo_core.api.v1.<product>.<module>.<fn>` | `zatgo_core.api.v1.vansalex.me.context` |
| App switch (ZG System Settings Check field) | `enable_<app key>` | `enable_vansalex` |
| Python modules / functions | `snake_case`; settings access via `services/` | `services/app_state.py` |
| Patches | `patches/v<major>_<minor>_<patch>/<verb>_<what>.py`, listed in `patches.txt` | `v0_4_7/enable_vansalex_default_on.py` |

## DocTypes

- **A new DocType is `ZG <Name>`.** `tests/unit/test_naming_standard.py` fails on any DocType the package ships
  that does not start with `ZG ` — and on any name containing "ZatGo" (the retired convention was
  `<Name> ZatGo`; none are left).
- **Legacy names are kept.** 25 DocTypes predate the standard — the modules merged in on 2026-10-08 came with
  their own names, and `VanSaleX Settings` is older than the prefix:
  `VanSaleX Settings`, `VanSaleX Access`; `Chat AI Settings` and the 15 `AI …`; `Tracker Settings`,
  `Tracker Activity Session`; `Space Settings`, `Space Plan`, `Space Order`, `Space Order App`, `Space Job Log`.
  They are listed in `LEGACY_NON_ZG` in that test and are **not** renamed: a rename moves table names, hook
  keys (Chat AI's per-user privacy scoping is keyed by DocType name), raw SQL, workspaces, permissions and
  stored secrets. If one is ever renamed (a `[pre_model_sync]` patch using `frappe.rename_doc`, with the hooks,
  `OWNER_FIELD`, SQL, desk records, JS routes and tests changed in the same release), remove it from the list —
  the test also fails on an entry that no longer exists.
- Why a prefix at all: it keeps ZatGo's DocTypes from colliding with Frappe/ERPNext built-ins (`System
  Settings`) and shows ownership in Desk search.

## Custom fields

Existing fields are not renamed — they are part of the schema and, for `zatgo_client_id`, of the client wire
protocol. They carry several historical prefixes (`zatgo_*`, `custom_*`, `custom_zg_*`, `zg_*`, `vansale_*`,
`zatca_*`). New ones use `zg_<name>`, are created by `setup/ensure_custom_fields.py` (so a migrate that
"recorded" a patch but never materialised the column cannot hide them — see `.claude/rules/accounting.md`),
and get a patch only for data.

## Branding — what the user sees

- Desk app title is `ZatGo` (`hooks.py: app_title`). The Module Def is still called "ZatGo Core" because its name
  maps to the package folder `zatgo_core/zatgo_core/`; renaming it would move every DocType's module path for a
  label. It appears only in module lists.
- Messages, buttons, help text and toasts say "ZatGo", never "zatgo_core". An instruction to an admin says
  "run bench migrate", not "migrate zatgo_core".
- Internal identifiers keep the package name: log/Error Log titles, API payload `app` fields, the `app:
  "zatgo_core"` tag on Desk records, import paths.
- Desk routes are `/desk/…` (Frappe v16).

## Apps

An app registers with a manifest (`<module>/app_manifest.py`, or an entry in `plugins/manifests/core_apps.py`);
see `plugin_guide.md`. Its key is `snake_case`, its label carries the `ZatGo` prefix (`ZatGo Tracker`), and its
switch field is `enable_<key>` unless it names another.
