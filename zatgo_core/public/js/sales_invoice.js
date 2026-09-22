// Payment Type UX hint for Sales Invoice (custom_payment_type,
// patches/v0_2_2/add_payment_type_field.py). Purely visual -- the actual
// Cash/Credit handling lives server-side in
// zatgo_core.services.sales_invoice_payment_service.

frappe.ui.form.on("Sales Invoice", {
	custom_payment_type(frm) {
		show_payment_type_hint(frm);
	},
	refresh(frm) {
		show_payment_type_hint(frm);
	},
});

function show_payment_type_hint(frm) {
	frm.dashboard.clear_headline();

	if (frm.doc.custom_payment_type === "Cash") {
		frm.dashboard.set_headline_alert(
			"Cash — payment will be collected immediately. Submitting will " +
				"auto-create and submit a Payment Entry for the full amount.",
			"green"
		);
	} else if (frm.doc.custom_payment_type === "Credit") {
		frm.dashboard.set_headline_alert(
			"Credit — no payment will be collected now. The amount will " +
				"remain outstanding after submit.",
			"orange"
		);
	}
}
