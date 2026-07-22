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
    try:
        doc = frappe.get_doc({"doctype": doctype, **values})
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception as exc:  # noqa: BLE001
        frappe.log_error(f"{doctype} seed skipped: {exc}", "zatgo_core.seed")
        return None


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
                "status": "Assigned",
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
                "status": "Out For Delivery",
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
    van = _seed_van_sale_enrichment(items=items, customers=customers, group=group)
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
        "van_sale": van,
    }
    frappe.logger("zatgo_core").info("seed_demo_data complete: %s", summary)
    return summary


def _ensure_item_price(item_code: str, rate: float, price_list: str = "Standard Selling") -> None:
    if not frappe.db.exists("Price List", price_list):
        return
    existing = frappe.db.exists(
        "Item Price",
        {"item_code": item_code, "price_list": price_list, "selling": 1},
    )
    if existing:
        frappe.db.set_value("Item Price", existing, "price_list_rate", rate, update_modified=False)
        return
    frappe.get_doc(
        {
            "doctype": "Item Price",
            "item_code": item_code,
            "price_list": price_list,
            "selling": 1,
            "buying": 0,
            "price_list_rate": rate,
        }
    ).insert(ignore_permissions=True)


def _ensure_warehouse(warehouse_name: str, company: str) -> str | None:
    if not company:
        return None
    existing = frappe.db.exists("Warehouse", warehouse_name)
    if existing:
        return existing
    # Prefer under All Warehouses - <abbr> when present
    parent = frappe.db.get_value(
        "Warehouse",
        {"company": company, "is_group": 1, "warehouse_name": ("like", "All Warehouses%")},
        "name",
    )
    payload: dict[str, Any] = {
        "doctype": "Warehouse",
        "warehouse_name": warehouse_name.split(" - ")[0] if " - " in warehouse_name else warehouse_name,
        "company": company,
        "is_group": 0,
    }
    if parent:
        payload["parent_warehouse"] = parent
    try:
        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception as exc:  # noqa: BLE001
        frappe.log_error(f"Warehouse seed skipped: {exc}", "zatgo_core.seed")
        # Fall back to first non-group warehouse for the company
        return frappe.db.get_value(
            "Warehouse",
            {"company": company, "is_group": 0},
            "name",
            order_by="creation asc",
        )


def _ensure_opening_stock(warehouse: str, lines: list[tuple[str, float, float]], company: str) -> str | None:
    """Material Receipt into van warehouse when Bin qty is zero."""
    if not warehouse or not company or not lines:
        return None
    need: list[tuple[str, float, float]] = []
    for item_code, qty, rate in lines:
        if not frappe.db.exists("Item", item_code):
            continue
        bal = frappe.db.get_value(
            "Bin",
            {"item_code": item_code, "warehouse": warehouse},
            "actual_qty",
        )
        if float(bal or 0) <= 0:
            need.append((item_code, qty, rate))
    if not need:
        return None

    # Find stock entry type / purpose compatible with this ERPNext version
    purpose = "Material Receipt"
    se = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": purpose,
            "purpose": purpose,
            "company": company,
            "to_warehouse": warehouse,
            "items": [
                {
                    "item_code": code,
                    "qty": qty,
                    "t_warehouse": warehouse,
                    "basic_rate": rate,
                    "allow_zero_valuation_rate": 0,
                }
                for code, qty, rate in need
            ],
        }
    )
    try:
        se.insert(ignore_permissions=True)
        se.submit()
        return se.name
    except Exception as exc:  # noqa: BLE001
        frappe.log_error(f"Opening stock seed skipped: {exc}", "zatgo_core.seed")
        try:
            if se.name:
                se.reload()
                if se.docstatus == 0:
                    se.delete(ignore_permissions=True)
        except Exception:  # noqa: BLE001
            pass
        return None


