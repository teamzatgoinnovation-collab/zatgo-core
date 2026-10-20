// IFRS Report Templates switch (ZG System Settings > Enable IFRS Report Templates; services/report_templates.py).
// Off: the Report Template filter is hidden on Balance Sheet / Profit and Loss Statement / Cash Flow, so the
// classic report is the only one a user can pick. The server drops the filter too.
(function () {
	const REPORTS = ["Balance Sheet", "Profit and Loss Statement", "Cash Flow"];

	function on() {
		const system = (frappe.boot.zatgo_core && frappe.boot.zatgo_core.system) || {};
		return !!system.enable_ifrs_reports;
	}

	function patch() {
		const QR = frappe.views && frappe.views.QueryReport;
		if (!QR) return false;
		if (QR.prototype._zg_ifrs_patched) return true;
		QR.prototype._zg_ifrs_patched = true;
		const original = QR.prototype.setup_filters;
		QR.prototype.setup_filters = function () {
			if (!on() && REPORTS.includes(this.report_name) && this.report_settings && this.report_settings.filters) {
				this.report_settings.filters = this.report_settings.filters.map((f) =>
					f.fieldname === "report_template" ? Object.assign({}, f, { hidden: 1, default: "" }) : f
				);
			}
			return original.apply(this, arguments);
		};
		// A template carried in by a URL / saved filter must not switch ERPNext's formatter and print path to template mode.
		const original_value = QR.prototype.get_filter_value;
		QR.prototype.get_filter_value = function (fieldname) {
			if (fieldname === "report_template" && !on() && REPORTS.includes(this.report_name)) return "";
			return original_value.apply(this, arguments);
		};
		return true;
	}

	if (!patch()) $(document).one("startup", patch);
})();
