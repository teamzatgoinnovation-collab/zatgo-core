// ZatGo Editions: build and inspect commercial editions (docs/licensing.md).
// Data and every rule come from zatgo_core.api.v1.licensing.editions; the Edition controller decides who may
// change what (licence issuer site + System Manager). Elsewhere this page is read-only.
frappe.pages["zg-edition-builder"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("ZatGo Editions"), single_column: true });
	const root = document.createElement("div");
	root.className = "zg-eb";
	page.main[0].appendChild(root);

	const API = "zatgo_core.api.v1.licensing.editions.";
	const STATUS_TONE = { Active: "green", Draft: "orange", Archived: "gray" };
	const PLATFORM_LABEL = { desk: __("ERPNext Desk"), desktop: __("Desktop apps"), mobile: __("Mobile apps") };

	// DOM builder: text goes in as text nodes, never as HTML.
	const h = (tag, props, ...kids) => {
		const el = document.createElement(tag);
		for (const [k, v] of Object.entries(props || {})) {
			if (v === false || v == null) continue;
			if (k === "class") el.className = v;
			else if (k === "value") el.value = v;
			else if (k === "checked") el.checked = !!v;
			else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
			else el.setAttribute(k, v === true ? "" : v);
		}
		kids.flat().forEach((c) => c != null && c !== false && el.append(c));
		return el;
	};

	// frappe.call returns a jQuery promise: wrap it. A server error has already been shown by Frappe.
	const call = (method, args, type) =>
		Promise.resolve(frappe.call({ method: API + method, args: args || {}, type: type || "GET" })).then((r) => {
			const m = r && r.message;
			if (m && m.success === false) throw new Error((m.error && m.error.message) || __("Request failed"));
			return m && m.data !== undefined ? m.data : m;
		});
	const post = (method, args) => call(method, args, "POST");
	const fail = (e) => {
		if (e instanceof Error) frappe.msgprint(e.message);
	};

	const loadCss = (href) =>
		new Promise((resolve) => {
			if (!href || document.querySelector("link[data-zg-eb]")) return resolve();
			const link = h("link", { rel: "stylesheet", href, "data-zg-eb": "" });
			link.addEventListener("load", resolve);
			link.addEventListener("error", resolve);
			document.head.append(link);
			setTimeout(resolve, 2000);
		});

	const S = {
		reg: null, // modules, features, ... from get_builder
		editions: [],
		canEdit: false,
		isIssuer: false,
		filter: "all",
		search: "",
		cfg: null, // working copy of the open edition
		savedHash: null,
		isNew: false,
		inspection: null,
	};
	const featureById = () => Object.fromEntries(S.reg.features.map((f) => [f.id, f]));
	const snapshot = (cfg) => JSON.stringify(cfg);
	const dirty = () => S.cfg && snapshot(S.cfg) !== S.savedHash;

	// -- toolbar ---------------------------------------------------------------------------------------------
	function toolbar() {
		page.clear_primary_action();
		page.clear_menu();
		if (S.canEdit) {
			page.set_primary_action(__("Save"), save, "check");
			page.add_menu_item(__("New edition"), () => guard(newEdition));
			page.add_menu_item(__("Import edition file"), importFile);
		}
		if (S.cfg && !S.isNew) {
			if (S.canEdit) {
				page.add_menu_item(__("Duplicate"), duplicate);
				if (S.cfg.status === "Archived") page.add_menu_item(__("Restore as Draft"), () => setStatus("Draft"));
				else page.add_menu_item(__("Archive"), () => setStatus("Archived"));
			}
			page.add_menu_item(__("Compare with..."), compare);
			page.add_menu_item(__("Export edition file"), exportFile);
		}
		page.set_secondary_action(__("Dependency inspector"), showInspector, "search");
	}

	function guard(next) {
		if (!dirty()) return next();
		frappe.confirm(__("Discard the unsaved changes to this edition?"), next);
	}

	// -- data ------------------------------------------------------------------------------------------------
	function load(editionId) {
		root.setAttribute("aria-busy", "true");
		return call("get_builder")
			.then((data) => loadCss(data.css).then(() => data))
			.then((data) => {
				S.reg = data;
				S.editions = data.editions;
				S.canEdit = data.can_edit;
				S.isIssuer = data.is_issuer;
				const pick = editionId || (S.cfg && S.cfg.edition_id) || (data.editions[0] && data.editions[0].name);
				return pick ? open(pick) : (S.cfg = null, render());
			})
			.catch((e) => {
				root.replaceChildren(
					h("div", { class: "zg-banner", role: "alert" }, h("p", {}, e instanceof Error ? e.message : __("Could not load editions.")))
				);
			})
			.finally(() => root.removeAttribute("aria-busy"));
	}

	function open(editionId) {
		return call("get_edition", { edition_id: editionId }).then((d) => {
			S.cfg = d.config;
			S.savedHash = snapshot(d.config);
			S.isNew = false;
			S.inspection = d.inspection;
			render();
		});
	}

	function newEdition() {
		S.cfg = {
			edition_id: "",
			edition_name: "",
			description: "",
			status: "Draft",
			version: 1,
			platforms: { desk: 1, desktop: 0, mobile: 0 },
			licence_defaults: { licence_type: "Yearly", duration_days: 365, trial_days: 30, max_users: 5, max_companies: 1 },
			default_roles: [],
			features: {},
		};
		S.savedHash = null;
		S.isNew = true;
		S.inspection = null;
		render();
		reinspect();
	}

	let inspectTimer = null;
	function reinspect() {
		clearTimeout(inspectTimer);
		inspectTimer = setTimeout(() => {
			if (!S.cfg) return;
			post("inspect", { features: JSON.stringify(S.cfg.features), platforms: JSON.stringify(S.cfg.platforms) })
				.then((r) => {
					S.inspection = r;
					renderSide();
				})
				.catch(fail);
		}, 300);
	}

	function changed() {
		toolbar();
		reinspect();
		const flag = root.querySelector(".zg-eb__dirty");
		if (flag) flag.hidden = !dirty();
	}

	// -- actions ---------------------------------------------------------------------------------------------
	function save() {
		if (!S.cfg) return;
		post("save_edition", { config: JSON.stringify(S.cfg) })
			.then((d) => {
				frappe.show_alert({ message: __("Edition {0} saved (version {1})", [d.config.edition_name, d.config.version]), indicator: "green" });
				return load(d.config.edition_id);
			})
			.catch(fail);
	}

	function duplicate() {
		const d = new frappe.ui.Dialog({
			title: __("Duplicate {0}", [S.cfg.edition_name]),
			fields: [
				{ fieldname: "new_id", fieldtype: "Data", label: __("New edition ID"), reqd: 1, description: __("lower case, e.g. sales_plus") },
				{ fieldname: "new_name", fieldtype: "Data", label: __("New edition name"), reqd: 1, default: __("{0} (copy)", [S.cfg.edition_name]) },
			],
			primary_action_label: __("Duplicate"),
			primary_action: (v) =>
				post("duplicate_edition", { edition_id: S.cfg.edition_id, new_id: v.new_id, new_name: v.new_name })
					.then((cfg) => {
						d.hide();
						return load(cfg.edition_id);
					})
					.catch(fail),
		});
		d.show();
	}

	function setStatus(status) {
		const go = () => post("set_edition_status", { edition_id: S.cfg.edition_id, status }).then(() => load(S.cfg.edition_id)).catch(fail);
		guard(go);
	}

	function download(name, text) {
		const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
		const a = h("a", { href: url, download: name });
		document.body.append(a);
		a.click();
		a.remove();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}

	function exportFile() {
		call("export_edition", { edition_id: S.cfg.edition_id })
			.then((payload) => download(`${payload.edition_id}.edition.json`, JSON.stringify(payload, null, 1)))
			.catch(fail);
	}

	function importFile() {
		const input = h("input", { type: "file", accept: ".json,application/json", hidden: true });
		input.addEventListener("change", () => {
			const file = input.files && input.files[0];
			input.remove();
			if (!file) return;
			file.text().then((text) =>
				post("preview_import", { payload: text })
					.then((preview) => importDialog(text, preview))
					.catch(fail)
			);
		});
		document.body.append(input);
		input.click();
	}

	function importDialog(text, p) {
		const body = h("div", { class: "zg-eb__dialog" });
		const labels = {
			create: __("A new edition will be created."),
			update: __("The existing edition will be replaced."),
			unchanged: __("The site already has exactly this edition."),
			refuse: __("This file cannot be imported."),
		};
		body.append(h("p", {}, h("strong", {}, `${p.edition_name || "?"} (${p.edition_id || "?"})`), " - ", labels[p.action]));
		if (p.problems.length) body.append(h("ul", { class: "zg-eb__warn" }, p.problems.map((x) => h("li", {}, x))));
		if (p.diff) body.append(diffView(p.diff, __("on this site"), __("in the file")));
		if (p.inspection && p.inspection.warnings.length)
			body.append(h("h5", {}, __("Warnings")), h("ul", { class: "zg-eb__warn" }, p.inspection.warnings.map((w) => h("li", {}, w))));
		const d = new frappe.ui.Dialog({
			title: __("Import edition file"),
			fields: [{ fieldname: "body", fieldtype: "HTML" }],
			primary_action_label: p.action === "update" ? __("Overwrite") : __("Import"),
			primary_action: () =>
				post("import_edition", { payload: text, overwrite: p.conflict ? 1 : 0 })
					.then((r) => {
						d.hide();
						frappe.show_alert({ message: __("Imported {0}", [r.config.edition_name]), indicator: "green" });
						return load(r.config.edition_id);
					})
					.catch(fail),
		});
		d.fields_dict.body.$wrapper[0].replaceChildren(body);
		if (p.action === "refuse" || p.action === "unchanged") d.get_primary_btn().prop("disabled", true);
		d.show();
	}

	function diffView(diff, aLabel, bLabel) {
		const list = (title, items) =>
			items.length ? h("div", {}, h("h5", {}, title), h("ul", {}, items.map((i) => h("li", {}, i)))) : null;
		const names = featureById();
		const label = (id) => (names[id] ? `${names[id].label} (${id})` : id);
		const parts = [
			list(__("Only {0}", [aLabel]), diff.only_a.map(label)),
			list(__("Only {0}", [bLabel]), diff.only_b.map(label)),
			list(__("Different actions"), diff.actions_differ.map((x) => `${label(x.feature)}: ${x.a.join(", ") || __("all")} / ${x.b.join(", ") || __("all")}`)),
			list(__("Platforms"), Object.entries(diff.platforms).map(([k, v]) => `${PLATFORM_LABEL[k]}: ${v[0] ? __("yes") : __("no")} / ${v[1] ? __("yes") : __("no")}`)),
			list(__("Licence defaults"), Object.entries(diff.licence_defaults).map(([k, v]) => `${k}: ${v[0]} / ${v[1]}`)),
		].filter(Boolean);
		return parts.length ? h("div", { class: "zg-eb__diff" }, parts) : h("p", {}, __("No differences."));
	}

	function compare() {
		const others = S.editions.filter((e) => e.name !== S.cfg.edition_id);
		if (!others.length) return frappe.msgprint(__("There is no other edition to compare with."));
		const d = new frappe.ui.Dialog({
			title: __("Compare {0} with", [S.cfg.edition_name]),
			fields: [
				{ fieldname: "other", fieldtype: "Select", label: __("Edition"), options: others.map((e) => ({ value: e.name, label: e.edition_name })), default: others[0].name },
				{ fieldname: "result", fieldtype: "HTML" },
			],
			primary_action_label: __("Compare"),
			primary_action: (v) =>
				call("compare_editions", { a: S.cfg.edition_id, b: v.other })
					.then((diff) => {
						const other = others.find((e) => e.name === v.other);
						d.fields_dict.result.$wrapper[0].replaceChildren(diffView(diff, S.cfg.edition_name, other.edition_name));
					})
					.catch(fail),
		});
		d.show();
	}

	function showInspector() {
		const r = S.inspection;
		if (!r) return frappe.msgprint(__("Open or create an edition first."));
		const table = (cols, rows) =>
			h("table", { class: "table table-sm zg-eb__table" }, h("thead", {}, h("tr", {}, cols.map((c) => h("th", {}, c)))), h("tbody", {}, rows));
		const body = h(
			"div",
			{ class: "zg-eb__dialog" },
			h("p", {}, __("{0} modules, {1} features, {2} DocTypes, {3} reports (foundation included).", [r.counts.modules, r.counts.features, r.counts.doctypes, r.counts.reports])),
			r.warnings.length ? h("ul", { class: "zg-eb__warn" }, r.warnings.map((w) => h("li", {}, w))) : h("p", { class: "zg-eb__ok" }, __("No missing dependencies.")),
			h("h5", {}, __("What submitting writes (never gated)")),
			r.posting.length
				? table([__("DocType"), __("Ledgers ERPNext writes"), __("Background jobs")], r.posting.map((p) => h("tr", {}, h("td", {}, p.doctype), h("td", {}, p.ledgers.join(", ")), h("td", {}, p.jobs.join(", ") || "-"))))
				: h("p", {}, __("Nothing this edition submits posts to a ledger.")),
			h("h5", {}, __("DocTypes and actions")),
			table([__("DocType"), __("Actions"), __("From features"), __("Only when")], r.doctypes.map((d) => h("tr", {}, h("td", {}, d.doctype), h("td", {}, d.actions.join(", ")), h("td", {}, d.features.join(", ")), h("td", {}, d.match.map((m) => Object.entries(m).filter(([k]) => k !== "feature").map(([k, v]) => `${k} = ${Array.isArray(v) ? v.join(" / ") : v}`).join("; ")).join(" | ") || "-")))),
			h("h5", {}, __("Settings users can change")),
			h("p", {}, r.settings.join(", ") || "-"),
			h("h5", {}, __("Reports")),
			h("p", {}, r.reports.join(", ") || "-"),
			h("h5", {}, __("Workspaces and pages")),
			h("p", {}, [...r.workspaces, ...r.pages].join(", ") || "-"),
			h("h5", {}, __("API prefixes")),
			h("p", { class: "zg-eb__mono" }, r.api_prefixes.join("\n") || "-")
		);
		const d = new frappe.ui.Dialog({ title: __("Dependency inspector"), size: "extra-large", fields: [{ fieldname: "body", fieldtype: "HTML" }] });
		d.fields_dict.body.$wrapper[0].replaceChildren(body);
		d.show();
	}

	// -- view ------------------------------------------------------------------------------------------------
	function render() {
		toolbar();
		const banner = !S.canEdit
			? h("div", { class: "zg-banner", role: "status" }, S.isIssuer ? __("Read only: only a System Manager can change editions.") : __("Read only: editions are created and changed on the ZatGo licence issuer site. A licence keeps its own signed copy of its edition."))
			: null;
		root.replaceChildren(
			...[banner].filter(Boolean),
			h("div", { class: "zg-eb__layout" }, h("aside", { class: "zg-eb__list", "aria-label": __("Editions") }, listView()), h("section", { class: "zg-eb__main" }, mainView()), h("aside", { class: "zg-eb__side", "aria-label": __("Summary") }))
		);
		renderSide();
	}

	function listView() {
		const filters = ["all", "Active", "Draft", "Archived"];
		const chips = h(
			"div",
			{ class: "zg-eb__chips", role: "group", "aria-label": __("Filter by status") },
			filters.map((f) =>
				h("button", { type: "button", class: "zg-eb__chip", "aria-pressed": String(S.filter === f), onclick: () => ((S.filter = f), render()) }, f === "all" ? __("All") : __(f))
			)
		);
		const items = S.editions.filter((e) => S.filter === "all" || e.status === S.filter);
		const list = h(
			"ul",
			{ class: "zg-eb__items" },
			items.map((e) =>
				h(
					"li",
					{},
					h(
						"button",
						{ type: "button", class: "zg-eb__item", "aria-current": S.cfg && S.cfg.edition_id === e.name ? "true" : false, onclick: () => guard(() => open(e.name).catch(fail)) },
						h("span", { class: "zg-eb__item-name" }, e.edition_name),
						h("span", { class: "zg-eb__item-meta" }, `${e.edition_id} · v${e.version}`, e.preset ? ` · ${__("preset")}` : ""),
						h("span", { class: `indicator-pill ${STATUS_TONE[e.status] || "gray"}` }, __(e.status))
					)
				)
			)
		);
		return [chips, items.length ? list : h("p", { class: "zg-eb__empty" }, S.editions.length ? __("No edition with this status.") : S.isIssuer ? __("No editions yet. Presets are created on migrate.") : __("No editions on this site."))];
	}

	function mainView() {
		if (!S.cfg) return [h("p", { class: "zg-eb__empty" }, __("Choose an edition."))];
		const c = S.cfg;
		const ro = !S.canEdit;
		const field = (label, input) => h("label", { class: "zg-eb__field" }, h("span", {}, label), input);
		const head = h(
			"div",
			{ class: "zg-eb__head" },
			field(__("Edition name"), h("input", { class: "form-control", value: c.edition_name, disabled: ro, oninput: (e) => ((c.edition_name = e.target.value), changed()) })),
			field(__("Edition ID"), h("input", { class: "form-control", value: c.edition_id, disabled: ro || !S.isNew, oninput: (e) => ((c.edition_id = e.target.value.trim()), changed()) })),
			field(
				__("Status"),
				h("select", { class: "form-control", disabled: ro, onchange: (e) => ((c.status = e.target.value), changed()) }, S.reg.statuses.map((s) => h("option", { value: s, selected: s === c.status }, __(s))))
			),
			h("span", { class: "zg-eb__version" }, S.isNew ? __("New edition") : __("Version {0}", [c.version]), c.preset ? ` · ${__("from preset {0}", [c.preset])}` : ""),
			h("span", { class: "zg-eb__dirty", hidden: !dirty() }, __("Unsaved changes")),
			field(__("Description"), h("textarea", { class: "form-control", rows: 2, disabled: ro, oninput: (e) => ((c.description = e.target.value), changed()) }, c.description || ""))
		);
		const search = h("input", {
			class: "form-control zg-eb__search",
			type: "search",
			placeholder: __("Search features"),
			"aria-label": __("Search features"),
			value: S.search,
			oninput: (e) => {
				S.search = e.target.value.toLowerCase();
				const modulesEl = root.querySelector(".zg-eb__modules");
				if (modulesEl) modulesEl.replaceChildren(...modulesView());
			},
		});
		return [head, h("h3", { class: "zg-eb__title" }, __("Modules and features")), search, h("div", { class: "zg-eb__modules" }, modulesView())];
	}

	function modulesView() {
		const c = S.cfg;
		const ro = !S.canEdit;
		const q = S.search;
		const match = (f) => !q || f.label.toLowerCase().includes(q) || f.id.includes(q);
		return S.reg.modules
			.map((m) => {
				const feats = S.reg.features.filter((f) => f.module === m.id && match(f));
				if (!feats.length) return null;
				if (feats.every((f) => f.foundation)) {
					return h("details", { class: "zg-eb__module", "data-foundation": "" }, h("summary", {}, h("span", { class: "zg-eb__module-name" }, m.label), h("span", { class: "zg-eb__count" }, __("Included in every edition"))), h("ul", { class: "zg-eb__features" }, feats.map((f) => h("li", {}, h("span", {}, f.label), " ", h("code", {}, f.id)))));
				}
				const picked = feats.filter((f) => f.id in c.features).length;
				const all = h("input", {
					type: "checkbox",
					checked: picked === feats.length,
					disabled: ro,
					"aria-label": __("Select every feature of {0}", [m.label]),
					onclick: (e) => e.stopPropagation(),
					onchange: (e) => {
						feats.forEach((f) => {
							if (e.target.checked) c.features[f.id] = c.features[f.id] || [];
							else delete c.features[f.id];
						});
						rerenderModules();
						changed();
					},
				});
				if (picked && picked < feats.length) all.indeterminate = true;
				return h(
					"details",
					{ class: "zg-eb__module", open: picked > 0 || !!q },
					h("summary", {}, all, h("span", { class: "zg-eb__module-name" }, m.label), h("span", { class: "zg-eb__count" }, `${picked}/${feats.length}`), !m.available ? h("span", { class: "indicator-pill gray" }, __("not on this site")) : null),
					h("ul", { class: "zg-eb__features" }, feats.map(featureRow))
				);
			})
			.filter(Boolean);
	}

	function rerenderModules() {
		const el = root.querySelector(".zg-eb__modules");
		if (!el) return;
		const open = new Set([...el.querySelectorAll("details[open] .zg-eb__module-name")].map((n) => n.textContent));
		el.replaceChildren(...modulesView());
		el.querySelectorAll("details").forEach((d) => {
			const name = d.querySelector(".zg-eb__module-name");
			if (name && open.has(name.textContent)) d.open = true;
		});
	}

	function featureRow(f) {
		const c = S.cfg;
		const ro = !S.canEdit;
		const on = f.id in c.features;
		const id = `zg-eb-f-${f.id.replace(/\W/g, "-")}`;
		const needs = Object.keys(f.requires);
		const row = h(
			"li",
			{ class: "zg-eb__feature", "data-on": on ? "1" : false },
			h("input", {
				type: "checkbox",
				id,
				checked: on,
				disabled: ro,
				onchange: (e) => {
					if (e.target.checked) c.features[f.id] = [];
					else delete c.features[f.id];
					rerenderModules();
					changed();
				},
			}),
			h(
				"div",
				{ class: "zg-eb__feature-body" },
				h("label", { for: id }, f.label, " ", h("code", {}, f.id)),
				f.description ? h("div", { class: "zg-eb__hint" }, f.description) : null,
				h(
					"div",
					{ class: "zg-eb__tags" },
					f.platforms.map((p) => h("span", { class: "zg-eb__tag" }, PLATFORM_LABEL[p])),
					!f.available ? h("span", { class: "zg-eb__tag", "data-tone": "warn" }, __("needs {0}", [f.source_app])) : null,
					needs.length ? h("span", { class: "zg-eb__tag", "data-tone": "info" }, __("requires {0}", [needs.join(", ")])) : null
				),
				on && f.actions.length ? actionsPicker(f) : null
			)
		);
		return row;
	}

	function actionsPicker(f) {
		const c = S.cfg;
		const ro = !S.canEdit;
		const narrowed = c.features[f.id] || [];
		return h(
			"details",
			{ class: "zg-eb__actions", open: narrowed.length > 0 },
			h("summary", {}, narrowed.length ? __("Limited to: {0}", [narrowed.join(", ")]) : __("All actions ({0}) - limit...", [f.actions.length])),
			h(
				"div",
				{ class: "zg-eb__action-grid" },
				f.actions.map((a) =>
					h(
						"label",
						{},
						h("input", {
							type: "checkbox",
							disabled: ro,
							checked: !narrowed.length || narrowed.includes(a),
							onchange: (e) => {
								const boxes = [...e.target.closest(".zg-eb__action-grid").querySelectorAll("input")];
								const chosen = f.actions.filter((_, i) => boxes[i].checked);
								c.features[f.id] = chosen.length === f.actions.length || !chosen.length ? [] : chosen;
								changed();
								const sum = e.target.closest("details").querySelector("summary");
								sum.textContent = c.features[f.id].length ? __("Limited to: {0}", [c.features[f.id].join(", ")]) : __("All actions ({0}) - limit...", [f.actions.length]);
							},
						}),
						" ",
						a
					)
				)
			)
		);
	}

	function renderSide() {
		const side = root.querySelector(".zg-eb__side");
		if (!side) return;
		if (!S.cfg) return side.replaceChildren();
		const c = S.cfg;
		const r = S.inspection;
		const ro = !S.canEdit;
		const stat = (v, label, tone) => h("div", { class: "zg-stat", "data-tone": tone || false }, h("div", { class: "zg-stat__value" }, String(v)), h("div", { class: "zg-stat__label" }, label));
		const num = (key, label) =>
			h(
				"label",
				{ class: "zg-eb__field" },
				h("span", {}, label),
				h("input", { class: "form-control", type: "number", min: 0, step: 1, value: c.licence_defaults[key], disabled: ro, oninput: (e) => ((c.licence_defaults[key] = parseInt(e.target.value || "0", 10)), changed()) })
			);
		const nodes = [
			h("h3", { class: "zg-eb__title" }, __("Summary")),
			r
				? h("div", { class: "zg-eb__stats" }, stat(r.counts.modules, __("Modules")), stat(r.counts.features, __("Features")), stat(r.counts.doctypes, __("DocTypes")), stat(r.missing.length, __("Missing"), r.missing.length ? "warn" : "good"))
				: h("p", {}, __("Inspecting...")),
			h("h3", { class: "zg-eb__title" }, __("Platforms")),
			h(
				"div",
				{ class: "zg-eb__platforms" },
				S.reg.platforms.map((p) =>
					h("label", {}, h("input", { type: "checkbox", checked: !!c.platforms[p], disabled: ro, onchange: (e) => ((c.platforms[p] = e.target.checked ? 1 : 0), changed()) }), " ", PLATFORM_LABEL[p])
				)
			),
			h("h3", { class: "zg-eb__title" }, __("Licence defaults")),
			h(
				"label",
				{ class: "zg-eb__field" },
				h("span", {}, __("Licence type")),
				h("select", { class: "form-control", disabled: ro, onchange: (e) => ((c.licence_defaults.licence_type = e.target.value), changed()) }, S.reg.licence_types.map((t) => h("option", { value: t, selected: t === c.licence_defaults.licence_type }, __(t))))
			),
			num("duration_days", __("Duration (days)")),
			num("trial_days", __("Trial (days)")),
			num("max_users", __("Maximum users (0 = no limit)")),
			num("max_companies", __("Maximum companies (0 = no limit)")),
			h(
				"label",
				{ class: "zg-eb__field" },
				h("span", {}, __("Default roles (one per line)")),
				h("textarea", { class: "form-control", rows: 3, disabled: ro, oninput: (e) => ((c.default_roles = e.target.value.split("\n").map((x) => x.trim()).filter(Boolean)), changed()) }, (c.default_roles || []).join("\n"))
			),
		];
		if (r) {
			nodes.push(h("h3", { class: "zg-eb__title" }, __("Warnings")));
			if (!r.warnings.length) nodes.push(h("p", { class: "zg-eb__ok" }, __("No missing dependencies.")));
			else {
				const names = featureById();
				nodes.push(
					h(
						"ul",
						{ class: "zg-eb__warn" },
						r.missing.map((m) =>
							h(
								"li",
								{},
								__("{0} needs {1}", [(names[m.needed_by] || {}).label || m.needed_by, (names[m.feature] || {}).label || m.feature]),
								m.actions.length ? ` (${m.actions.join(", ")})` : "",
								S.canEdit
									? h("button", { type: "button", class: "btn btn-xs btn-default zg-eb__add", onclick: () => ((c.features[m.feature] = c.features[m.feature] || []), rerenderModules(), changed()) }, __("Add {0}", [m.feature]))
									: null
							)
						),
						r.warnings.filter((w) => !w.startsWith("Missing")).map((w) => h("li", {}, w))
					)
				);
			}
		}
		side.replaceChildren(...nodes);
	}

	load();
};
