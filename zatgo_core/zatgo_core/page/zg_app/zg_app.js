// ZatGo > Apps > <app>: the page behind each entry of the ZatGo sidebar's "Apps" section.
// Route: /desk/zg-app/<route key>[/<tab>] (route key = slug of the app label, e.g. zatgo-vansalex). Data: zatgo_core.api.v1.app_page.get_app_page -- what a user may see is
// decided on the server; this file only draws it. Tabs: "Overview" is this page; a settings tab opens that
// settings form on its tab (the form draws the same bar, see public/js/zg_app_tabs.js).
frappe.pages["zg-app"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("ZatGo"),
		single_column: true,
	});
	const root = document.createElement("div");
	root.className = "zg-app";
	page.main[0].appendChild(root);
	page.set_secondary_action(__("Refresh"), () => show(true), "refresh");

	const state = { key: null, data: null, seq: 0 };

	// DOM builder: text goes in as text nodes, never as HTML.
	const h = (tag, props, ...kids) => {
		const el = document.createElement(tag);
		for (const [k, v] of Object.entries(props || {})) {
			if (v === false || v == null) continue;
			if (k === "class") el.className = v;
			else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
			else el.setAttribute(k, v === true ? "" : v);
		}
		kids.flat().forEach((c) => c != null && el.append(c));
		return el;
	};

	// frappe.call returns a jQuery promise (no .catch/.finally chain): wrap it in a native Promise. Our own
	// failures arrive as {success:false, error:{code,message}} and are thrown as Errors carrying the code.
	const call = (method, args) =>
		Promise.resolve(frappe.call({ method: `zatgo_core.api.v1.app_page.${method}`, args: args || {} })).then((r) => {
			const m = r.message;
			if (m && m.success === false) {
				const e = new Error((m.error && m.error.message) || __("Request failed"));
				e.code = m.error && m.error.code;
				throw e;
			}
			return m && m.data !== undefined ? m.data : m;
		});

	// frappe.require cannot load a URL with a ?v= cache-buster (it picks the handler by extension).
	const loadCss = (href) =>
		new Promise((resolve) => {
			if (!href || document.querySelector("link[data-zg-app]")) return resolve();
			const link = h("link", { rel: "stylesheet", href, "data-zg-app": "" });
			link.addEventListener("load", resolve);
			link.addEventListener("error", resolve);
			document.head.append(link);
			setTimeout(resolve, 2000);
		});

	// The sidebar is not built when this URL is opened directly (reload, bookmark): show ZatGo's.
	const ensureSidebar = (attempt = 0) => {
		try {
			const sb = frappe.app && frappe.app.sidebar;
			if (sb && (sb.sidebar_title !== "ZatGo" || !document.querySelector(".sidebar-item-container"))) {
				sb.setup("ZatGo");
			} else if (!sb && attempt < 5) {
				setTimeout(() => ensureSidebar(attempt + 1), 400);
			}
		} catch (e) {
			/* the page works without it */
		}
	};

	const iconEl = (name) => {
		const span = h("span", { class: "zg-app__icon", "aria-hidden": "true" });
		if (/^[a-z0-9-]+$/.test(name || "")) span.innerHTML = frappe.utils.icon(name, "md");
		return span;
	};

	const href = (item) => {
		const args = { type: item.type, name: item.name };
		if (item.doc_view) args.doc_view = item.doc_view;
		if (item.type === "Report") {
			args.is_query_report = item.is_query_report;
			args.report_ref_doctype = item.report_ref_doctype;
		}
		return frappe.utils.generate_route(args);
	};

	const tabBar = (d, active) => {
		const base = `/desk/zg-app/${d.app.route_key}`;
		const items = d.tabs.map((t) => {
			const isOverview = t.kind === "overview";
			const url = isOverview
				? base
				: frappe.utils.generate_route({ type: "DocType", name: t.doctype, tab: t.tab || undefined });
			const on = isOverview && active === "overview";
			return h(
				"li",
				{ class: "nav-item", role: "presentation" },
				h(
					"a",
					{
						class: "nav-link" + (on ? " active" : ""),
						href: url,
						role: "tab",
						"aria-selected": on ? "true" : "false",
						"data-zg-tab": t.key,
					},
					__(t.label)
				)
			);
		});
		return h("div", { class: "form-tabs-list" }, h("ul", { class: "nav form-tabs", role: "tablist" }, items));
	};

	const overview = (o) => {
		const frag = document.createDocumentFragment();
		if (!o || (!o.shortcuts.length && !o.sections.length)) {
			frag.append(h("div", { class: "zg-app__empty" }, h("p", null, __("Nothing to show here for your role."))));
			return frag;
		}
		if (o.shortcuts.length) {
			frag.append(
				h(
					"div",
					{ class: "zg-app__chips" },
					o.shortcuts.map((s) => h("a", { class: "zg-app__chip", href: href(s) }, __(s.label)))
				)
			);
		}
		if (o.sections.length) {
			frag.append(
				h(
					"div",
					{ class: "zg-app__cards" },
					o.sections.map((section) =>
						h(
							"div",
							{ class: "zg-app__card" },
							h("h3", null, __(section.label)),
							h(
								"ul",
								null,
								section.links.map((l) => h("li", null, h("a", { class: "zg-app__link", href: href(l) }, __(l.label))))
							)
						)
					)
				)
			);
		}
		return frag;
	};

	const message = (title, body, d) =>
		h(
			"div",
			{ class: "zg-app__empty", role: "status" },
			h("p", null, h("strong", null, title)),
			h("p", null, body),
			d && d.link ? h("a", { href: d.link.href }, d.link.label) : null
		);

	const draw = (d, tab) => {
		page.set_title(d.app.label);
		// Frappe registers a page's breadcrumb for the first route it was opened on only; every app has its own route.
		frappe.breadcrumbs.add({ type: "Custom", label: __(d.app.label), route: frappe.get_route_str() });
		const head = h(
			"div",
			{ class: "zg-app__head" },
			iconEl(d.app.icon),
			h(
				"div",
				{ class: "zg-app__title" },
				h("h2", null, d.app.label),
				d.app.description ? h("p", { class: "zg-app__desc" }, __(d.app.description)) : null
			),
			h(
				"div",
				{ class: "zg-app__pills" },
				h("span", { class: "zg-app__pill", "data-tone": "good" }, __("Enabled")),
				h("span", { class: "zg-app__pill" }, `v${d.app.version}`),
				d.can_manage ? h("a", { class: "zg-app__pill", href: d.hub }, __("Manage in ZatGo Apps")) : null
			)
		);
		const warn = d.warnings.length
			? h(
					"div",
					{ class: "zg-app__warn", role: "status" },
					h("strong", null, __("Needs attention")),
					h("ul", null, d.warnings.map((w) => h("li", null, w)))
			  )
			: null;
		// replaceChildren writes a null argument as the text "null": leave the absent parts out.
		const parts = [head, warn, d.tabs.length > 1 ? tabBar(d, "overview") : null, overview(d.overview)];
		root.replaceChildren(...parts.filter(Boolean));
	};

	const fail = (e) => {
		const hub = frappe.user.has_role("System Manager") ? { href: "/desk/zg-app-hub", label: __("Open ZatGo Apps") } : null;
		const titles = {
			app_off: __("This app is switched off on this site"),
			forbidden: __("You do not have access to this app"),
			not_found: __("There is no such app"),
		};
		root.replaceChildren(message(titles[e.code] || __("Could not load this app"), e.message || "", { link: hub }));
	};

	const show = (force) => {
		const route = frappe.get_route();
		const key = (route[1] || "").toLowerCase();
		const tab = route[2] || "";
		if (!key) return frappe.set_route("zg-app-hub");
		ensureSidebar();
		const ready = !force && state.data && state.key === key;
		const go = (d) => {
			// /zg-app/<app>/<settings tab key>: straight to that tab of the settings form.
			const t = tab && d.tabs.find((x) => x.kind === "settings" && x.key === tab);
			// A user who may open the settings but not the app's Workspace has no Overview: open the first tab.
			const first = !tab && !d.tabs.some((x) => x.kind === "overview") && d.tabs[0];
			const target = t || first;
			if (target) {
				return frappe.set_route(
					frappe.utils.generate_route({ type: "DocType", name: target.doctype, tab: target.tab || undefined })
				);
			}
			draw(d, "overview");
		};
		if (ready) return go(state.data);
		const seq = ++state.seq;
		root.setAttribute("aria-busy", "true");
		root.replaceChildren(h("div", { class: "zg-app__empty" }, __("Loading...")));
		call("get_app_page", { key })
			.then((d) =>
				loadCss(d.css).then(() => {
					if (seq !== state.seq) return;
					state.key = key;
					state.data = d;
					go(d);
				})
			)
			.catch((e) => {
				if (seq !== state.seq) return;
				state.data = null;
				// A server exception rejects with frappe.call's response, which Frappe has already shown in its own
				// dialog; the page still says it could not load.
				fail(e instanceof Error ? e : { code: "error", message: "" });
			})
			.then(() => {
				if (seq === state.seq) root.removeAttribute("aria-busy");
			});
	};

	wrapper.zg_show = show;
};

frappe.pages["zg-app"].on_page_show = function (wrapper) {
	if (wrapper.zg_show) wrapper.zg_show(false);
};
