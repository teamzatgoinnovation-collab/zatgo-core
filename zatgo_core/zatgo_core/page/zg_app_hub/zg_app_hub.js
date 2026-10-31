// ZatGo overview: every ZatGo app on this site, its state, its switch and where its settings are.
// Data comes from zatgo_core.api.v1.app_hub.get_hub; who may switch is decided on the server.
frappe.pages["zg-app-hub"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("ZatGo Apps"),
		single_column: true,
	});
	const root = document.createElement("div");
	root.className = "zg-app-hub";
	page.main[0].appendChild(root);
	page.set_secondary_action(__("Refresh"), () => render(), "refresh");

	// "app" (in-core apps) and "bundled" (modules) are both apps to the user.
	const SECTIONS = [
		{ id: "apps", label: __("Apps"), groups: ["app", "bundled"] },
		{ id: "ui", label: __("Desk appearance"), groups: ["ui"] },
		{ id: "industries", label: __("Industries"), groups: ["industries"] },
		{ id: "core", label: __("Core settings"), groups: ["core"] },
	];
	const STATE_LABEL = { on: __("Enabled"), off: __("Disabled"), always: __("Always on") };

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

	// Our own failure payloads arrive as Errors; a server exception rejects with frappe.call's response,
	// which Frappe has already shown in its own dialog.
	const describe = (e) => (e instanceof Error ? e.message : __("Request failed"));

	// frappe.call returns a jQuery promise (no .catch/.finally chain): wrap it in a native Promise.
	const call = (method, args) =>
		Promise.resolve(frappe.call({ method: `zatgo_core.api.v1.app_hub.${method}`, args: args || {} })).then((r) => {
			const m = r.message;
			if (m && m.success === false) {
				throw new Error((m.error && m.error.message) || m.message || __("Request failed"));
			}
			return m && m.data !== undefined ? m.data : m;
		});

	// frappe.require cannot load a URL with a ?v= cache-buster (it picks the handler by extension).
	const loadCss = (href) =>
		new Promise((resolve) => {
			if (!href || document.querySelector("link[data-zg-app-hub]")) return resolve();
			const link = h("link", { rel: "stylesheet", href, "data-zg-app-hub": "" });
			link.addEventListener("load", resolve);
			link.addEventListener("error", resolve);
			document.head.append(link);
			setTimeout(resolve, 2000);
		});

	function stat(value, label, tone) {
		return h(
			"div",
			{ class: "zg-stat", "data-tone": tone || false },
			h("div", { class: "zg-stat__value" }, String(value)),
			h("div", { class: "zg-stat__label" }, label)
		);
	}

	function toggle(app, titleId) {
		const btn = h(
			"button",
			{
				type: "button",
				class: "zg-switch",
				role: "switch",
				"aria-checked": String(app.enabled),
				"aria-labelledby": titleId,
				"data-key": app.key,
			},
			h("span", { class: "zg-switch__track", "aria-hidden": "true" }, h("span", { class: "zg-switch__thumb" })),
			h("span", { class: "zg-switch__text" }, app.enabled ? __("On") : __("Off"))
		);
		btn.addEventListener("click", () => {
			const want = btn.getAttribute("aria-checked") !== "true";
			btn.disabled = true;
			btn.setAttribute("aria-busy", "true");
			call("set_switch", { key: app.key, enabled: want ? 1 : 0 })
				.then(() => {
					frappe.show_alert({
						message: want ? __("{0} switched on", [app.label]) : __("{0} switched off", [app.label]),
						indicator: want ? "green" : "orange",
					});
					return render(app.key);
				})
				.catch((e) => {
					btn.disabled = false;
					btn.removeAttribute("aria-busy");
					if (e instanceof Error) frappe.msgprint(e.message);
				});
		});
		return btn;
	}

	function card(app) {
		const state = !app.has_switch ? "always" : app.enabled ? "on" : "off";
		const titleId = `zg-app-${app.key}`;
		const head = h(
			"div",
			{ class: "zg-card__head" },
			h(
				"div",
				{ class: "zg-card__title" },
				h("h3", { id: titleId }, app.label),
				h("span", { class: "zg-card__version" }, `v${app.version}`)
			),
			app.has_switch ? toggle(app, titleId) : null
		);
		const body = h(
			"div",
			{ class: "zg-card__body" },
			h("span", { class: "zg-pill", "data-state": state }, STATE_LABEL[state]),
			app.description ? h("p", { class: "zg-card__desc" }, app.description) : null,
			app.requires.length ? h("p", { class: "zg-card__meta" }, __("Requires: {0}", [app.requires.join(", ")])) : null,
			app.has_switch && !app.enabled ? h("p", { class: "zg-card__meta" }, __("Off on this site. Its data is kept.")) : null,
			app.warnings.length
				? h(
						"ul",
						{ class: "zg-warnings", role: "status" },
						app.warnings.map((w) => h("li", {}, w))
				  )
				: null
		);
		const links = h(
			"div",
			{ class: "zg-card__links" },
			app.settings.length
				? h("a", { class: "btn btn-primary btn-xs", href: `/desk/zg-settings-map?app=${encodeURIComponent(app.key)}` }, __("Configure"))
				: null,
			app.settings.map((s) => h("a", { class: "btn btn-default btn-xs", href: s.route }, s.label))
		);
		return h("section", { class: "zg-card", "data-state": state, "aria-labelledby": titleId }, head, body, app.settings.length ? links : null);
	}

	function view(hub) {
		const nodes = [];
		const s = hub.summary;
		nodes.push(
			h(
				"div",
				{ class: "zg-summary" },
				stat(s.apps, __("Apps and settings")),
				stat(s.enabled, __("Enabled"), "good"),
				stat(s.disabled, __("Disabled")),
				stat(s.warnings, __("Need attention"), s.warnings ? "warn" : false),
				h("div", { class: "zg-summary__version" }, __("ZatGo version {0}", [hub.version]))
			)
		);
		if (hub.load_errors.length) {
			nodes.push(
				h(
					"div",
					{ class: "zg-banner", role: "alert" },
					h("strong", {}, __("Some app manifests could not be loaded and are not listed:")),
					h("ul", {}, hub.load_errors.map((e) => h("li", {}, e)))
				)
			);
		}
		SECTIONS.forEach((sec) => {
			const apps = hub.apps.filter((a) => sec.groups.includes(a.group));
			if (!apps.length) return;
			nodes.push(h("h2", { class: "zg-section" }, sec.label), h("div", { class: "zg-grid" }, apps.map(card)));
		});
		if (!hub.apps.length) nodes.push(h("p", { class: "zg-empty" }, __("No apps are registered on this site.")));
		return nodes;
	}

	function render(focusKey) {
		root.setAttribute("aria-busy", "true");
		return call("get_hub")
			.then((hub) => loadCss(hub.css).then(() => hub))
			.then((hub) => {
				root.replaceChildren(...view(hub));
				if (focusKey) {
					const again = root.querySelector(`.zg-switch[data-key="${CSS.escape(focusKey)}"]`);
					if (again) again.focus();
				}
			})
			.catch((e) => {
				root.replaceChildren(
					h(
						"div",
						{ class: "zg-banner", role: "alert" },
						h("p", {}, describe(e)),
						h("button", { type: "button", class: "btn btn-default btn-sm", onclick: () => render() }, __("Try again"))
					)
				);
			})
			.finally(() => root.removeAttribute("aria-busy"));
	}
	render();
};
