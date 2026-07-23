"""Debug helper to diagnose Sales Invoice creation failure for van sale.

Run: bench --site erp.zatgo.online execute zatgo_core.setup.debug_van_order.run
"""
import frappe


def run():
    frappe.set_user("Administrator")

    print("=== Van Sale Order Debug ===")

    # 1. Customer
    cust = frappe.db.get_value("Customer", {"customer_name": "Al Noor Mini Mart"}, "name")
    print(f"Customer: {cust}")

    # 2. Item
    print(f"Item ZG-WATER-15 exists: {frappe.db.exists('Item', 'ZG-WATER-15')}")

    # 3. Key columns
    print(f"SI.zatgo_client_id: {frappe.db.has_column('Sales Invoice', 'zatgo_client_id')}")
    print(f"SI.set_warehouse: {frappe.db.has_column('Sales Invoice', 'set_warehouse')}")
    print(f"SI.update_stock: {frappe.db.has_column('Sales Invoice', 'update_stock')}")

    # 4. Van warehouse
    wh = frappe.db.get_value("ZG Van Sale Profile", {"user": "Administrator"}, "warehouse")
    print(f"Van warehouse: {wh}")

    # 5. Stock in van
    if wh:
        qty = frappe.db.get_value("Bin", {"item_code": "ZG-WATER-15", "warehouse": wh}, "actual_qty")
        print(f"Stock ZG-WATER-15 in {wh}: {qty}")

    # 6. Company & taxes
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    print(f"Company: {company}")
    tax = frappe.db.get_value("Sales Taxes and Charges Template", {"company": company, "disabled": 0}, "name")
    print(f"Tax template: {tax}")

    # 7. Debtors account
    acc = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Receivable", "is_group": 0},
        "name",
    )
    print(f"Receivable account: {acc}")

    # 8. Item income account
    item_acc = frappe.db.get_value(
        "Item Default",
        {"parent": "ZG-WATER-15", "company": company},
        "income_account",
    )
    print(f"Item income account: {item_acc}")

    # 9. Actual invoice test
    try:
        doc = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": cust or "Al Noor Mini Mart",
            "company": company,
            "posting_date": frappe.utils.today(),
            "items": [{"item_code": "ZG-WATER-15", "qty": 1, "rate": 5.0}],
            "update_stock": 1,
        })
        if wh:
            doc.set_warehouse = wh
        doc.insert()
        print(f"INSERT OK: {doc.name}")
        doc.submit()
        print(f"SUBMIT OK: {doc.name} status={doc.status}")
        frappe.db.commit()
        # Cancel and delete for cleanup
        try:
            doc.cancel()
            frappe.db.commit()
            doc.delete()
            frappe.db.commit()
            print("Cleaned up test invoice.")
        except Exception as ce:
            print(f"Cleanup note: {ce}")
    except Exception as e:
        print(f"\nERROR creating invoice: {e}")
        import traceback
        traceback.print_exc()
