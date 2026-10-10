frappe.ui.form.on("AI REST Tool", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Connection"), () => {
				frm.call("test_connection").then((r) => {
					frm.reload_doc();
					const ok = r && r.message && r.message.ok;
					frappe.show_alert({
						message: ok ? __("Connection OK") : __("Connection failed"),
						indicator: ok ? "green" : "red",
					});
				});
			});
		}
	},
});
