/**
 * ZatGo Core Desk helpers (Vue 3 Desk compatible).
 * Exposes boot payload and lightweight client utilities.
 */
frappe.provide("zatgo.core");

zatgo.core = {
	version: "0.1.0",

	boot() {
		return (frappe.boot && frappe.boot.zatgo_core) || {};
	},

	isFeatureEnabled(flagKey) {
		const flags = (this.boot().feature_flags || []);
		const row = flags.find((f) => f.flag_key === flagKey);
		if (!row) return false;
		return ["Enabled", "Beta", "Experimental", "Internal"].includes(row.status);
	},

	async getSystemSettings() {
		const r = await frappe.call({
			method: "zatgo_core.api.v1.settings.get_system_settings",
		});
		return r.message && r.message.data;
	},

	async clearCache() {
		return frappe.call({
			method: "zatgo_core.api.v1.settings.clear_cache",
			freeze: true,
			freeze_message: __("Clearing ZatGo Core cache..."),
		});
	},

	async syncApps() {
		return frappe.call({
			method: "zatgo_core.api.v1.apps.sync_application_registry",
			freeze: true,
			freeze_message: __("Syncing application registry..."),
		});
	},
};

$(document).on("app_ready", function () {
	const boot = zatgo.core.boot();
	if (boot.system && boot.system.maintenance_mode) {
		frappe.show_alert(
			{
				message: __("ZatGo maintenance mode is enabled"),
				indicator: "orange",
			},
			8
		);
	}
});
