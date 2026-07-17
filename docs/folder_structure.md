# Folder Structure — ZatGo Core

```text
CustomApps/ZatGoCore/
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
│   └── CHANGELOG.md
├── scripts/
│   ├── generate_doctypes.py
│   ├── fix_controllers.py
│   └── generate_reports.py
└── zatgo_core/                      # Python package / Frappe app
    ├── hooks.py
    ├── modules.txt                  # "ZatGo Core"
    ├── install.py
    ├── patches.txt
    ├── api/
    │   ├── response.py
    │   ├── validators.py
    │   └── v1/
    │       ├── settings.py
    │       ├── features.py
    │       ├── apps.py
    │       ├── integrations.py
    │       └── health.py
    ├── services/
    ├── repositories/
    ├── cache/
    ├── validation/
    ├── permissions/
    ├── constants/
    ├── mixins/
    ├── events/
    ├── setup/
    ├── utils/
    ├── config/
    ├── patches/
    ├── public/js|css/
    ├── number_card/
    ├── dashboard/
    ├── dashboard_chart/
    ├── fixtures/
    ├── tests/
    └── zatgo_core/                  # nested module (modules.txt scrub)
        ├── doctype/
        ├── workspace/core_administration/
        ├── report/
        ├── number_card/
        ├── dashboard/
        └── dashboard_chart/
```

## Why nested `zatgo_core/zatgo_core/`?

`modules.txt` contains `ZatGo Core`, which Frappe scrubs to `zatgo_core`.
When the scrubbed module name equals the app package name, DocTypes / Workspace /
Reports must live under the nested package path.
