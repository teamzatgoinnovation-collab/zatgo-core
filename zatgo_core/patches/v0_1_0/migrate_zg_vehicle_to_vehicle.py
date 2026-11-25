"""Migrate ZatGo Vehicle records → ERPNext Vehicle DocType.

Old ZatGo Vehicle fields:
  title, plate, vehicle_type, status, driver_name

ERPNext Vehicle fields:
  license_plate, make, location, employee, chassis_no (all optional)
"""

from __future__ import annotations

import frappe


def execute() -> None:
    """Copy ZatGo Vehicle rows into ERPNext Vehicle; remap link fields."""
    if not frappe.db.exists("DocType", "ZatGo Vehicle"):
        return  # already removed, nothing to do

    zg_vehicles = frappe.get_all(
        "ZatGo Vehicle",
        fields=["name", "title", "plate", "vehicle_type", "status", "driver_name"],
    )

    # Map old ZatGo Vehicle name → new ERPNext Vehicle name (license_plate)
    name_map: dict[str, str] = {}

    for v in zg_vehicles:
        plate = v.get("plate") or v.get("name")
        title = v.get("title") or plate

        # ERPNext Vehicle uses license_plate as the natural key
        # Ensure UOM exists
        uom_name = "Kilometer"
        if not frappe.db.exists("UOM", uom_name):
            frappe.get_doc({"doctype": "UOM", "uom_name": uom_name}).insert(ignore_permissions=True)

        if not frappe.db.exists("Vehicle", {"license_plate": plate}):
            vehicle_doc = frappe.get_doc({
                "doctype": "Vehicle",
                "license_plate": plate,
                "make": title,
                "model": v.get("vehicle_type") or "Van",
                "last_odometer": 0,
                "fuel_type": "Diesel",
                "uom": uom_name,
            })
            vehicle_doc.insert(ignore_permissions=True)
            new_name = vehicle_doc.name
        else:
            new_name = frappe.db.get_value("Vehicle", {"license_plate": plate}, "name")

        name_map[v["name"]] = new_name

    frappe.db.commit()

    # Remap links: Van Sale Profile.vehicle
    for old, new in name_map.items():
        frappe.db.sql(
            "UPDATE `tabVan Sale Profile` SET `vehicle` = %s WHERE `vehicle` = %s",
            (new, old),
        )
        frappe.db.sql(
            "UPDATE `tabDelivery Boy` SET `vehicle` = %s WHERE `vehicle` = %s",
            (new, old),
        )
        frappe.db.sql(
            "UPDATE `tabTrip` SET `vehicle` = %s WHERE `vehicle` = %s",
            (new, old),
        )

    frappe.db.commit()
    frappe.logger().info(
        f"migrate_zg_vehicle_to_vehicle: migrated {len(name_map)} vehicles → ERPNext Vehicle"
    )
