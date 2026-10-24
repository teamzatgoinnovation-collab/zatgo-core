# User Manual — ZatGo Core

ZatGo is the supporting layer on top of ERPNext: its apps (VanSaleX, Tracker, ZatGo AI, ZatGo Space, industries),
its settings and the API its client apps use. In Desk, open **ZatGo** in the app switcher.

## Apps

**ZatGo Apps** (ZatGo sidebar → General Settings → *ZatGo Apps*, System Manager only) lists every app on this site with
its version, whether it is on, what it needs, and what is not set up yet. The switch turns an app on or off for
this site:

- **Off** hides the app (its sidebar entry, its Desk workspace) and its API answers "not found". Nothing is
  deleted — records, roles and settings stay, and switching it on again brings everything back.
- An app that **needs** another cannot be on while that one is off (the page and the form say which).
- Only a System Manager can switch apps or industries, from the page or from *ZG System Settings*.

Each app has its own page: **ZatGo sidebar → Apps → the app**. Its **Overview** tab lists the app's screens (only
those your role may open); the other tabs are its settings, one tab per topic (for example *VanSaleX → Payments /
Sales & Warehouse / Modules & Features*). The ZatGo sidebar has two sections: **Apps** and **General Settings**
(company, branch, payment, security settings and the app switches). An app's own rail icon is hidden: apps open
from ZatGo → Apps.

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

Developers: `plugin_guide.md` (adding an app), `naming.md`, `architecture.md`.
