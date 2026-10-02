// User-wise Sales Invoice naming series. The server enforces these on every
// Sales Invoice insert (zatgo_core/events/sales_invoice_naming.py); this form
// only edits the mapping.

frappe.ui.form.on("ZG Sales Invoice Naming Settings", {
	setup(frm) {
		frm.set_query("user", "rules", () => ({ filters: { enabled: 1 } }));
	},
	refresh(frm) {
		set_series_options(frm, (frm.doc.__onload || {}).sales_invoice_series || []);
		frm.set_intro(
			__(
				"Each user's Sales Invoices and Sales Returns are numbered from the series below, " +
					"whatever series the invoice or the app sends. Existing invoices keep their numbers."
			)
		);
		if (frappe.model.can_write("Document Naming Settings")) {
			frm.add_custom_button(__("Edit Sales Invoice Series"), () => edit_series(frm));
		}
	},
});

frappe.ui.form.on("ZG Sales Invoice Naming Rule", {
	rules_add(frm, cdt, cdn) {
		const company = frappe.defaults.get_user_default("Company");
		if (company) frappe.model.set_value(cdt, cdn, "company", company);
	},
});

function set_series_options(frm, series) {
	const options = [""].concat(series).join("\n");
	const grid = frm.fields_dict.rules.grid;
	grid.update_docfield_property("normal_series", "options", options);
	grid.update_docfield_property("return_series", "options", options);
}

// Frappe's own Document Naming dialog for Sales Invoice, so a series can be
// added without leaving this page.
function edit_series(frm) {
	new frappe.ui.NamingSeriesDialog({
		doctype: "Sales Invoice",
		title: __("Sales Invoice Naming Series"),
		on_update: ({ naming_series_options }) => {
			const series = naming_series_options
				.split("\n")
				.map((s) => s.trim())
				.filter(Boolean);
			frm.doc.__onload = Object.assign(frm.doc.__onload || {}, { sales_invoice_series: series });
			set_series_options(frm, series);
		},
	}).show();
}
