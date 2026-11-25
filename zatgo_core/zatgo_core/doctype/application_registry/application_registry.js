// Copyright (c) 2026, ZatGo Innovation and contributors
// License: MIT
// Legacy list DocType — prefer Application Settings (site Single).

frappe.listview_settings["Application Registry"] = {
	onload(listview) {
		listview.page.set_indicator(
			__("Deprecated — use Application Settings"),
			"orange"
		);
		listview.page.add_inner_button(__("Open Application Settings"), () => {
			frappe.set_route("Form", "Application Settings");
		});
	},
};
