# API Reference — ZatGo Core

All endpoints return the standard envelope from `zatgo_core.api.response`:

```json
{
  "success": true,
  "data": {},
  "meta": {},
  "error": null,
  "request_id": "uuid"
}
```

Base path: `/api/method/<dotted.path>`

## Settings

| Method | Args | Description |
|--------|------|-------------|
| `zatgo_core.api.v1.settings.get_system_settings` | — | Global settings |
| `zatgo_core.api.v1.settings.get_company_settings` | `company` | Company settings |
| `zatgo_core.api.v1.settings.get_branch_settings` | `branch` | Branch settings name |
| `zatgo_core.api.v1.settings.get_user_preferences` | `user?` | User preferences |
| `zatgo_core.api.v1.settings.save_settings` | `doctype`, `values`, `name?`, `category?` | Persist settings |
| `zatgo_core.api.v1.settings.reload_settings` | `doctype?` | Reload + clear related cache |
| `zatgo_core.api.v1.settings.clear_cache` | — | Flush all core caches |

## Features

| Method | Args | Description |
|--------|------|-------------|
| `zatgo_core.api.v1.features.get_feature_flags` | — | List all flags |
| `zatgo_core.api.v1.features.is_feature_enabled` | `flag_key`, `company?`, `branch?` | Evaluate one flag |

## Applications

| Method | Args | Description |
|--------|------|-------------|
| `zatgo_core.api.v1.apps.get_application_settings` | — | Site application settings (Single) |
| `zatgo_core.api.v1.apps.get_application_registry` | — | Client app rows for this site |
| `zatgo_core.api.v1.apps.get_client_app` | `app_key` | One client config |
| `zatgo_core.api.v1.apps.is_client_enabled` | `app_key` | Whether client may run |
| `zatgo_core.api.v1.apps.seed_default_client_apps` | `replace?` | Seed Electron/Flutter/Web defaults |

## Integrations / printers

| Method | Description |
|--------|-------------|
| `zatgo_core.api.v1.integrations.get_integrations` | Integration settings |
| `zatgo_core.api.v1.integrations.get_printers` | Printer settings |

## Health / catalog

| Method | Description |
|--------|-------------|
| `zatgo_core.api.v1.health.ping` | Liveness (guest allowed); returns app version |
| `zatgo_core.api.v1.health.catalog` | Product API catalog |
| `zatgo_core.api.v1.health.status` | Hub + installed products |
| `zatgo_core.api.v1.health.get_system_health` | Redis, queues, users online, counts |

### Catalog `status` values

| Status | Meaning |
|--------|---------|
| `active` | Full domain workflows (delivery stops/boys/tracking, resto_pos catalog + KDS) |
| `thin` | ERPNext- or ZG-backed list/get (+ ping/status); safe for client wiring |
| `stub` | Placeholder helpers only |

### Devices (FCM / push)

| Method | Args | Description |
|--------|------|-------------|
| `zatgo_core.api.v1.devices.register_token` | `token`, `platform?`, `app_key?` | Register device token for user |
| `zatgo_core.api.v1.devices.unregister_token` | `token` | Remove device token |
| `zatgo_core.api.v1.devices.send_to_user` | `user`, `title`, `body`, … | Send push to user's devices |

## Configuration center (plugin registry)

| Method | Args | Description |
|--------|------|-------------|
| `zatgo_core.api.v1.config.get_dashboard` | — | Installed/enabled/pending + health |
| `zatgo_core.api.v1.config.get_applications` | — | Apps visible to current user |
| `zatgo_core.api.v1.config.get_application` | `app_key` | App + section tree |
| `zatgo_core.api.v1.config.register_application` | `manifest` | Upsert plugin manifest |
| `zatgo_core.api.v1.config.seed_bundled_manifests` | — | Re-seed POS/Delivery/Kitchen |
| `zatgo_core.api.v1.config.get_settings` | `app_key`, `section_key` | Load section payload |
| `zatgo_core.api.v1.config.update_settings` | `app_key`, `section_key`, `values` | Save section |
| `zatgo_core.api.v1.config.reset_settings` | `app_key`, `section_key` | Reset to defaults |
| `zatgo_core.api.v1.config.export_settings` | `profile_name?` | Export JSON |
| `zatgo_core.api.v1.config.import_settings` | `payload` | Import JSON |
| `zatgo_core.api.v1.config.validate_configuration` | `app_key` | Pending / missing checks |
| `zatgo_core.api.v1.config.search_settings` | `query` | Cross-app section search |

