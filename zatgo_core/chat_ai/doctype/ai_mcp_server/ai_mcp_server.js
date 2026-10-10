frappe.ui.form.on("AI MCP Server", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Discover Tools"), () => {
				frm.call("discover_tools").then((r) => {
					frm.reload_doc();
					const n = (r && r.message && r.message.count) || 0;
					frappe.show_alert({
						message: __("Discovered {0} tools", [n]),
						indicator: "green",
					});
				});
			});
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
