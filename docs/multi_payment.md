# Multi-method / multi-account payments

One Sales Invoice or Payment Entry can take its money through several
Payment Methods (Mode of Payment), and through several ledger accounts under
each method, e.g. on one 10,000 invoice:

| Method | Account | Amount |
|--------|---------|-------:|
| Cash | Cash - KAS | 2,000 |
| Cash | Petty Cash - KAS | 500 |
| Card | HDFC POS - KAS | 3,000 |
| Card | SBI POS - KAS | 1,500 |
| UPI | HDFC UPI - KAS | 2,000 |
| UPI | SBI UPI - KAS | 1,000 |

Code: `zatgo_core/services/payment_allocation.py` (rules),
`zatgo_core/overrides/` (class mixins), `zatgo_core/api/v1/accounting/payment_methods.py`,
VanSaleX wiring in `services/vansalex_service.py`.
Tests: `zatgo_core/tests/integration/test_multi_payment.py`.

## Accounting flow (no parallel ledger, nothing posted twice)

**Sales Invoice.** The rows are ERPNext's own `payments` table (Sales Invoice
Payment) on an `is_pos` invoice. ERPNext's `make_pos_gl_entries()` posts one
pair per row:

```
Dr <row account>            row amount
    Cr Debtors (customer)   row amount
```

on top of the invoice's normal `Dr Debtors / Cr Income / Cr VAT` (and stock /
COGS when `update_stock`). Outstanding is ERPNext's own
`grand_total - paid_amount`. No Payment Entry is created, so the existing
Cash auto-Payment-Entry hook skips it (outstanding is already 0).

