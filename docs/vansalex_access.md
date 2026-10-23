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
Tests: `zatgo_core/tests/integration/test_vansalex_module_access.py` (switches), `test_vansalex_stock_scope.py` (stock / money limits).
App side: `flutter-vansalex` `lib/core/access/feature_registry.dart`.

## Keys

Stable machine identifiers (never page titles).

| Key | Kind | Controls |
|-----|------|----------|
| `dashboard` | module | Dashboard |
| `sales_invoice` | module | Invoice create/list/print, Documents |
| `sales_order` | module | Order (invoice later) + Convert to Invoice — **= `allow_orders`** |
| `purchase_invoice` | module | More → Purchases: New Purchase Invoice (stock received into the van warehouse) and the purchase list. **Default off** |
| `purchase_order` | module | More → Purchases: New Purchase Order + Convert to Invoice. **Default off** |
| `purchase_return` | module | More → Purchase Returns: a debit note against a purchase (stock goes back out of the warehouse it was received into). **Default off** |
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
| `sales_invoice.multiple_payment_accounts` | feature | Pay into an account other than the default: the Cash / Bank account of a Cash / Bank sale, and the account of each split-payment row |
| `sales_invoice.credit_sale` | feature | **= Allow Credit Sales** (settings + profile override) |
| `sales_invoice.bank_payment` | feature | **= Allow Bank Payment** (settings + profile override): Bank beside Cash / Credit on New Invoice and Convert to Invoice |
| `sales_invoice.discount` | feature | Discount % on the whole invoice (capped by Max Discount %; off while it is 0) |
| `sales_invoice.line_discount` | feature | Disc % on each item line (capped by Max Discount %; off while it is 0); shown on the invoice line as ERPNext's own line discount |
| `sales_invoice.edit_rate` | feature | Typed rate on each line; without it the server refuses a rate other than the item's price |
| `sales_invoice.change_warehouse` | feature | **= Allow Changing Warehouse** (settings + profile override) |
| `collections.card` | feature | Collect by a non-cash Mode of Payment (type ≠ Cash) |
| `collections.multiple_payment_modes` | feature | Split a collection across methods |
| `inventory.transfer` | feature | A **field user** moves stock between their van and a warehouse ticked *VanSaleX Transfer Point*. **Default off.** No screen in the app yet (API `stock.transfer`; Stock Entry in Desk). Admins aren't limited |
| `inventory.adjust` | feature | A **field user** writes off (decreases) stock in their own van, up to *Max Stock Write-off Qty*. **Default off.** No screen yet (API `stock.adjust`). Admins aren't limited |

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
2. **DocType backstop** — `check_doc_access` in `doc_events`, for **field
   users** (enabled ZG Van Sale Profile, type Field User) on any entry point
   — `/api/resource`, the shared `accounting.customers.*` /
   `warehouse.items.*` endpoints, Desk:
   - Sales Invoice / return, Sales Order, Purchase Invoice / Order, Payment
     Entry (Receive) `before_insert`, Customer / Item `before_save`: the
     module switch (a Cash invoice's own auto Payment Entry passes,
     `flags.zatgo_auto_cash_payment`);
   - **Stock Entry** (`validate`, `before_submit`): only a transfer or a
     write-off that follows [Stock limits](#stock-limits-for-field-users);
     Material Receipt and every other purpose are refused;
   - **Payment Entry `Pay` / `Internal Transfer`**: refused, except the
     purchase bill's own payment (same flag as above);
   - **Sales Invoice / Order feature switches** the vansalex API enforces on
     its own path: without `sales_invoice.edit_rate` a line must carry the
     item's price (`check_item_rates`), a discount needs
     `sales_invoice.discount` / `.line_discount` and stays within Max Discount
     %, a credit sale (Payment Type Credit, or none and nothing paid on the
     invoice) needs credit sales allowed, and every warehouse must be one the
     user may sell from (`allowed_warehouse`: their own, or another only with
     `change_warehouse`). Returns are exempt. Documents the vansalex API built
     (create_order, confirm_order, create_sales_order) carry an in-process
     flag (`mark_api_validated`) and are not re-checked: the API already did
     it, and a REST caller can't set the flag.
   Not covered yet (API-only): Bank payment type, Choose payment account and
   Split payment on a directly posted invoice.
   A VanSale Admin / System Manager is exempt from the Stock Entry, Payment
   Entry Pay and sales-feature checks.

Nothing is cached on the device, so there is nothing to tamper with; a
modified app still hits both layers.

## Stock limits for field users

`services/vansalex_stock_rules.py` — one set of rules for the `stock.transfer`
/ `stock.adjust` endpoints and the Stock Entry backstop. Admins (VanSale
Admin, System Manager, Administrator) and users without a van profile are not
limited by it (their ERPNext permissions still apply).

| What | Rule |
|---|---|
| Transfer (`inventory.transfer`, default off) | one side is the user's own van, the other a leaf, enabled warehouse of the same company ticked **VanSaleX Transfer Point** (Warehouse form). Van ↔ van and any other warehouse are refused; with no Transfer Point ticked nothing can be transferred. A blank `from_warehouse` is the van. |
| Write-off (`inventory.adjust`, default off) | own van only (a different `warehouse` is refused — it used to be swapped for the van), decrease only (a Material Issue; stock never appears from nowhere), at most **Max Stock Write-off Qty** per item line (VanSaleX Settings → Van Stock; 0 = no cap). The optional `reason` goes into the Stock Entry's remarks. |
| Opening stock | an item op with `opening_quantity` / `opening_qty` (item bundle, `sync.batch`, `warehouse.items.create`) from a field user is refused (PermissionError) before anything is written. No shipped client sends it. |

Stock comes into a van by a transfer from a Transfer Point, a purchase invoice
(`purchase_invoice` module) or an admin.

## ensure_vansale_perms seeds once

`setup/ensure_vansale_perms.py` creates the Custom DocPerms VanSale roles need
(Sales Invoice, Stock Entry, ...) — **once per DocType/role pair**, recorded
as a global default `zg_vansale_perm_<doctype>_<role>`. After that the pair
belongs to the site's admin: a row they delete is not re-created on migrate
and a flag they change is not reset. The first run after upgrading tops
existing rows up (add-only) so nothing the roles rely on is missing, and marks
them; an admin removal made *before* that upgrade is re-granted that one
time. To have a grant seeded again, delete its marker (Desk → Defaults, or
`frappe.db.delete("DefaultValue", {"defkey": ...})`) and migrate.

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

## Cash / Bank accounts

Cash and Bank sales pay into one ledger account (ERPNext's auto Payment
Entry). Default, first match wins: the driver's `ZG Van Sale Profile`
Cash / Bank Account → `VanSaleX Settings` Default Cash / Bank Account (if it
belongs to the driver's company) → ERPNext (Mode of Payment "Cash" default;
the company's Bank-type Mode of Payment default, "Bank" first). The app
starts on that account; changing it needs `sales_invoice.multiple_payment_accounts`
(`orders.payment_accounts` lists the choices: just the default without the
feature, else all enabled Cash- / Bank-type ledger accounts of the company).
The server checks the account's type and company before saving anything.
Bank also takes an optional transfer / cheque no. (`bank_reference_no`, blank
= the invoice no.).

## Purchases (buying into the van)

`purchase_invoice` / `purchase_order` mirror the sales flow
(`services/vansalex_purchase_service.py`, `api/v1/vansalex/purchases.py`):
a **Purchase Invoice** is submitted at once with `update_stock` into the van
warehouse; a **Purchase Order** moves no stock until *Convert to Invoice*
(ERPNext's own mapper). Cash / Bank / Credit and the pay-from account are
validated by the same `resolve_sale` as a sale (so *Allow Credit Sales*,
*Allow Bank Payment* and *Choose payment account* apply to purchases too); a
Cash or Bank bill gets its Payment Entry (Pay) on submit. Rates are the buying
price: typed, else the item's last purchase rate (none on record = refused).
Optional supplier invoice no. (`bill_no`) and Bank reference no.

Field users have no ERPNext permission on purchase documents: the module
switch is the authorization, writes run with `ignore_permissions`, and a driver
only lists / prints / converts their **own** documents (admins: all). The
auto Payment Entry is built as Administrator and re-owned by the driver
(`invoice_cash_payment_service._reader_for`). Same `client_id` idempotency as
a sale (`zatgo_client_id` on Purchase Invoice and, new, Purchase Order —
`patches/v0_3_0`). The DocType backstop covers direct inserts.

**Purchase returns** (`purchase_return`): a debit note (Purchase Invoice with
`is_return`) for part or all of a purchase, built with ERPNext's
`make_return_doc`; quantities are capped at what is left to return, a driver
returns only against their own van's purchases, and the returned stock leaves
the warehouse it was received into. The amount sits on the debit note as a
negative outstanding that ERPNext nets against the supplier; a refund the
supplier pays is not recorded here. Lists: `purchases.list(kind=invoice|order|return)`.
