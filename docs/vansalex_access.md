# VanSaleX modules & features (per-client control)

One VanSaleX app build serves every client. Each client is its own ERPNext
site, and **that site's `VanSaleX Settings` decides what its drivers get**:
the app shows only what the site enables, and the server rejects the rest.

```
VanSaleX app ──me.context──▶ zatgo_core (control plane) ──▶ ERPNext (books, stock)
              ◀── access ───  VanSaleX Settings → Modules & Features
                               ZG Van Sale Profile → switch-offs per user
```

Code: `zatgo_core/services/vansalex_access.py` (catalog, evaluation,
enforcement), `setup/ensure_vansalex_access.py` (migration seeding).
Tests: `zatgo_core/tests/integration/test_vansalex_module_access.py`.
App side: `flutter-vansalex` `lib/core/access/feature_registry.dart`.

## Keys

Stable machine identifiers (never page titles).

| Key | Kind | Controls |
|-----|------|----------|
| `dashboard` | module | Dashboard |
| `sales_invoice` | module | Invoice create/list/print, Documents |
| `sales_order` | module | Order (invoice later) + Convert to Invoice — **= `allow_orders`** |
| `sales_return` | module | Sales Returns (credit notes) |
| `collections` | module | Customer payments |
| `customers` | module | Browse / create / edit customers (the customer picker on a sale stays) |
| `products` | module | Browse / create / edit products (the product picker on a sale stays) |
| `route_plan` | module | More → Plan & Route (trips/visits) |
| `reports` | module | More → Reports, Aging |
| `activities` | module | More → Activities |
| `documents` | module | More → Documents (list + print) |
| `my_performance` | module | More → My Performance |
| `inventory` | module | Van stock |
| `sales_invoice.print_a4` | feature | A4 printing (invoices & credit notes) |
| `sales_invoice.print_80mm` | feature | 80mm thermal printing (invoices & credit notes) |
| `sales_invoice.multiple_payment_modes` | feature | Split an invoice's payment across methods |
| `sales_invoice.multiple_payment_accounts` | feature | Pay into an account other than the method's default |
| `sales_invoice.credit_sale` | feature | **= Allow Credit Sales** (settings + profile override) |
| `sales_invoice.discount` | feature | Discount % on the whole invoice (capped by Max Discount %; off while it is 0) |
| `sales_invoice.line_discount` | feature | Disc % on each item line (capped by Max Discount %; off while it is 0); shown on the invoice line as ERPNext's own line discount |
| `sales_invoice.edit_rate` | feature | Typed rate on each line; without it the server refuses a rate other than the item's price |
| `sales_invoice.change_warehouse` | feature | **= Allow Changing Warehouse** (settings + profile override) |
| `collections.card` | feature | Collect by a non-cash Mode of Payment (type ≠ Cash) |
| `collections.multiple_payment_modes` | feature | Split a collection across methods |

Each row in VanSaleX Settings shows **Where in the app** it applies, and rows
follow the app's order (every More-tab entry has its own row). Activities,
Documents and My Performance were split out of Plan & Route, Sales Invoice
and Reports on 2026-10-07; an app or server from before that treats them as
part of the module they came from.

**Bold** keys are *derived*: they mirror an existing VanSaleX setting, so
there is still exactly one place to change them; they have no row in the
Modules & Features table. Settings and Logout are always available.

## Evaluation

```
effective(key) = client on   (row in VanSaleX Settings, or the derived setting)
             AND not switched off on the user's ZG Van Sale Profile
             AND parent module on          (features only)
```

A profile can only take away, never add. Delivered to the app in
`vansalex.me.context` → `access`:

```json
"access": {
  "modules":  {"sales_invoice": true, "customers": false, ...},
  "features": {"sales_invoice.print_80mm": true, ...},
  "config_version": 3
}
```

`config_version` (on VanSaleX Settings) goes up each time a switch changes.

## Security model

Hiding a screen in the app is not the control:

1. **API layer** — every `zatgo_core.api.v1.vansalex.*` endpoint calls
   `require(...)` before doing anything; it binds every caller, admins
   included (it is the client's licence). Read-only lists the dashboard also
   uses (`orders.list`, `returns.list`, `collections.list`, `stock.list`,
   `trips.list`, `aging.*`) accept `dashboard` too. `orders.pdf` checks the
   paper feature (80mm format vs anything else = A4). Split payments, account
   choice and card collections are checked where the payment rows are parsed
   (`services/vansalex_service.py`).
2. **DocType backstop** — `check_doc_access` in `doc_events`: Sales Invoice /
   return, Sales Order, Payment Entry (Receive) `before_insert`, Customer /
   Item `before_save`. Applies to **field users** (enabled ZG Van Sale
   Profile, type Field User) on any entry point — `/api/resource`, the shared
   `accounting.customers.*` / `warehouse.items.*` endpoints, Desk. A Cash
   invoice's own auto Payment Entry is part of the sale and passes
   (`flags.zatgo_auto_cash_payment`).

Nothing is cached on the device, so there is nothing to tamper with; a
modified app still hits both layers.

## Migration of existing clients

`after_migrate` → `ensure_vansalex_access()` only **adds** rows for keys a
site doesn't have, using the catalog default, and never changes an existing
row. Everything VanSaleX did before this existed defaults **on**, so an
upgraded site keeps all its functionality. Keys added in future default
**off** (fail-closed) unless their catalog entry says otherwise.

## Admin how-to

**Sales Invoice-only client** — ERPNext → VanSaleX Settings → Modules &
Features: tick `Sales Invoice`, and the print/payment features wanted; untick
every other module; untick *Allow Orders* above. Save. Drivers see the change
on their next app launch or dashboard refresh — no new app build.

**Enable more modules** — tick them in the same table.

**One driver gets less** — their ZG Van Sale Profile → Modules & Features:
add a row per key to switch off.

Every change is in the document's Version history (who, when, old → new).

## Adding a new key

1. Add it to `CATALOG` in `services/vansalex_access.py` (default `0` for new
   functionality) and to the `ZG Van Sale Profile Access.access_key` options.
2. Gate the endpoint(s) with `require(...)`; add a DocType backstop branch if
   it creates documents.
3. Mirror the key in the app's `feature_registry.dart` and gate the UI.
4. `bench migrate` seeds the row on every site.
