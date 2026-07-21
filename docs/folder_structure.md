# Folder Structure — ZatGo Core

```text
CustomApps/api/ZatGoCore/
├── README.md
├── pyproject.toml
├── setup.py
├── MANIFEST.in
├── docs/
│   ├── architecture.md
│   ├── folder_structure.md
│   ├── doctypes.md
│   ├── api.md
│   ├── permissions.md
│   ├── installation.md
│   ├── upgrade.md
│   ├── developer.md
│   ├── deployment.md
│   ├── plugin_guide.md
│   └── CHANGELOG.md
├── scripts/
│   ├── generate_doctypes.py
│   ├── fix_controllers.py
│   └── generate_reports.py
└── zatgo_core/                      # Python package / Frappe app
    ├── hooks.py
    ├── modules.txt                  # "ZatGo Core"
    ├── install.py                   # seeds + Desk leftover purge
    ├── patches.txt
    ├── api/
    │   ├── response.py
    │   ├── validators.py
    │   └── v1/                      # whitelist RPC (platform + product hubs)
    ├── services/
    ├── repositories/
    ├── cache/
    ├── validation/
    ├── permissions/
    ├── plugins/
    ├── constants/
    ├── mixins/
    ├── events/
    ├── setup/                       # roles + seed defaults (no Desk ensure)
    ├── utils/
    ├── config/
    ├── patches/
    ├── fixtures/
    ├── tests/
    └── zatgo_core/                  # nested module (modules.txt scrub)
        └── doctype/                 # platform + interim product DocTypes
```

## Why nested `zatgo_core/zatgo_core/`?

`modules.txt` contains `ZatGo Core`, which Frappe scrubs to `zatgo_core`.
When the scrubbed module name equals the app package name, DocTypes must live
under the nested package path.

## Explicitly not in this app

Desk pages, workspaces, desktop icons, script reports, number cards, and
dashboards were removed. Product Desk UI belongs in `CustomApps/erpnext/<Product>/`.
