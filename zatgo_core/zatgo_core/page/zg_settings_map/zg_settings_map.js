// ZatGo Settings Map: every app's settings with real controls, scope and status, editable in place.
// Data: zatgo_core.api.v1.settings_map.get_map; one change = save_field (the DocType's own save validates and audits it).
// App switches go through app_hub.set_switch. Text is always set as text, never as HTML.
frappe.pages["zg-settings-map"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("ZatGo Settings Map"), single_column: true });
	const root = document.createElement("div");
	root.className = "zgs";
	page.main[0].appendChild(root);
	page.set_secondary_action(__("Refresh"), () => render(), "refresh");

	const STATUS = {
		enforced: __("Enforced"),
		read: __("Read by client"),
		info: __("Informational"),
		unwired: __("Not wired yet"),
	};
	const STATUS_HELP = {
		enforced: __("The server reads it and acts on it"),
		read: __("A client app reads it; the server does not enforce it"),
		info: __("Stored, but no code acts on it"),
		unwired: __("Stored or served, but nothing uses it yet"),
	};
	const ICONS = {
		site: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 0c2.5 2.4 3.8 5.4 3.8 9s-1.3 6.6-3.8 9c-2.5-2.4-3.8-5.4-3.8-9S9.500 5.400 12 3zM3 12h18",
		company: "M4 21V7l8-4 8 4v14M9 21v-6h6v6M8 10h2M14 10h2",
		branch: "M7 4v10a4 4 0 0 0 4 4h6M7 4a2 2 0 1 0 0 .01M17 18a2 2 0 1 0 0 .01M7 10h6a4 4 0 0 1 4 4",
		user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
		role: "M12 3l8 3v6c0 5-3.500 8-8 9-4.500-1-8-4-8-9V6l8-3z",
		device: "M8 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM11 18h2",
		warehouse: "M3 9l9-5 9 5v11H3zM8 20v-6h8v6",
	};

	const h = (tag, props, ...kids) => {
		const el = document.createElement(tag);
		for (const [k, v] of Object.entries(props || {})) {
			if (v === false || v == null) continue;
			if (k === "class") el.className = v;
			else if (k === "style") el.setAttribute("style", v);
			else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
			else el.setAttribute(k, v === true ? "" : v);
		}
		kids.flat().forEach((c) => c != null && c !== false && el.append(c));
		return el;
	};
	const icon = (name) => {
		const ns = "http://www.w3.org/2000/svg";
		const svg = document.createElementNS(ns, "svg");
		svg.setAttribute("viewBox", "0 0 24 24");
		svg.setAttribute("aria-hidden", "true");
		svg.setAttribute("class", "zgs-ico");
		const p = document.createElementNS(ns, "path");
		p.setAttribute("d", ICONS[name] || ICONS.site);
		svg.append(p);
		return svg;
	};

	// frappe.call returns a jQuery promise: wrap it. Our failures arrive as { success: false }.
	const call = (module, method, args) =>
		Promise.resolve(frappe.call({ method: `zatgo_core.api.v1.${module}.${method}`, args: args || {}, type: "POST" })).then((r) => {
			const m = r.message;
			if (m && m.success === false) throw new Error((m.error && m.error.message) || __("Request failed"));
			return m && m.data !== undefined ? m.data : m;
		});
	const loadCss = (href) =>
		new Promise((resolve) => {
			if (!href || document.querySelector("link[data-zg-settings-map]")) return resolve();
			const link = h("link", { rel: "stylesheet", href, "data-zg-settings-map": "" });
			link.addEventListener("load", resolve);
			link.addEventListener("error", resolve);
			document.head.append(link);
			setTimeout(resolve, 2000);
		});

	let state = { data: null, filter: new URLSearchParams(location.search).get("app") || "" };

	function vars(p) {
		const d = p.dark;
		return `--zgs-a-l:${p.accent};--zgs-on-l:${p.on_accent};--zgs-tint-l:${p.tint};--zgs-ink-l:${p.ink};` +
			`--zgs-a-d:${d.accent};--zgs-on-d:${d.on_accent};--zgs-tint-d:${d.tint};--zgs-ink-d:${d.ink}`;
	}
	const pill = (kind, key, label, title) =>
		h("span", { class: `zgs-pill zgs-pill--${kind}`, "data-k": key, title: title || false }, kind === "scope" ? icon(key) : null, label);

	function say(msg, ok) {
		frappe.show_alert({ message: msg, indicator: ok ? "green" : "red" });
	}

	// One field: control -> save -> reflect the saved value (or put the old one back and say why).
	function field(dt, row) {
		const err = h("div", { class: "zgs-err", role: "alert" });
		const box = h("div", { class: "zgs-ctl" });
		const wrap = h(
			"div",
			{ class: "zgs-row", "data-status": row.status, "data-field": row.fieldname },
			h("div", { class: "zgs-row__top" },
				h("div", { class: "zgs-row__label" }, row.label),
				h("div", { class: "zgs-row__badges" },
					pill("scope", row.scope, state.data.scopes[row.scope] || row.scope),
					pill("status", row.status, STATUS[row.status], STATUS_HELP[row.status]),
					row.control === "switch" && !row.stored ? pill("plain", "default", __("Default"), __("Nothing is stored; the default applies")) : null)),
			box,
			row.description ? h("div", { class: "zgs-row__help" }, row.description) : null,
			row.note ? h("div", { class: "zgs-row__help" }, row.note) : null,
			row.enforced_by ? h("div", { class: "zgs-row__where" }, __("Used by {0}", [row.enforced_by])) : null,
			err
		);
		let current = row.value;
		const save = (value, undo) => {
			err.textContent = "";
			wrap.setAttribute("aria-busy", "true");
			return call("settings_map", "save_field", { doctype: dt, fieldname: row.fieldname, value })
				.then((r) => {
					current = r.value;
					const def = wrap.querySelector('[data-k="default"]');
					if (def) def.remove(); // it is stored now
					say(r.changed ? __("{0} saved", [row.label]) : __("No change"), true);
				})
				.catch((e) => {
					undo();
					err.textContent = e.message;
				})
				.finally(() => wrap.removeAttribute("aria-busy"));
		};
		const editable = row.writable;
		if (row.control === "switch") {
			const b = h("button", { type: "button", class: "zgs-switch", role: "switch", "aria-checked": String(!!row.value), "aria-label": row.label, disabled: !editable },
				h("span", { class: "zgs-switch__track" }, h("span", { class: "zgs-switch__thumb" })),
				h("span", { class: "zgs-switch__text" }, row.value ? __("On") : __("Off")));
			const paint = (on) => {
				b.setAttribute("aria-checked", String(on));
				b.lastChild.textContent = on ? __("On") : __("Off");
			};
			b.addEventListener("click", () => {
				const want = b.getAttribute("aria-checked") !== "true";
				paint(want);
				save(want ? 1 : 0, () => paint(!want));
			});
			box.append(b);
		} else if (row.control === "choice") {
			const group = h("div", { class: "zgs-choice", role: "radiogroup", "aria-label": row.label });
			const opts = row.options.length ? row.options : [""];
			const paint = (v) =>
				group.querySelectorAll("button").forEach((x) => {
					const on = x.dataset.v === (v || "");
					x.setAttribute("aria-checked", String(on));
					x.tabIndex = on ? 0 : -1; // radio pattern: one tab stop, arrows move
				});
			group.addEventListener("keydown", (e) => {
				const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
				if (!keys[e.key] || !editable) return;
				const all = [...group.querySelectorAll("button")];
				const next = all[(all.indexOf(document.activeElement) + keys[e.key] + all.length) % all.length];
				e.preventDefault();
				next.focus();
				next.click();
			});
			opts.forEach((o) =>
				group.append(h("button", {
					type: "button", role: "radio", class: "zgs-opt", "data-v": o, "aria-checked": String(o === (row.value || "")), disabled: !editable,
					onclick: () => {
						const was = current;
						paint(o);
						save(o, () => paint(was));
					},
				}, o || __("(none)"))));
			paint(row.value);
			box.append(group);
		} else if (row.control === "select") {
			const sel = h("select", { class: "zgs-input", "aria-label": row.label, disabled: !editable },
				row.options.map((o) => h("option", { value: o }, o || __("(none)"))));
			sel.value = row.value || "";
			sel.addEventListener("change", () => {
				const was = current || "";
				save(sel.value, () => (sel.value = was));
			});
			box.append(sel);
		} else if (row.control === "link") {
			const holder = h("div", { class: "zgs-link" });
			box.append(holder);
			if (frappe.ui && frappe.ui.form && frappe.ui.form.make_control && editable) {
				const ctl = frappe.ui.form.make_control({
					df: { fieldtype: "Link", options: row.options, fieldname: row.fieldname, label: row.label, only_input: true,
						change: () => {
							const v = ctl.get_value() || "";
							if (v === (current || "")) return;
							const was = current || "";
							save(v, () => ctl.set_value(was));
						} },
					parent: holder, render_input: true, only_input: true,
				});
				if (ctl.$input) ctl.$input.attr("aria-label", row.label);
				ctl.set_value(row.value || "");
				current = row.value || "";
			} else {
				holder.append(h("input", { class: "zgs-input", value: row.value || "", disabled: !editable, "aria-label": row.label,
					onchange: (e) => { const was = current || ""; save(e.target.value, () => (e.target.value = was)); } }));
			}
		} else if (row.control === "password") {
			box.append(pill("plain", row.is_set ? "set" : "unset", row.is_set ? __("Set") : __("Not set")),
				h("a", { class: "zgs-link-btn", href: dtRoute(dt) }, __("Change in the form")));
		} else if (row.control === "table" || row.control === "attach") {
			box.append(h("span", { class: "zgs-summary" }, row.control === "table" ? row.summary : row.is_set ? __("File attached") : __("No file")),
				h("a", { class: "zgs-link-btn", href: row.open }, __("Open form")));
		} else {
			const multi = row.control === "textarea";
			const type = row.control === "number" ? "number" : "text";
			const input = h(multi ? "textarea" : "input", { class: "zgs-input", type: multi ? false : type, step: row.control === "number" ? "any" : false,
				"aria-label": row.label, disabled: !editable, rows: multi ? 3 : false });
			input.value = row.value == null ? "" : row.value;
			input.addEventListener("change", () => {
				const was = current == null ? "" : current;
				save(input.value, () => (input.value = was));
			});
			box.append(input);
		}
		if (!editable) box.append(h("span", { class: "zgs-lock", title: lockWhy(row) }, lockWhy(row)));
		return wrap;
	}
	const dtRoute = (dt) => "/desk/" + frappe.router.slug(dt);
	const lockWhy = (row) =>
		({ read_only: __("Read only"), secret: __("Secret"), table: __("Table"), attachment: __("Attachment"), app_switch: __("App switch") }[row.locked] || __("View only"));

	function doctypeBlock(app, dt) {
		const body = h("div", { class: "zgs-tabbody" });
		const tabs = h("div", { class: "zgs-tabs", role: "tablist" });
		const show = (i) => {
			tabs.querySelectorAll("button").forEach((b, j) => b.setAttribute("aria-selected", String(i === j)));
			body.replaceChildren(...dt.tabs[i].sections.map((s) =>
				h("div", { class: "zgs-section" }, s.label ? h("h4", { class: "zgs-section__title" }, s.label) : null, s.rows.map((r) => field(dt.doctype, r)))));
		};
		dt.tabs.forEach((t, i) => tabs.append(h("button", { type: "button", role: "tab", class: "zgs-tab", onclick: () => show(i) }, t.label)));
		tabs.addEventListener("keydown", (e) => {
			const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
			if (!d) return;
			const all = [...tabs.querySelectorAll("button")];
			const next = all[(all.indexOf(document.activeElement) + d + all.length) % all.length];
			e.preventDefault();
			next.focus();
			next.click();
		});
		show(0);
		return h("div", { class: "zgs-dt" },
			h("div", { class: "zgs-dt__head" }, h("h3", {}, dt.label), h("a", { class: "zgs-link-btn", href: dt.route }, __("Open form")),
				dt.writable ? null : h("span", { class: "zgs-lock" }, __("View only"))),
			dt.note ? h("p", { class: "zgs-note" }, dt.note) : null,
			dt.tabs.length > 1 ? tabs : null,
			body);
	}

	function appSwitch(app) {
		const b = h("button", { type: "button", class: "zgs-switch zgs-switch--lg", role: "switch", "aria-checked": String(app.enabled), "aria-label": app.label },
			h("span", { class: "zgs-switch__track" }, h("span", { class: "zgs-switch__thumb" })),
			h("span", { class: "zgs-switch__text" }, app.enabled ? __("On") : __("Off")));
		b.addEventListener("click", () => {
			const want = b.getAttribute("aria-checked") !== "true";
			b.disabled = true;
			call("app_hub", "set_switch", { key: app.key, enabled: want ? 1 : 0 })
				.then(() => { say(want ? __("{0} switched on", [app.label]) : __("{0} switched off", [app.label]), true); return render(); })
				.then(() => { const again = root.querySelector(`#zgs-${CSS.escape(app.key)} .zgs-switch--lg`); if (again) again.focus(); })
				.catch((e) => { b.disabled = false; say(e.message, false); });
		});
		return b;
	}

	function card(app) {
		const c = app.counts;
		const device = app.device.length
			? h("details", { class: "zgs-device" },
				h("summary", {}, __("On the device")),
				app.device.map((d) => h("div", { class: "zgs-device__client" }, h("h4", {}, d.client),
					h("ul", {}, d.items.map((i) => h("li", {}, h("strong", {}, i.label), " ", h("span", {}, i.note)))))))
			: null;
		return h("section", { class: "zgs-card", id: `zgs-${app.key}`, style: vars(app.palette), "data-on": String(app.enabled), "aria-labelledby": `zgs-t-${app.key}` },
			h("header", { class: "zgs-card__head" },
				h("div", { class: "zgs-tile", "aria-hidden": "true" }, (app.label.replace("ZatGo ", "")[0] || "Z").toUpperCase()),
				h("div", { class: "zgs-card__title" },
					h("h2", { id: `zgs-t-${app.key}` }, app.label),
					h("p", {}, app.description)),
				app.has_switch ? appSwitch(app) : h("span", { class: "zgs-pill zgs-pill--plain" }, __("Always on"))),
			h("div", { class: "zgs-card__meta" },
				app.scopes.map((s) => pill("scope", s, state.data.scopes[s] || s)),
				app.clients.length ? h("span", { class: "zgs-clients" }, __("Used by: {0}", [app.clients.join(", ")])) : null,
				h("span", { class: "zgs-count" }, __("{0} settings, {1} you can edit", [c.fields, c.editable]))),
			app.settings.length ? app.settings.map((dt) => doctypeBlock(app, dt)) : h("p", { class: "zgs-note" }, app.restricted.length
				? __("Your roles cannot open: {0}.", [app.restricted.join(", ")])
				: __("This app has no settings of its own; its switch is above.")),
			device);
	}

	function view(data) {
		const apps = data.apps.filter((a) => !state.filter || a.key === state.filter);
		const chips = h("div", { class: "zgs-chips", role: "group", "aria-label": __("Show app") },
			[{ key: "", label: __("All apps"), palette: null }, ...data.apps].map((a) =>
				h("button", { type: "button", class: "zgs-chip", "aria-pressed": String(state.filter === a.key), style: a.palette ? vars(a.palette) : false,
					onclick: () => { state.filter = a.key; paint(); } }, a.palette ? h("span", { class: "zgs-dot" }) : null, a.label)));
		const legend = h("div", { class: "zgs-legend" }, Object.keys(STATUS).map((k) => h("span", { class: "zgs-legend__item" }, pill("status", k, STATUS[k]), h("small", {}, STATUS_HELP[k]))));
		return [h("div", { class: "zgs-intro" }, h("p", {}, __("Every app's settings in one place. Change a value here and it is saved at once; the same checks as the app's own form apply.")), legend), chips,
			...apps.map(card), apps.length ? null : h("p", { class: "zgs-note" }, __("Nothing to show."))];
	}
	function paint() {
		root.replaceChildren(...view(state.data));
		const t = state.filter && root.querySelector(`#zgs-${CSS.escape(state.filter)}`);
		if (t) t.scrollIntoView({ block: "start" });
	}
	function render() {
		root.setAttribute("aria-busy", "true");
		return call("settings_map", "get_map")
			.then((data) => loadCss(data.css).then(() => data))
			.then((data) => { state.data = data; paint(); })
			.catch((e) => root.replaceChildren(h("div", { class: "zgs-banner", role: "alert" }, e.message,
				h("button", { type: "button", class: "btn btn-default btn-sm", onclick: () => render() }, __("Try again")))))
			.finally(() => root.removeAttribute("aria-busy"));
	}
	render();
	// Coming back from "Open form": show what the form saved, not the first load.
	let first = true;
	frappe.pages["zg-settings-map"].on_page_show = () => {
		if (first) first = false;
		else render();
	};
};
