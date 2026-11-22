// ZatGo ERP workspace: count + total per document, top selling product, top category.
// Runs in a Custom HTML Block (shadow DOM): `root_element` is the shadow root. Data: zatgo_core.api.v1.erp_summary.get
(function () {
	const root = root_element;
	const KEY = "zg_erp_summary_period";
	const ROUTES = {
		"Sales Invoice": "sales-invoice",
		"Purchase Invoice": "purchase-invoice",
		"Sales Order": "sales-order",
		"Purchase Order": "purchase-order",
	};
	const select = root.querySelector(".zgs-period");
	const cards = root.querySelector(".zgs-cards");

	let saved = "all";
	try {
		saved = window.localStorage.getItem(KEY) || "all";
	} catch (e) {
		/* private mode: default */
	}
	select.value = ["all", "year", "month"].includes(saved) ? saved : "all";

	const money = (value, currency) =>
		frappe.format(value || 0, { fieldtype: "Currency", options: currency || undefined }, { only_value: false });
	const esc = (text) => frappe.utils.escape_html(String(text == null ? "" : text));

	function card(doc, currency) {
		const hidden = doc.count === null;
		const link = "/desk/" + ROUTES[doc.doctype];
		return (
			'<a class="zgs-card" href="' + link + '">' +
			'<span class="zgs-name">' + esc(__(doc.doctype)) + "</span>" +
			(hidden
				? '<span class="zgs-muted">—</span>'
				: '<span class="zgs-count">' + esc(doc.count) + "</span>" +
				  '<span class="zgs-total">' + money(doc.total, currency) + "</span>") +
			"</a>"
		);
	}

	function top(el, rows, currency, withQty) {
		if (rows === null) {
			el.innerHTML = '<div class="zgs-muted">—</div>';
			return;
		}
		if (!rows.length) {
			el.innerHTML = '<div class="zgs-muted">' + esc(__("No sales in this period")) + "</div>";
			return;
		}
		const first = rows[0];
		let html =
			'<div class="zgs-first"><span class="zgs-first-name">' + esc(first.label) + "</span>" +
			'<span class="zgs-first-amount">' + money(first.amount, currency) + "</span>" +
			(withQty ? '<span class="zgs-muted">' + esc(Number(first.qty || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })) + " " + esc(__("sold")) + "</span>" : "") +
			"</div>";
		if (rows.length > 1) {
			html += '<ol class="zgs-rest" start="2">';
			rows.slice(1).forEach((r) => {
				html += "<li><span>" + esc(r.label) + "</span><span>" + money(r.amount, currency) + "</span></li>";
			});
			html += "</ol>";
		}
		el.innerHTML = html;
	}

	function load() {
		try {
			window.localStorage.setItem(KEY, select.value);
		} catch (e) {
			/* ignore */
		}
		cards.classList.add("zgs-loading");
		frappe
			.call({ method: "zatgo_core.api.v1.erp_summary.get", args: { period: select.value } })
			.then((r) => {
				const data = (r.message && r.message.data) || {};
				cards.innerHTML = (data.docs || []).map((d) => card(d, data.currency)).join("");
				top(root.querySelector(".zgs-products .zgs-top-body"), data.top_products, data.currency, true);
				top(root.querySelector(".zgs-categories .zgs-top-body"), data.top_categories, data.currency, false);
			})
			.always(() => cards.classList.remove("zgs-loading"));
	}

	select.addEventListener("change", load);
	load();
})();
