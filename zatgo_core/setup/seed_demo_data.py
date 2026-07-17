"""Seed ERPNext + zatgo_core demo data so product apps return real list payloads.

Run:
  bench --site <site> execute zatgo_core.setup.seed_demo_data.seed
Or:
  ./scripts/seed_zatgo_demo_data.sh development development.localhost
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_to_date, now_datetime


def _ensure_uom(name: str) -> str:
    if frappe.db.exists("UOM", name):
        return name
    doc = frappe.get_doc({"doctype": "UOM", "uom_name": name})
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_tree_root(doctype: str, name: str, name_field: str) -> str:
    """Create a root tree node when ERPNext masters were never seeded."""
    if frappe.db.exists(doctype, name):
        return name
    payload: dict[str, Any] = {
        "doctype": doctype,
        name_field: name,
        "is_group": 1,
    }
    # NestedSet roots omit parent_*; ERPNext validates empty parent on insert
    doc = frappe.get_doc(payload)
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_tree_leaf(
    doctype: str,
    name: str,
    *,
    name_field: str,
    parent_field: str,
    parent: str,
) -> str:
    if frappe.db.exists(doctype, name):
        return name
    doc = frappe.get_doc(
        {
            "doctype": doctype,
            name_field: name,
            parent_field: parent,
            "is_group": 0,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_masters() -> dict[str, str]:
    """Ensure minimal Item/Customer/Supplier tree masters + UOMs."""
    for uom in ("Nos", "Box", "Pack", "Unit"):
        _ensure_uom(uom)

    item_root = _ensure_tree_root("Item Group", "All Item Groups", "item_group_name")
    item_group = _ensure_tree_leaf(
        "Item Group",
        "ZatGo Products",
        name_field="item_group_name",
        parent_field="parent_item_group",
        parent=item_root,
    )

    customer_root = _ensure_tree_root("Customer Group", "All Customer Groups", "customer_group_name")
    customer_group = _ensure_tree_leaf(
        "Customer Group",
        "Commercial",
        name_field="customer_group_name",
        parent_field="parent_customer_group",
        parent=customer_root,
    )

    territory_root = _ensure_tree_root("Territory", "All Territories", "territory_name")
    territory = _ensure_tree_leaf(
        "Territory",
        "Riyadh",
        name_field="territory_name",
        parent_field="parent_territory",
        parent=territory_root,
    )

    supplier_root = _ensure_tree_root("Supplier Group", "All Supplier Groups", "supplier_group_name")
    supplier_group = _ensure_tree_leaf(
        "Supplier Group",
        "Local",
        name_field="supplier_group_name",
        parent_field="parent_supplier_group",
        parent=supplier_root,
    )

    return {
        "item_group": item_group,
        "customer_group": customer_group,
        "territory": territory,
        "supplier_group": supplier_group,
    }


def _ensure_item(
    code: str,
    *,
    item_name: str,
    rate: float,
    group: str,
    uom: str = "Nos",
) -> str:
    if frappe.db.exists("Item", code):
        return code
    _ensure_uom(uom)
    doc = frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": code,
            "item_name": item_name,
            "item_group": group,
            "stock_uom": uom,
            "is_stock_item": 1,
            "include_item_in_manufacturing": 0,
            "standard_rate": rate,
            "valuation_rate": rate,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_customer(
    name: str,
    *,
    customer_type: str = "Company",
    customer_group: str = "Commercial",
    territory: str = "Riyadh",
) -> str:
    existing = frappe.db.get_value("Customer", {"customer_name": name}, "name")
    if existing:
        return existing
    doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": customer_type,
            "customer_group": customer_group,
            "territory": territory,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_supplier(name: str, *, supplier_group: str = "Local") -> str:
    existing = frappe.db.get_value("Supplier", {"supplier_name": name}, "name")
    if existing:
        return existing
    doc = frappe.get_doc(
        {
            "doctype": "Supplier",
            "supplier_name": name,
            "supplier_group": supplier_group,
            "supplier_type": "Company",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_lead(lead_name: str, company_name: str) -> str:
    existing = frappe.db.get_value("Lead", {"lead_name": lead_name}, "name")
    if existing:
        return existing
    doc = frappe.get_doc(
        {
            "doctype": "Lead",
            "lead_name": lead_name,
            "company_name": company_name,
            "status": "Open",
            "email_id": f"{lead_name.lower().replace(' ', '.')}@example.com",
            "mobile_no": "+966500000001",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _company() -> str:
    return frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value(
        "Company", {}, "name"
    )


def _ensure_employee(employee_name: str) -> str | None:
    if not frappe.db.exists("DocType", "Employee"):
        return None
    existing = frappe.db.get_value("Employee", {"employee_name": employee_name}, "name")
    if existing:
        return existing
    company = _company()
    if not company:
        return None
    # Minimal employee — date_of_joining / gender often required
    payload: dict[str, Any] = {
        "doctype": "Employee",
        "first_name": employee_name.split()[0],
        "last_name": " ".join(employee_name.split()[1:]) or "Demo",
        "employee_name": employee_name,
        "company": company,
        "status": "Active",
        "date_of_joining": "2024-01-01",
        "gender": "Male",
        "date_of_birth": "1990-01-01",
    }
    try:
        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception as exc:  # noqa: BLE001
        frappe.log_error(f"Employee seed skipped: {exc}", "zatgo_core.seed")
        return None


def _ensure_zg(doctype: str, filters: dict[str, Any], values: dict[str, Any]) -> str | None:
    if not frappe.db.exists("DocType", doctype):
        return None
    name = frappe.db.exists(doctype, filters)
    if name:
        return name
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    return doc.name


def seed() -> dict[str, Any]:
    """Idempotent demo data for all product API namespaces."""
    frappe.set_user("Administrator")
    masters = _ensure_masters()
    group = masters["item_group"]

    items = [
        _ensure_item("ZG-WATER-15", item_name="Bottled Water 1.5L", rate=5.0, group=group, uom="Nos"),
        _ensure_item("ZG-SNACK-MIX", item_name="Snack Assortment", rate=18.5, group=group, uom="Box"),
        _ensure_item("ZG-MILK-1L", item_name="UHT Milk 1L", rate=4.25, group=group, uom="Nos"),
        _ensure_item("ZG-JUICE-200", item_name="Orange Juice 200ml", rate=2.5, group=group, uom="Pack"),
        _ensure_item("ZG-BURGER", item_name="Beef Burger", rate=16.0, group=group, uom="Nos"),
        _ensure_item("ZG-FRIES", item_name="Fries", rate=5.0, group=group, uom="Nos"),
        _ensure_item("ZG-SALAD", item_name="House Salad", rate=8.0, group=group, uom="Nos"),
        _ensure_item("ZG-COFFEE", item_name="Espresso", rate=3.5, group=group, uom="Nos"),
    ]

    customers = [
        _ensure_customer(
            "Al Noor Mini Mart",
            customer_group=masters["customer_group"],
            territory=masters["territory"],
        ),
        _ensure_customer(
            "City Grocer",
            customer_group=masters["customer_group"],
            territory=masters["territory"],
        ),
        _ensure_customer(
            "Fresh Basket Co-op",
            customer_group=masters["customer_group"],
            territory=masters["territory"],
        ),
        _ensure_customer(
            "Corner Pantry",
            customer_group=masters["customer_group"],
            territory=masters["territory"],
        ),
        _ensure_customer(
            "Green Kitchen Co.",
            customer_group=masters["customer_group"],
            territory=masters["territory"],
        ),
    ]
    supplier = _ensure_supplier("ZatGo Wholesale Supply", supplier_group=masters["supplier_group"])
    leads = [
        _ensure_lead("Sara Ahmed", "Oasis Retail"),
        _ensure_lead("Omar Khalid", "Desert Foods LLC"),
    ]
    employee = _ensure_employee("Omar Khalid")

    vehicles = [
        _ensure_zg(
            "ZG Vehicle",
            {"plate": "VAN-204"},
            {
                "title": "Delivery Van 204",
                "plate": "VAN-204",
                "vehicle_type": "Van",
                "status": "On Route",
                "driver_name": "Amina Hassan",
            },
        ),
        _ensure_zg(
            "ZG Vehicle",
            {"plate": "VAN-07"},
            {
                "title": "Go Van 07",
                "plate": "VAN-07",
                "vehicle_type": "Van",
                "status": "Available",
                "driver_name": "Field Sales Rep",
            },
        ),
    ]

    delivery_boy = _ensure_zg(
        "ZG Delivery Boy",
        {"code": "DB-001"},
        {
            "full_name": "Amina Hassan",
            "code": "DB-001",
            "phone": "+966 50 555 0100",
            "status": "On Route",
            "vehicle": "VAN-204" if vehicles[0] else None,
        },
    )

    now = now_datetime()
    trips = [
        _ensure_zg(
            "ZG Trip",
            {"title": "Stop 1 — Al Noor"},
            {
                "title": "Stop 1 — Al Noor",
                "customer": "Al Noor Mini Mart",
                "address": "King Fahd Rd, Exit 5",
                "sequence": 1,
                "lat": 24.7136,
                "lng": 46.6753,
                "status": "Completed",
                "planned_at": add_to_date(now, hours=-4),
            },
        ),
        _ensure_zg(
            "ZG Trip",
            {"title": "Stop 2 — City Grocer"},
            {
                "title": "Stop 2 — City Grocer",
                "customer": "City Grocer",
                "address": "Olaya St 12",
                "sequence": 2,
                "lat": 24.69,
                "lng": 46.685,
                "status": "Checked In",
                "planned_at": add_to_date(now, hours=-2),
            },
        ),
        _ensure_zg(
            "ZG Trip",
            {"title": "Stop 3 — Fresh Basket"},
            {
                "title": "Stop 3 — Fresh Basket",
                "customer": "Fresh Basket Co-op",
                "address": "Industrial Area Warehouse 4",
                "sequence": 3,
                "lat": 24.65,
                "lng": 46.72,
                "status": "Planned",
                "planned_at": add_to_date(now, hours=1),
            },
        ),
    ]

    stops = [
        _ensure_zg(
            "ZG Delivery Stop",
            {"order_number": "DL-10447"},
            {
                "title": "DL-10447 Green Kitchen",
                "order_number": "DL-10447",
                "customer": "Green Kitchen Co.",
                "address": "5 Warehouse Lane",
                "city": "Riyadh",
                "window_label": "09:00–11:00",
                "items_summary": "Foodservice · 8 trays",
                "sequence": 1,
                "phone": "+966 50 100 2001",
                "status": "Pending",
                "delivery_boy": delivery_boy,
                "lat": 24.71,
                "lng": 46.67,
            },
        ),
        _ensure_zg(
            "ZG Delivery Stop",
            {"order_number": "DL-10448"},
            {
                "title": "DL-10448 City Grocer",
                "order_number": "DL-10448",
                "customer": "City Grocer",
                "address": "Olaya St 12",
                "city": "Riyadh",
                "window_label": "11:30–13:00",
                "items_summary": "Grocery · 12 cases",
                "sequence": 2,
                "phone": "+966 50 100 2002",
                "status": "En Route",
                "delivery_boy": delivery_boy,
                "lat": 24.69,
                "lng": 46.68,
            },
        ),
        _ensure_zg(
            "ZG Delivery Stop",
            {"order_number": "DL-10449"},
            {
                "title": "DL-10449 Al Noor",
                "order_number": "DL-10449",
                "customer": "Al Noor Mini Mart",
                "address": "King Fahd Rd, Exit 5",
                "city": "Riyadh",
                "window_label": "14:00–16:00",
                "items_summary": "Beverages · 20 packs",
                "sequence": 3,
                "phone": "+966 50 100 2003",
                "status": "Delivered",
                "delivery_boy": delivery_boy,
                "lat": 24.7136,
                "lng": 46.6753,
            },
        ),
    ]

    tickets = [
        _ensure_zg(
            "ZG Service Ticket",
            {"number": "SRV-1001"},
            {
                "title": "POS drawer jam",
                "number": "SRV-1001",
                "customer": "City Grocer",
                "address": "Olaya St 12",
                "issue": "Cash drawer does not open on print",
                "priority": "High",
                "status": "Scheduled",
                "scheduled_at": add_to_date(now, hours=2),
            },
        ),
        _ensure_zg(
            "ZG Service Ticket",
            {"number": "SRV-1002"},
            {
                "title": "Cooler thermostat",
                "number": "SRV-1002",
                "customer": "Fresh Basket Co-op",
                "address": "Industrial Area Warehouse 4",
                "issue": "Display cooler running warm",
                "priority": "Normal",
                "status": "Open",
                "scheduled_at": add_to_date(now, hours=5),
            },
        ),
        _ensure_zg(
            "ZG Service Ticket",
            {"number": "SRV-1003"},
            {
                "title": "Scale calibration",
                "number": "SRV-1003",
                "customer": "Al Noor Mini Mart",
                "address": "King Fahd Rd, Exit 5",
                "issue": "Counter scale drifts by 20g",
                "priority": "Low",
                "status": "In Progress",
                "scheduled_at": add_to_date(now, hours=-1),
            },
        ),
    ]

    kds_tickets = [
        _ensure_zg(
            "ZG KDS Ticket",
            {"order_number": "POS-1042", "item_name": "Beef Burger"},
            {
                "title": "Beef Burger ×2",
                "order_number": "POS-1042",
                "table_name": "T-12",
                "item_name": "Beef Burger",
                "qty": 2,
                "station": "grill",
                "status": "Queued",
                "opened_at": add_to_date(now, minutes=-8),
                "server": "Layla",
                "note": "No onions",
                "extras": "Cheese,Extra patty",
            },
        ),
        _ensure_zg(
            "ZG KDS Ticket",
            {"order_number": "POS-1042", "item_name": "Fries"},
            {
                "title": "Fries ×2",
                "order_number": "POS-1042",
                "table_name": "T-12",
                "item_name": "Fries",
                "qty": 2,
                "station": "cold",
                "status": "Preparing",
                "opened_at": add_to_date(now, minutes=-8),
                "server": "Layla",
                "note": "",
                "extras": "",
            },
        ),
        _ensure_zg(
            "ZG KDS Ticket",
            {"order_number": "POS-1043", "item_name": "Espresso"},
            {
                "title": "Espresso ×1",
                "order_number": "POS-1043",
                "table_name": "Bar",
                "item_name": "Espresso",
                "qty": 1,
                "station": "bar",
                "status": "Ready",
                "opened_at": add_to_date(now, minutes=-3),
                "server": "Omar",
                "note": "For takeaway",
                "extras": "",
            },
        ),
        _ensure_zg(
            "ZG KDS Ticket",
            {"order_number": "POS-1044", "item_name": "House Salad"},
            {
                "title": "House Salad ×1",
                "order_number": "POS-1044",
                "table_name": "T-4",
                "item_name": "House Salad",
                "qty": 1,
                "station": "cold",
                "status": "Queued",
                "opened_at": add_to_date(now, minutes=-1),
                "server": "Sara",
                "note": "Dressing on side",
                "extras": "Avocado",
            },
        ),
        _ensure_zg(
            "ZG KDS Ticket",
            {"order_number": "POS-1045", "item_name": "Beef Burger"},
            {
                "title": "Beef Burger ×1",
                "order_number": "POS-1045",
                "table_name": "T-7",
                "item_name": "Beef Burger",
                "qty": 1,
                "station": "grill",
                "status": "Preparing",
                "opened_at": add_to_date(now, minutes=-12),
                "server": "Omar",
                "note": "Well done",
                "extras": "",
            },
        ),
        _ensure_zg(
            "ZG KDS Ticket",
            {"order_number": "POS-1046", "item_name": "Orange Juice 200ml"},
            {
                "title": "Orange Juice ×3",
                "order_number": "POS-1046",
                "table_name": "Counter",
                "item_name": "Orange Juice 200ml",
                "qty": 3,
                "station": "counter",
                "status": "Queued",
                "opened_at": now,
                "server": "Layla",
                "note": "",
                "extras": "",
            },
        ),
    ]

    frappe.db.commit()
    summary = {
        "items": items,
        "customers": customers,
        "supplier": supplier,
        "leads": leads,
        "employee": employee,
        "delivery_boy": delivery_boy,
        "trips": [t for t in trips if t],
        "stops": [s for s in stops if s],
        "tickets": [t for t in tickets if t],
        "kds_tickets": [k for k in kds_tickets if k],
        "vehicles": [v for v in vehicles if v],
    }
    frappe.logger("zatgo_core").info("seed_demo_data complete: %s", summary)
    return summary
