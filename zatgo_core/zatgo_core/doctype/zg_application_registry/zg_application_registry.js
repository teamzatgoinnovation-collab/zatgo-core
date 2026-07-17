// Copyright (c) 2026, ZatGo Innovation and contributors
// License: MIT
// Legacy list DocType — prefer ZG Application Settings (site Single).

frappe.listview_settings["ZG Application Registry"] = {
	onload(listview) {
		listview.page.set_indicator(
			__("Deprecated — use ZG Application Settings"),
			"orange"
		);
		listview.page.add_inner_button(__("Open Application Settings"), () => {
			frappe.set_route("Form", "ZG Application Settings");
		});
	},
};