The only core behaviour changed: ERPNext's `before_save →
set_account_for_mode_of_payment()` overwrote every row's account with the
mode's single default (Petty Cash would have been booked to Cash). The
`ZatGoSalesInvoice` mixin keeps an account that is allowed for the row's
mode, and otherwise falls back to exactly what ERPNext did.

**Payment Entry.** Rows go in `custom_payment_details` (ZG Payment Allocation).
ERPNext's `build_gl_map()` runs unchanged except `add_bank_gl_entries()`:
the single `paid_to` (Receive) / `paid_from` (Pay) line becomes one line per
row, same direction, company-currency amounts summing exactly to the amount
ERPNext would have posted.

```
Receive:  Dr <row accounts…>           Cr Debtors (party)
Pay:      Dr Creditors (party)         Cr <row accounts…>
```

Party line, References (which invoices are settled), outstanding updates,
deductions, taxes, exchange gain/loss and cancellation (ERPNext reverses the
posted GL rows) are all ERPNext's. `paid_to`/`paid_from` is set to the first
row's account so ERPNext's currency and account-type logic still works.
The mixin uses `extend_doctype_class` because hrms already overrides the
Payment Entry class.

## Rules (enforced server-side; the forms only mirror them)

- Every row: an enabled Payment Method, an account that exists, belongs to
  the document's company, is not a group, not disabled, not
  Receivable/Payable, **and is one of that method's allowed accounts** for
  the company. An API caller can't route money to an arbitrary ledger.
- Amount > 0 (a POS return's refund rows are negative, as ERPNext requires).
- Two rows with the same method + account and no Reference are rejected as
  a double entry.
- Sales Invoice total: payments may not exceed the invoice total (no
  ERPNext "change"). A shortfall is allowed only with **Payment Type =
  Credit** (the difference stays outstanding); otherwise: "Payment allocation
  does not match invoice total". VanSaleX's "Allow Credit Sales" setting
  therefore also governs partial payments. Nothing is adjusted silently.
- Rounding: the invoice total compared is ERPNext's `rounded_total` (else
  `grand_total`); payment rows are never rounded.
- Currency: Sales Invoice rows must be in company currency or the invoice
  currency (what `make_pos_gl_entries` assumes). Payment Entry rows must all
  share one currency, that of the bank side. Their total must equal Received
  Amount (Receive) or Paid Amount (Pay). Company-currency amounts are split
  proportionally from ERPNext's `base_*` amount, with the remainder on the
  last row.
- Internal Transfers can't have rows.
- POS-terminal invoices (`is_created_using_pos`) and consolidated ones are
  left entirely to ERPNext's POS flow.
- Backward compatible: invoices and Payment Entries without rows behave
  exactly as before (including the Cash auto-Payment-Entry flow).

## Configuration

Mode of Payment → **Allowed Accounts** (`custom_zg_accounts`): Company,
Account, Default, Enabled. Example for company KAS:

| Mode of Payment | Account | Default |
|-----------------|---------|:-------:|
| Cash | Cash - KAS | ✓ |
| Cash | Petty Cash - KAS | |
| Card | HDFC POS - KAS | ✓ |
| Card | SBI POS - KAS | |
| UPI | HDFC UPI - KAS | ✓ |
| UPI | SBI UPI - KAS | |

The native "Default Account" row for the company (Mode of Payment
Accounts) is also allowed, and is the default when no Allowed Accounts row
is marked Default. Picking a method on a payment row pre-fills its default,
and the Account picker only offers that method's accounts.

## Desk

- Sales Invoice: tick **Is POS** (Payments tab). Rows show Mode, Amount,
  Reference, Account. Below the grid: Invoice Total / Payment Total /
  Difference, with a warning when they differ.
- Payment Entry: the **Payment Details** section under the accounts. The
  first row's account fills Account Paid To/From. The rows' total drives
  Received/Paid Amount. References work as usual.

## API

VanSaleX (`payment_details`: list or JSON string of
`{payment_method, account?, amount, reference_no?, remarks?}`; a missing
account becomes the method's default for the document's company):

- `zatgo_core.api.v1.vansalex.orders.create` / `.confirm`: the invoice
  records the payment itself. Use `payment_type: "Credit"` to allow a
  shortfall.
- `zatgo_core.api.v1.vansalex.collections.create`: `amount` is optional
  when `payment_details` is given; if both are sent they must match.
- `zatgo_core.api.v1.vansalex.collections.modes`: now also returns
  `methods: [{name, type, accounts: [{account, is_default}]}]` for the
  caller's company (`modes` unchanged for older app builds).
- Responses include `payment_details` with each row's `base_amount`.
- `zatgo_core.api.v1.vansalex.orders.preview_totals` (read-only, nothing
  saved): ERPNext's own totals for a would-be `orders.create`;
  `payable_total` (= `rounded_total`, or `grand_total` when rounding is
  disabled) is what a split must add up to. Sales Orders (`create_order_draft`
  ack, `list_sales_orders`) carry `rounded_total` for the same purpose on
  `orders.confirm`. ERPNext rounds to the currency's smallest fraction with
  the site's rounding method, so clients must not re-derive it.

Desk / other clients: `zatgo_core.api.v1.accounting.payment_methods.methods(company)`,
`.default_account(mode_of_payment, company)`, `.account_query` (Link search,
permission-aware).

Plain REST inserts work too: a Sales Invoice with `is_pos: 1` + `payments`,
or a Payment Entry with `custom_payment_details`, goes through the same
document hooks.

## Reporting

**Payment Method Summary** (Script Report, Accounts): received / paid / net
per Payment Method, per Account, or both, in company currency, for a company
and date range. Sources (disjoint, so nothing is counted twice): Sales
Invoice payment rows, Payment Entry `custom_payment_details` rows, and
Payment Entries without rows (header mode + `paid_to`/`paid_from`). The
General Ledger remains the authority for account balances.

## Known limitations

- Bank Reconciliation clears a Payment Entry as a whole. If its rows hit
  several *bank* accounts, reconcile it from the first (`paid_to`/`paid_from`)
  account. Cash and POS-clearing accounts are unaffected.
- `paid_to_account_balance` / `paid_from_account_balance` on the form show
  the first row's account only.
- When a Payment Entry's rows use mixed methods, the header Mode of Payment
  is left empty. The per-row method is in Payment Details and in the report.
- The Flutter VanSaleX app doesn't send `payment_details` yet. The backend is
  ready; that's an app-side change.

## Install / update / verify

```bash
# inside the bench (local devcontainer, or each production backend container)
bench --site <site> migrate          # creates the DocTypes, fields, grid property setters
bench --site <site> clear-cache      # REQUIRED: extend_doctype_class + form scripts are cached
bench --site <site> run-tests --app zatgo_core --module zatgo_core.tests.integration.test_multi_payment
```

Verify the schema rather than trusting Patch Log: `tabZG Payment Allocation`
and `tabZG Mode of Payment Account` exist, `tabSales Invoice Payment` has
`custom_remarks`, and Custom Field rows exist for `Payment Entry.custom_payment_details`
and `Mode of Payment.custom_zg_accounts`.
