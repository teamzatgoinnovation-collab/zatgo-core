# User Manual — ZatGo Core

ZatGo Core is an **API / settings hub**, not a Desk application. Manage data via
whitelisted methods from clients, or open DocTypes from AwesomeBar when needed.

## Settings DocTypes

| DocType | Purpose |
|---------|---------|
| ZG System Settings | Brand, defaults, maintenance |
| ZG Company Settings | Per-company rows |
| ZG Branch Settings | Branches |
| ZG Application Settings | Client app registry |
| ZG Feature Flag | Product feature toggles |
| ZG Security Settings | Password / session policy |
| ZG Integration / Printer / Payment / Notification / Storage | Cross-cutting config |
| ZG Registered Application / ZG Setting Section | Plugin manifests |
| ZG Audit Log | Audit history |

## Typical admin flow

1. Set brand + defaults in **ZG System Settings**
2. Review company rows in **ZG Company Settings**
3. Create branches in **ZG Branch Settings**
4. Configure clients in **ZG Application Settings**
5. Toggle product features in **ZG Feature Flag**
6. Configure printers / payments / notifications as needed

Product Desk UIs (Tracker, POS, etc.) live in their domain apps under
`CustomApps/erpnext/<Product>/`, not in this hub.
