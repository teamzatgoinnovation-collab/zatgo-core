// An empty "Source Warehouse" on a new Sales Invoice / Sales Order / Delivery
// Note (and "Set Accepted Warehouse" on a Purchase Receipt) is pre-filled with the user's default warehouse (the server fills it
// on save too -- events/default_source_warehouse.py).

for (const doctype of ["Sales Invoice", "Sales Order", "Delivery Note", "Purchase Receipt"]) {
	frappe.ui.form.on(doctype, {
		setup(frm) {
			// Only warehouses ticked "Selectable in VanSaleX" are offered.
			const query = () => ({
				query: "zatgo_core.events.default_source_warehouse.warehouse_query",
				filters: { company: frm.doc.company },
			});
			frm.set_query("set_warehouse", query);
			if (frm.fields_dict.rejected_warehouse) frm.set_query("rejected_warehouse", query);
		},
		onload(frm) {
			if (!frm.is_new() || frm.doc.set_warehouse) return;
			frappe.call({
				method: "zatgo_core.events.default_source_warehouse.get_default_source_warehouse",
				args: { company: frm.doc.company },
				callback(r) {
					if (r.message && !frm.doc.set_warehouse) frm.set_value("set_warehouse", r.message);
				},
			});
		},
	});
}
