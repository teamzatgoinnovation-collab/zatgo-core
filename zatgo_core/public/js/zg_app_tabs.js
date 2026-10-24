// Settings forms of ZatGo apps (VanSaleX Settings, Chat AI Settings, Tracker Settings, Space Settings): an
// "Overview" tab in front of the form's own tabs that returns to the app's page (/desk/zg-app/<route key>), so the
// page and its settings form show one tab bar. Which DocType belongs to which app comes from the server
// (frappe.boot.zatgo_core.app_settings, services/app_page.py). The form's own tabs are Tab Break fields.
(function () {
	if (!window.frappe || !window.$) return;

	const appOf = (doctype) => {
		const map = (frappe.boot && frappe.boot.zatgo_core && frappe.boot.zatgo_core.app_settings) || {};
		return map[doctype];
	};

	// Opened directly (reload, bookmark), Frappe does not know which sidebar belongs to this form.
	const ensureSidebar = () => {
		try {
			const sb = frappe.app && frappe.app.sidebar;
			if (sb && (sb.sidebar_title !== "ZatGo" || !document.querySelector(".sidebar-item-container"))) {
				sb.setup("ZatGo");
			}
		} catch (e) {
			/* the form works without it */
		}
	};

	// The settings form is not a sidebar entry of its own: keep the app's entry (Apps > ZatGo VanSaleX) lit, the
	// way Frappe lights the entry of the open page.
	const highlightApp = (key) => {
		try {
			const sb = frappe.app && frappe.app.sidebar;
			const item = $(`.item-anchor[href="/desk/zg-app/${key}"]`).first().parent();
			if (!sb || !item.length) return;
			if (sb.active_item && !sb.active_item.is(item)) sb.active_item.removeClass("active-sidebar");
			sb.active_item = item;
			item.addClass("active-sidebar");
		} catch (e) {
			/* cosmetic */
		}
	};

	const addOverview = (frm) => {
		const key = appOf(frm.doctype);
		const layout = frm.layout;
		if (!key || !layout || !layout.tab_link_container) return;
		const bar = layout.tab_link_container;

		// Frappe hides the only tab of a one-tab form; with the Overview in front it is a real tab again
		// (Frappe re-hides it on every refresh, and this runs after each one).
		(layout.tabs || [])
			.filter((t) => !t.wrapper.hasClass("hide"))
			.forEach((t) => t.tab_link.removeClass("hide").addClass("show"));

		if (!bar.find("[data-zg-overview]").length) {
			const url = `/desk/zg-app/${key}`;
			const link = $("<a>", {
				class: "nav-link",
				href: url,
				role: "tab",
				"aria-selected": "false",
				"data-zg-overview": "",
				text: __("Overview"),
			});
			// The bar's own delegated click handler treats every .nav-link as one of its tabs.
			link.on("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				frappe.set_route(url);
			});
			$("<li>", { class: "nav-item", role: "presentation" }).append(link).prependTo(bar);
		}
		ensureSidebar();
		highlightApp(key);
	};

	$(document).on("form-refresh", (e, frm) => {
		try {
			if (frm && appOf(frm.doctype)) addOverview(frm);
		} catch (err) {
			console.error("zg_app_tabs", err); // eslint-disable-line no-console
		}
	});
})();
