# ZatGo reports

*Phase 10, 2026-11-28.*

## Principle
ERPNext's own reports are the reports. They read the General Ledger and Stock Ledger, honour User Permissions and are maintained upstream. ZatGo adds a report only for a question ERPNext does not answer, and never with mock data.

The **ZatGo Reports** workspace links them by area:

| Area | ERPNext reports linked |
|---|---|
| Financial | Profit and Loss Statement, Balance Sheet, Trial Balance |
| Parties | Accounts Receivable, Accounts Payable |
| Sales and purchase | Sales Analytics, Purchase Analytics, Gross Profit |
| Stock | Stock Balance, Stock Ledger, Stock Ageing |

Each link shows only to users whose roles may open the report.

## ZatGo's own reports
| Report | Question | Source | Roles |
|---|---|---|---|
| Business Summary Report | one-screen sales, purchases, party cash and balances for a date range | General Ledger aggregates | Accounts User, Accounts Manager, System Manager |
| Payment Method Summary | how much came in and went out per payment method and account | Sales Invoice payment rows, Payment Entries (with Payment Allocation rows) | Accounts User, Accounts Manager, System Manager |

Number Cards on the ZatGo ERP workspace (sales / purchase invoices and orders, counts and totals) are Frappe Document Type cards, so Frappe applies permissions to them.

MyBis (the BI app) reads through `zatgo_core.mybis`; its queries are documented in `docs/mybis.md`.

## Rules for a report
- **Filters**: company, date range; warehouse where stock is involved.
- **Permissions**: a Script Report that uses `frappe.db.sql` skips User Permissions. It must check the filters itself: `frappe.has_permission("Company", "read", doc=company, throw=True)`, and the same for any Account or Warehouse filter. Both ZatGo reports now do (Payment Method Summary was fixed in Phase 10).
- **Performance**: one aggregate query per figure, on indexed columns (`company`, `posting_date`, `is_cancelled`, `account`). Run `EXPLAIN` on a new query before it ships.
- **Submitted documents only**; cancelled GL entries are excluded.
