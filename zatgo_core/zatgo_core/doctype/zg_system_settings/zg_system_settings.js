// Copyright (c) 2026, ZatGo Innovation and contributors
// License: MIT

frappe.ui.form.on("ZG System Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Clear Core Cache"), () => {
			zatgo.core.clearCache().then(() => {
				frappe.show_alert({
					message: __("ZatGo Core cache cleared"),
					indicator: "green",
				});
			});
		});
		frm.add_custom_button(__("Sync Apps"), () => {
			zatgo.core.syncApps().then((r) => {
				const data = r.message && r.message.data;
				frappe.msgprint(
					__("Created {0}, updated {1}", [
						(data && data.created) || 0,
						(data && data.updated) || 0,
					])
				);
			});
		});
	},
});
