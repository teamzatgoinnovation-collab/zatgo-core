"""Migrate ZG Vehicle records → ERPNext Vehicle DocType.

Old ZG Vehicle fields:
  title, plate, vehicle_type, status, driver_name

ERPNext Vehicle fields:
  license_plate, make, location, employee, chassis_no (all optional)
"""

from __future__ import annotations

import frappe


def execute() -> None:
    """Copy ZG Vehicle rows into ERPNext Vehicle; remap link fields."""
    if not frappe.db.exists("DocType", "ZG Vehicle"):
        return  # already removed, nothing to do

    zg_vehicles = frappe.get_all(
        "ZG Vehicle",
        fields=["name", "title", "plate", "vehicle_type", "status", "driver_name"],
    )

    # Map old ZG Vehicle name → new ERPNext Vehicle name (license_plate)
    name_map: dict[str, str] = {}

    for v in zg_vehicles:
        plate = v.get("plate") or v.get("name")
        title = v.get("title") or plate

        # ERPNext Vehicle uses license_plate as the natural key
        if not frappe.db.exists("Vehicle", {"license_plate": plate}):
            vehicle_doc = frappe.get_doc({
                "doctype": "Vehicle",
                "license_plate": plate,
                "make": title,
                "model": v.get("vehicle_type") or "Van",
                "location": "",
            })
            vehicle_doc.insert(ignore_permissions=True)
            new_name = vehicle_doc.name
        else:
            new_name = frappe.db.get_value("Vehicle", {"license_plate": plate}, "name")

        name_map[v["name"]] = new_name

    frappe.db.commit()

    # Remap links: ZG Van Sale Profile.vehicle
    for old, new in name_map.items():
        frappe.db.sql(
            "UPDATE `tabZG Van Sale Profile` SET `vehicle` = %s WHERE `vehicle` = %s",
            (new, old),
        )
        frappe.db.sql(
            "UPDATE `tabZG Delivery Boy` SET `vehicle` = %s WHERE `vehicle` = %s",
            (new, old),
        )
        frappe.db.sql(
            "UPDATE `tabZG Trip` SET `vehicle` = %s WHERE `vehicle` = %s",
            (new, old),
        )

    frappe.db.commit()
    frappe.logger().info(
        f"migrate_zg_vehicle_to_vehicle: migrated {len(name_map)} vehicles → ERPNext Vehicle"
    )
