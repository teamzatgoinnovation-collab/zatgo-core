# Folder Structure — ZatGo Core

```text
zatgo-core/                          # git repo root (the bench clones it as apps/zatgo_core)
├── README.md  CLAUDE.md  pyproject.toml  setup.py  MANIFEST.in
├── docs/                            # this folder; audit_2026-10-23.md is the 2026-10-23 audit, settings_scope.md the settings scope audit (2026-10-31)
├── scripts/                         # build_saas_theme.py, deploy_web_build.sh, self_hosted_ai/
│                                    # generate_*.py / fix_controllers.py: DESTRUCTIVE, guarded (see developer.md)
└── zatgo_core/                      # the Python package / Frappe app
    ├── hooks.py  install.py  modules.txt  patches.txt  compat_methods.py
    ├── api/
    │   ├── response.py  validators.py
    │   └── v1/                      # whitelisted RPC: app_hub, config, settings, <product>/…
    ├── services/                    # business logic. The app platform is here:
    │   ├── app_catalog.py           #   the catalog: every app's manifest, normalised
    │   ├── app_state.py             #   is app X on for this site?
    │   ├── app_gate.py              #   server-side gate: API 404, @app_api, require_app
    │   ├── app_authority.py         #   who may switch an app (System Manager)
    │   ├── app_desk.py              #   hide/show the Desk entries of in-core apps; keeps every app's rail icon hidden
    │   ├── app_page.py              #   the apps list, old-URL redirects, setup warnings
    │   ├── app_sidebar.py           #   each app's own Desk sidebar (Overview, Settings tabs, groups)
    │   ├── bundled_apps.py          #   gated hooks + set-up of the bundled modules
    │   ├── core_sidebar.py          #   the generated "ZatGo" sidebar
    │   └── ui_apps.py               #   SaaS theme, language switcher, VanSaleX web page
    ├── repositories/  cache/  validation/  permissions/  mixins/  constants/  utils/  events/  overrides/
    ├── plugins/                     # config-center registry: discover.py, manifests/ (core_apps.py = catalog core entries)
    ├── industries/                  # industry registry + gate (restaurant, gym, jewellery, textile, …)
    ├── setup/                       # idempotent ensure_* run on install/migrate
    ├── patches/                     # v0_x_y/ data patches (schema fields come from DocType JSON / ensure_custom_fields)
    ├── chat_ai/  tracker/  zatgo_space/   # bundled modules; each has app_manifest.py, install.py::bootstrap, desk_records/
    ├── public/                      # JS/CSS: saas_theme/, chat_ai/, tracker/, language_switcher/, js/, css/
    ├── templates/  www/  translations/  print_formats/  config/  workflow/
    ├── tests/                       # unit/ (no site), integration/ (needs a site), api/, permissions/
    └── zatgo_core/                  # the "ZatGo Core" module (modules.txt scrubs to zatgo_core)
        ├── doctype/                 # 45 DocTypes (ZG …, VanSaleX Settings/Access)
        ├── page/zg_app_hub/         # Desk page "ZatGo Apps"
        ├── report/  workspace/      # workspaces: zatgo, zatgo_vansalex
```

## Why nested `zatgo_core/zatgo_core/`?

`modules.txt` contains `ZatGo Core`, which Frappe scrubs to `zatgo_core`. When the scrubbed module name equals
the app package name, DocTypes, pages and workspaces live under the nested package path. The bundled modules
(`Chat AI`, `Tracker`, `ZatGo Space`) are separate module folders next to it.

## Desk records

Workspaces and pages inside `zatgo_core/zatgo_core/` are synced by migrate onto **every** site. The bundled
modules keep theirs in `<module>/desk_records/` instead, imported only where the module is switched on.