Config is API-only (no Desk page). Call the methods above from clients or `bench execute`.

## Product clients (former zatgo_api)

Pattern: `zatgo_core.api.v1.<product>.<module>.<method>`

Examples:

| Method | Description |
|--------|-------------|
| `zatgo_core.api.v1.delivery.stops.list` | Delivery stops |
| `zatgo_core.api.v1.delivery.stops.create` | Create stop (POS → Assigned) |
| `zatgo_core.api.v1.delivery.stops.assign` | Assign / reassign boy |
| `zatgo_core.api.v1.delivery.stops.update` | Driver status + POD + payment |
| `zatgo_core.api.v1.delivery.stops.accept` | Assigned → Accepted |
| `zatgo_core.api.v1.delivery.stops.reject` | Assigned → Rejected |
| `zatgo_core.api.v1.delivery.stops.reach_restaurant` | → Reached Restaurant |
| `zatgo_core.api.v1.delivery.stops.pickup` | → Picked Up |
| `zatgo_core.api.v1.delivery.stops.start_delivery` | → Out For Delivery |
| `zatgo_core.api.v1.delivery.stops.complete_delivery` | → Delivered (+10 pts) |
| `zatgo_core.api.v1.delivery.stops.fail_delivery` | → Failed |
| `zatgo_core.api.v1.delivery.tracking.ping` | Save courier GPS |
| `zatgo_core.api.v1.delivery.tracking.me` | Points / bonus / last location |
| `zatgo_core.api.v1.delivery.boys.ensure` | Resolve boy for session user |
| `zatgo_core.api.v1.resto_pos.catalog.list` | POS catalog |
| `zatgo_core.api.v1.resto_pos.kds_tickets.list` | Kitchen tickets |
| `zatgo_core.api.v1.go_van.trips.list` | Go Van trips |

### Accounting (AR/AP)

| Method | Args | Description |
|--------|------|-------------|
| `zatgo_core.api.v1.accounting.health.ping` | — | Liveness |
| `zatgo_core.api.v1.accounting.dashboard.summary` | — | AR/AP open, overdue, recent |
| `zatgo_core.api.v1.accounting.customers.list/get/create/update` | party fields | Customers |
| `zatgo_core.api.v1.accounting.suppliers.list/get/create/update` | party fields | Suppliers |
| `zatgo_core.api.v1.accounting.invoices.list/get/create/submit` | customer, items | Sales Invoice |
| `zatgo_core.api.v1.accounting.purchase_invoices.list/get/create/submit` | supplier, items | Purchase Invoice |
| `zatgo_core.api.v1.accounting.payments.list/get/create_receive/create_pay/submit` | invoice refs | Payment Entry |
| `zatgo_core.api.v1.accounting.journals.list/get/create/submit` | accounts lines | Journal Entry |
| `zatgo_core.api.v1.accounting.reports.outstanding_receivable` | page? | Open AR |
| `zatgo_core.api.v1.accounting.reports.outstanding_payable` | page? | Open AP |
| `zatgo_core.api.v1.accounting.reports.general_ledger` | from_date?, to_date?, account? | GL lines |
| `zatgo_core.api.v1.accounting.reports.profit_and_loss` | from_date?, to_date? | Income vs expense |

Products: `delivery`, `resto_pos`, `go_van`, `service`, `warehouse`, `crm`, `hr`, `fleet`, `accounting`, `admin`, `bi`, `customer_portal`, `vendor_portal`, `documentation`.

## Client helper

Desk JS (`zatgo_core.js`) exposes `zatgo.core.getSystemSettings()`,
`zatgo.core.isFeatureEnabled(key)`, `zatgo.core.clearCache()`, `zatgo.core.syncApps()`.

## Boot payload

`boot_session` injects `frappe.boot.zatgo_core` with:

- `system` — brand, theme, default company, maintenance mode
- `feature_flags` — enabled-like flags
- `version`
