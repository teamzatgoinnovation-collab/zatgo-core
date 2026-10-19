// Stock Summary: add a Company filter and offer only warehouses that hold
// stock (events/stock_summary.py). ERPNext's own page script runs first.

(function () {
	const page_def = frappe.pages["stock-balance"];
	const original = page_def && page_def.on_page_load;
	if (!original) return;
	page_def.on_page_load = function (wrapper) {
		original(wrapper);
		const page = wrapper.page;
		page.company_field = page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			change() {
				page.warehouse_field.set_value("");
			},
		});
		page.warehouse_field.get_query = () => ({
			query: "zatgo_core.events.stock_summary.live_stock_warehouses",
			filters: { company: page.company_field.get_value() },
		});
	};
})();
