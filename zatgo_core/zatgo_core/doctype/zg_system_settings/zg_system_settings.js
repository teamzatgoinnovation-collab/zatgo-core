// Copyright (c) 2026, ZatGo Innovation and contributors
// License: MIT

frappe.ui.form.on("ZG System Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Clear ZatGo Cache"), () => {
			frappe.call({ method: "zatgo_core.api.v1.settings.clear_cache" }).then(() => {
				frappe.show_alert({
					message: __("ZatGo cache cleared"),
					indicator: "green",
				});
			});
		});
		// Re-reads every app's manifest into the registry client apps use (the registry mirrors the
		// switches above; it is refreshed on every switch change and on migrate as well).
		frm.add_custom_button(__("Refresh App Registry"), () => {
			frappe.call({ method: "zatgo_core.api.v1.config.seed_bundled_manifests" }).then((r) => {
				const data = r.message && r.message.data;
				frappe.msgprint(
					__("Registered {0} apps, {1} changed", [
						(data && data.registered) || 0,
						(data && data.changed) || 0,
					])
				);
			});
		});
	},
});