def _seed_van_sale_enrichment(
    *,
    items: list[str],
    customers: list[str],
    group: str,
) -> dict[str, Any]:
    """Extra masters/stock tailored for Flutter Van Sale on demo sites."""
    company = _company()
    extra_items = [
        _ensure_item("ZG-RICE-5KG", item_name="Basmati Rice 5kg", rate=42.0, group=group, uom="Nos"),
        _ensure_item("ZG-OIL-1L", item_name="Cooking Oil 1L", rate=12.0, group=group, uom="Nos"),
        _ensure_item("ZG-SUGAR-1KG", item_name="White Sugar 1kg", rate=6.5, group=group, uom="Nos"),
        _ensure_item("ZG-TEA-200", item_name="Black Tea 200g", rate=9.75, group=group, uom="Pack"),
        _ensure_item("ZG-BREAD", item_name="Arabic Bread Pack", rate=3.0, group=group, uom="Pack"),
        _ensure_item("ZG-YOGURT", item_name="Yogurt Cup", rate=2.25, group=group, uom="Nos"),
        _ensure_item("ZG-CHIPS", item_name="Potato Chips 150g", rate=4.5, group=group, uom="Nos"),
        _ensure_item("ZG-SODA-330", item_name="Cola Can 330ml", rate=2.0, group=group, uom="Nos"),
        _ensure_item("ZG-DATES-500", item_name="Dates Box 500g", rate=15.0, group=group, uom="Box"),
        _ensure_item("ZG-HONEY-250", item_name="Honey Jar 250g", rate=22.0, group=group, uom="Nos"),
    ]
    all_items = list(dict.fromkeys([*items, *extra_items]))

    extra_customers = [
        _ensure_customer(
            "Najd Corner Store",
            customer_group="Commercial",
            territory="Riyadh",
        ),
        _ensure_customer(
            "Wadi Superette",
            customer_group="Commercial",
            territory="Riyadh",
        ),
        _ensure_customer(
            "Souq Express",
            customer_group="Commercial",
            territory="Riyadh",
        ),
        _ensure_customer(
            "Palm Grove Mart",
            customer_group="Commercial",
            territory="Riyadh",
        ),
        _ensure_customer(
            "Highway Stop Shop",
            customer_group="Commercial",
            territory="Riyadh",
        ),
    ]
    all_customers = list(dict.fromkeys([*customers, *extra_customers]))

    # Item prices on Standard Selling
    rates = {
        "ZG-WATER-15": 5.0,
        "ZG-SNACK-MIX": 18.5,
        "ZG-MILK-1L": 4.25,
        "ZG-JUICE-200": 2.5,
        "ZG-BURGER": 16.0,
        "ZG-FRIES": 5.0,
        "ZG-SALAD": 8.0,
        "ZG-COFFEE": 3.5,
        "ZG-RICE-5KG": 42.0,
        "ZG-OIL-1L": 12.0,
        "ZG-SUGAR-1KG": 6.5,
        "ZG-TEA-200": 9.75,
        "ZG-BREAD": 3.0,
        "ZG-YOGURT": 2.25,
        "ZG-CHIPS": 4.5,
        "ZG-SODA-330": 2.0,
        "ZG-DATES-500": 15.0,
        "ZG-HONEY-250": 22.0,
    }
    for code, rate in rates.items():
        if frappe.db.exists("Item", code):
            _ensure_item_price(code, rate)
            frappe.db.set_value("Item", code, "standard_rate", rate, update_modified=False)

    warehouse = _ensure_warehouse("Van 07", company) if company else None
    # Prefer exact name if ERPNext appended company abbr
    if warehouse and company:
        abbr = frappe.db.get_value("Company", company, "abbr") or ""
        preferred = f"Van 07 - {abbr}" if abbr else warehouse
        if frappe.db.exists("Warehouse", preferred):
            warehouse = preferred

    stock_lines = [
        ("ZG-WATER-15", 120, 5.0),
        ("ZG-SNACK-MIX", 40, 18.5),
        ("ZG-MILK-1L", 80, 4.25),
        ("ZG-JUICE-200", 100, 2.5),
        ("ZG-RICE-5KG", 35, 42.0),
        ("ZG-OIL-1L", 50, 12.0),
        ("ZG-SUGAR-1KG", 60, 6.5),
        ("ZG-TEA-200", 45, 9.75),
        ("ZG-BREAD", 70, 3.0),
        ("ZG-YOGURT", 55, 2.25),
        ("ZG-CHIPS", 90, 4.5),
        ("ZG-SODA-330", 150, 2.0),
        ("ZG-DATES-500", 30, 15.0),
        ("ZG-HONEY-250", 25, 22.0),
        ("ZG-BURGER", 20, 16.0),
        ("ZG-FRIES", 40, 5.0),
        ("ZG-SALAD", 25, 8.0),
        ("ZG-COFFEE", 60, 3.5),
    ]
    stock_entry = None
    if warehouse and company:
        stock_entry = _ensure_opening_stock(warehouse, stock_lines, company)

    now = now_datetime()
    more_trips = [
        _ensure_zg(
            "ZG Trip",
            {"title": "Stop 4 — Najd Corner"},
            {
                "title": "Stop 4 — Najd Corner",
                "customer": "Najd Corner Store",
                "address": "Exit 10 Service Rd",
                "sequence": 4,
                "lat": 24.72,
                "lng": 46.66,
                "status": "Planned",
                "planned_at": add_to_date(now, hours=2),
            },
        ),
        _ensure_zg(
            "ZG Trip",
            {"title": "Stop 5 — Wadi Superette"},
            {
                "title": "Stop 5 — Wadi Superette",
                "customer": "Wadi Superette",
                "address": "Wadi Hanifa District",
                "sequence": 5,
                "lat": 24.68,
                "lng": 46.70,
                "status": "Planned",
                "planned_at": add_to_date(now, hours=3),
            },
        ),
        _ensure_zg(
            "ZG Trip",
            {"title": "Stop 6 — Souq Express"},
            {
                "title": "Stop 6 — Souq Express",
                "customer": "Souq Express",
                "address": "Diriyah Gate Retail",
                "sequence": 6,
                "lat": 24.74,
                "lng": 46.58,
                "status": "Planned",
                "planned_at": add_to_date(now, hours=4),
            },
        ),
        _ensure_zg(
            "ZG Trip",
            {"title": "Stop 7 — Palm Grove"},
            {
                "title": "Stop 7 — Palm Grove",
                "customer": "Palm Grove Mart",
                "address": "Northern Ring Rd",
                "sequence": 7,
                "lat": 24.78,
                "lng": 46.69,
                "status": "Planned",
                "planned_at": add_to_date(now, hours=5),
            },
        ),
        _ensure_zg(
            "ZG Trip",
            {"title": "Stop 8 — Highway Stop"},
            {
                "title": "Stop 8 — Highway Stop",
                "customer": "Highway Stop Shop",
                "address": "Dammam Hwy km 18",
                "sequence": 8,
                "lat": 24.64,
                "lng": 46.80,
                "status": "Planned",
                "planned_at": add_to_date(now, hours=6),
            },
        ),
    ]

    frappe.db.commit()
    return {
        "company": company,
        "warehouse": warehouse,
        "items": all_items,
        "customers": all_customers,
        "stock_entry": stock_entry,
        "extra_trips": [t for t in more_trips if t],
        "prefs_hint": {
            "site": "https://demo.zatgo.online",
            "company": company,
            "warehouse": warehouse,
        },
    }
