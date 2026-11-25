// Selling Settings → Document Naming defines which Sales Invoice series exist;
// which user gets which one lives in Sales Invoice Naming Settings. That's
// its own page because Selling Settings is writable by Sales Manager, who must
// not control invoice numbering.

frappe.ui.form.on("Selling Settings", {
	refresh(frm) {
		if (!frappe.model.can_read("Sales Invoice Naming Settings")) return;
		frm.add_custom_button(__("User-wise Sales Invoice Naming"), () =>
			frappe.set_route("Form", "Sales Invoice Naming Settings")
		);
	},
});
