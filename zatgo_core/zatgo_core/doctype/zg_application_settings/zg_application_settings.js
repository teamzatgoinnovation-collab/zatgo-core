// Copyright (c) 2026, ZatGo Innovation and contributors
// License: MIT

frappe.ui.form.on("ZG Application Settings", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Configure Electron, Flutter, and Web client apps for this site. This is not the Frappe custom-app list."
			)
		);
		frm.add_custom_button(__("Seed Default Clients"), () => {
			frappe.call({
				method: "zatgo_core.api.v1.apps.seed_default_client_apps",
				freeze: true,
				callback(r) {
					frm.reload_doc();
					const data = r.message && r.message.data;
					frappe.show_alert({
						message: __("Seeded {0} client apps", [(data && data.seeded) || 0]),
						indicator: "green",
					});
				},
			});
		});
	},
});
