// Phone layout for Desk child tables (css/zg_mobile_forms.css), on every site.
// While the window is phone-wide (< 768px, Frappe's own frappe.utils.is_xs() cut-off) this sets
// html.zg-grid-cards, which turns every grid row into a card, and gives each grid cell a
// data-zg-label with its column heading, which the card shows above the value. The heading is
// copied from the grid's own header row, so it is already translated and follows the user's
// own column settings. Purely visual: no Frappe code is patched and no data is touched.
(function () {
	if (window.zg_mobile_forms_loaded) return;
	window.zg_mobile_forms_loaded = true;

	const mq = window.matchMedia("(max-width: 767.98px)");
	const CELLS = ".form-grid .grid-body .grid-static-col[data-fieldname]:not([data-zg-label])";

	function heading(cell) {
		const grid = cell.closest(".form-grid");
		const name = cell.getAttribute("data-fieldname");
		const head = grid && grid.querySelector(
			`.grid-heading-row .grid-static-col[data-fieldname="${CSS.escape(name)}"] .static-area`
		);
		const text = head && head.textContent.trim();
		if (text) return text;
		const df = window.jQuery && window.jQuery(cell).data("df");
		return (df && df.label && (window.__ ? __(df.label, null, df.parent) : df.label)) || "";
	}

	function label_cells() {
		document.querySelectorAll(CELLS).forEach((cell) => {
			cell.setAttribute("data-zg-label", heading(cell));
		});
	}

	let queued = false;
	const observer = new MutationObserver(() => {
		if (queued) return;
		queued = true;
		requestAnimationFrame(() => {
			queued = false;
			label_cells();
		});
	});

	function apply() {
		document.documentElement.classList.toggle("zg-grid-cards", mq.matches);
		observer.disconnect();
		if (mq.matches && document.body) {
			label_cells();
			observer.observe(document.body, { childList: true, subtree: true });
		}
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", apply);
	} else {
		apply();
	}
	if (mq.addEventListener) mq.addEventListener("change", apply);
	else if (mq.addListener) mq.addListener(apply);
})();
