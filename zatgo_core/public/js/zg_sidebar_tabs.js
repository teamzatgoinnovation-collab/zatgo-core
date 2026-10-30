// A settings form is listed in an app's sidebar once per tab (Settings > Payments / Sales & Warehouse ...): all
// those items share one path and differ only by the #tab, which Frappe's sidebar ignores -- it lights the LAST item
// whose path matches. Here the item of the open tab is the lit one: the tab named by the URL hash, the one just
// clicked on the form, else the first.
//
// Opened directly (reload, bookmark) the form may also get another sidebar that lists it (the module's own): the
// settings form of an app always shows that app's sidebar (frappe.boot.zatgo_core.settings_sidebars).
(function () {
	if (!window.frappe || !window.$) return;

	const split = (href) => {
		const [path, tab] = decodeURIComponent(href || "").split("?")[0].split("#");
		return { path: path.replace(/\/$/, ""), tab: tab || "" };
	};

	const highlight = (tab) => {
		try {
			const here = decodeURIComponent(window.location.pathname).replace(/\/$/, "");
			const same = $(".item-anchor")
				.toArray()
				.filter((a) => split($(a).attr("href")).path === here && split($(a).attr("href")).tab);
			if (same.length < 2) return;
			const want = tab || window.location.hash.replace("#", "");
			const pick = same.find((a) => split($(a).attr("href")).tab === want) || same[0];
			same.forEach((a) => $(a).parent().removeClass("active-sidebar"));
			$(pick).parent().addClass("active-sidebar");
			if (frappe.app && frappe.app.sidebar) frappe.app.sidebar.active_item = $(pick).parent();
		} catch (e) {
			/* the highlight is cosmetic */
		}
	};

	const showAppSidebar = () => {
		try {
			const map = (frappe.boot.zatgo_core || {}).settings_sidebars || {};
			const name = frappe.get_route().map((p) => map[decodeURIComponent(p)]).find(Boolean);
			const sb = frappe.app && frappe.app.sidebar;
			if (name && sb && sb.sidebar_title !== name && frappe.boot.workspace_sidebar_item[name.toLowerCase()]) sb.setup(name);
		} catch (e) {
			/* the form works with whichever sidebar Frappe chose */
		}
	};

	// Frappe sets its own highlight on route changes, a moment after them: run after it.
	const later = (tab) =>
		[0, 150, 600].forEach((ms) =>
			setTimeout(() => {
				showAppSidebar();
				highlight(tab);
			}, ms)
		);

	// Capture phase: the form's own tab handler may stop the event before it reaches a delegated listener.
	document.addEventListener(
		"click",
		(e) => {
			const link = e.target.closest && e.target.closest(".form-tabs .nav-link");
			if (link) later(link.getAttribute("data-fieldname"));
		},
		true
	);
	$(window).on("hashchange", () => later());
	$(document).on("page-change form-refresh", () => later());
	if (frappe.router && frappe.router.on) frappe.router.on("change", () => later());
	later();
})();
