// Copyright (c) 2026, ZatGo Innovation and contributors
// License: MIT
frappe.ui.form.on("AI Scheduled Task", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Run now"), () => {
			frappe.call({
				method: "zatgo_core.chat_ai.api.tasks.run_now",
				args: { name: frm.doc.name },
				callback(r) {
					const m = r.message || {};
					frappe.show_alert({ message: m.ok ? __("Queued: results arrive as a notification.") : m.error, indicator: m.ok ? "green" : "orange" });
					frm.reload_doc();
				},
			});
		});
		if (frm.doc.session) {
			frm.add_custom_button(__("Open conversation"), () => frappe.set_route("Form", "AI Chat Session", frm.doc.session));
		}
	},
});
