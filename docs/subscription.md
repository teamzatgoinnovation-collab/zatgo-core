# Subscription gate (read-only mode)

A tenant site of ZatGo Space becomes **read-only** when its free trial ended without payment (or its subscription is
suspended / overdue). Everything can still be viewed and reported on; every create / update / delete / submit /
cancel / amend / import is refused.

## Where the state comes from
The platform pushes `zg_subscription` into this site's `site_config.json` (`bench set-config`, from
`space_cloud/services/tenant_sync.py`). Only the bench user can write that file, so nobody inside the site (System
Manager and Administrator included) can extend their own trial. The dates travel with the state, so expiry is
enforced locally even if a later push is missed.

```json
{"enforcement_on": 1, "status": "TRIAL", "trial_ends_at": "2026-12-06T12:00:00+00:00", "paid_until": null,
 "site_url": "https://acme.example.com", "portal_url": "https://space.example.com", "synced_at": "..."}
```

No `zg_subscription`, or `enforcement_on` 0, means **unrestricted** (fail-open): every site that is not a Space
customer site, and every Space site until an admin ticks "Enforce read-only mode" in Space Settings.

## Rule (`services/subscription_gate.py::evaluate`)
read-only when `enforcement_on` and: status is EXPIRED / SUSPENDED / PENDING_PAYMENT / DELETION_SCHEDULED / DELETED;
or TRIAL past `trial_ends_at` with no `paid_until` in the future; or ACTIVE more than 3 days past `paid_until`.
Unknown statuses never lock a site.

## Enforcement layers
1. `gate_requests` (before_request): known write endpoints and `/api/resource` write verbs -> 403.
2. `doc_has_permission` (has_permission `*`): a write permission check on a document answers no.
3. `enforce_doc_write` (doc_events `*`): every document write, `ignore_permissions` or not -- catches custom
   whitelisted endpoints, integrations and background jobs.

Exempt: log/queue doctypes (`EXEMPT_DOCTYPES`), a user's own User record, install / migrate / patch contexts.
A scheduler job that writes should be wrapped with `subscription_gate.guard_job`.

## Known gap
Code that writes with raw SQL, `frappe.db.set_value` or `db_set` never fires a document event and is not blocked.
That is how Frappe is built; reviewing new code for such writes is the mitigation.

## Activity
`services/activity.py::last_human_activity` is read by the platform's inactivity clock: successful logins, live
sessions and document changes by real users. API-key users and Guest never count; Administrator counts for logins
and sessions (it is the customer's own admin) but not for document changes (the scheduler runs as Administrator).

## Desk
`bootinfo.zatgo_core.subscription` feeds `public/js/zg_subscription_banner.js` (trial days left, read-only notice).
Tests: `tests/unit/test_subscription_gate.py`, `tests/integration/test_subscription_gate.py`.
