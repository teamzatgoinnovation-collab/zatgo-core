// ZatGo Licence: the licence in force on this site, what it includes, warnings, history -- and, on the licence
// issuer site, issuing and revoking (docs/licensing.md). Every rule is on the server
// (zatgo_core.api.v1.licensing.licences); buttons a user may not use are not shown.
frappe.pages["zg-licence"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("ZatGo Licence"), single_column: true });
	const root = document.createElement("div");
	root.className = "zg-lic";
	page.main[0].appendChild(root);

	const API = "zatgo_core.api.v1.licensing.licences.";
	const TONE = { Active: "green", Trial: "blue", Expiring: "orange", Expired: "red", Revoked: "red", Invalid: "red", Scheduled: "gray", Suspended: "red" };

	// DOM builder: text goes in as text nodes, never as HTML.
	const h = (tag, props, ...kids) => {
		const el = document.createElement(tag);
		for (const [k, v] of Object.entries(props || {})) {
			if (v === false || v == null) continue;
			if (k === "class") el.className = v;
			else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
			else el.setAttribute(k, v === true ? "" : v);
		}
		kids.flat().forEach((c) => c != null && c !== false && el.append(c));
		return el;
	};
	// frappe.call is a jQuery promise: wrap it. A server error is shown by Frappe itself.
	const call = (method, args, type) =>
		Promise.resolve(frappe.call({ method: API + method, args: args || {}, type: type || "GET" })).then((r) => {
			const m = r && r.message;
			if (m && m.success === false) throw new Error((m.error && m.error.message) || __("Request failed"));
			return m && m.data !== undefined ? m.data : m;
		});
	const post = (method, args) => call(method, args, "POST");
	const fail = (e) => e instanceof Error && frappe.msgprint(e.message);
	const loadCss = (href) =>
		new Promise((resolve) => {
			if (!href || document.querySelector("link[data-zg-lic]")) return resolve();
			const link = h("link", { rel: "stylesheet", href, "data-zg-lic": "" });
			link.addEventListener("load", resolve);
			link.addEventListener("error", resolve);
			document.head.append(link);
			setTimeout(resolve, 2000);
		});
	const download = (name, text) => {
		const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
		const a = h("a", { href: url, download: name });
		document.body.append(a);
		a.click();
		a.remove();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	};
	const pickFile = (accept) =>
		new Promise((resolve) => {
			const input = h("input", { type: "file", accept, hidden: true });
			input.addEventListener("change", () => {
				const file = input.files && input.files[0];
				input.remove();
				resolve(file ? file.text() : null);
			});
			document.body.append(input);
			input.click();
		}).then((p) => p);
	const fmt = (d) => (d ? frappe.datetime.str_to_user(d) : "-");

	let S = null;

	// -- actions ---------------------------------------------------------------------------------------------
	function importLicence() {
		pickFile(".zglicence,.json,application/json").then((text) => {
			if (!text) return;
			post("import_licence", { file: text })
				.then((r) => {
					frappe.show_alert({ message: __("Licence {0} imported", [r.licence_number]), indicator: "green" });
					return render();
				})
				.catch(fail);
		});
	}
	function importRevocation() {
		pickFile(".zgrevocation,.json,application/json").then((text) => {
			if (!text) return;
			post("import_revocation", { file: text })
				.then((r) => {
					frappe.msgprint(__("Revocation list imported: {0} licence(s) listed, {1} revoked on this site.", [r.listed, r.revoked.length]));
					return render();
				})
				.catch(fail);
		});
	}
	function verify() {
		post("verify_licence")
			.then((r) => {
				if (!r.present) frappe.msgprint(__("No licence is imported."));
				else if (r.ok) frappe.show_alert({ message: __("The licence verifies: signature and site match."), indicator: "green" });
				else frappe.msgprint({ title: __("The licence does not verify"), message: r.message, indicator: "red" });
				return render();
			})
			.catch(fail);
	}
	function exportJson(method, name) {
		call(method)
			.then((data) => download(typeof name === "function" ? name(data) : name, JSON.stringify(data, null, 1)))
			.catch(fail);
	}
	function downloadLicence(name) {
		call("download_licence", { name })
			.then((d) => download(d.filename, d.file))
			.catch(fail);
	}

	function toolbar() {
		page.clear_primary_action();
		page.clear_menu();
		page.set_secondary_action(__("Refresh"), () => render(), "refresh");
		if (!S || !S.can_manage) return;
		page.set_primary_action(S.licence.present ? __("Replace licence") : __("Import licence"), importLicence, "upload");
		page.add_menu_item(__("Verify licence"), verify);
		page.add_menu_item(__("Import revocation list"), importRevocation);
		page.add_menu_item(__("Export site identity (for ZatGo)"), () => exportJson("site_request", (d) => `zatgo-site-${d.site_name}.json`));
		page.add_menu_item(__("Export licence information"), () => exportJson("licence_info", `zatgo-licence-info-${S.today}.json`));
		if (S.licence.present) {
			const current = S.history.licences.find((l) => l.is_current);
			if (current) page.add_menu_item(__("Download licence file"), () => downloadLicence(current.name));
		}
	}

	// -- view ------------------------------------------------------------------------------------------------
	function field(label, value) {
		return h("div", { class: "zg-lic__field" }, h("dt", {}, label), h("dd", {}, value == null || value === "" ? "-" : String(value)));
	}
	function limit(used, max) {
		return max ? `${used} / ${max}` : `${used} (${__("no limit")})`;
	}

	function overviewView() {
		const l = S.licence;
		const site = S.site;
		const siteBox = h(
			"section",
			{ class: "zg-lic__card" },
			h("h3", {}, __("This site")),
			h("dl", { class: "zg-lic__grid" }, field(__("Site name"), site.site_name), field(__("Site ID"), site.site_id || __("not created yet (Export site identity creates it)")), field(__("ZatGo version"), site.app_version), field(__("Users"), limit(l.usage ? l.usage.users : "-", l.present ? l.limits.max_users : 0)), field(__("Companies"), limit(l.usage ? l.usage.companies : "-", l.present ? l.limits.max_companies : 0)), field(__("Enforcement"), S.enforcement.switch ? (S.enforcement.enforcing ? __("On") : __("Switched on, no licence")) : __("Off")))
		);
		if (!l.present) {
			return [h("section", { class: "zg-lic__card zg-lic__empty" }, h("h3", {}, __("No licence imported")), h("p", {}, __("Export this site's identity, send it to ZatGo, and import the licence file you receive."))), siteBox];
		}
		const days = l.days_remaining == null ? __("no expiry") : __("{0} day(s)", [l.days_remaining]);
		return [
			h(
				"section",
				{ class: "zg-lic__card zg-lic__hero" },
				h("div", { class: "zg-lic__hero-head" }, h("div", {}, h("div", { class: "zg-lic__eyebrow" }, __("Edition")), h("h2", {}, l.edition_name)), h("span", { class: `indicator-pill ${TONE[l.status] || "gray"}` }, __(l.status))),
				h("dl", { class: "zg-lic__grid" }, field(__("Customer"), l.customer_name), field(__("Licence number"), `${l.licence_number} (v${l.licence_version})`), field(__("Licence type"), __(l.licence_type)), field(__("Issued"), fmt(l.issue_date)), field(__("Starts"), fmt(l.start_date)), field(__("Imported"), l.imported_on ? frappe.datetime.str_to_user(l.imported_on) : "-"), field(__("Expires"), l.expiry_date ? fmt(l.expiry_date) : __("Never")), field(__("Remaining"), days), field(__("Signature"), l.verified ? __("Verified") : __("Does not verify")), field(__("Features"), l.feature_count))
			),
			siteBox,
		];
	}

	function warningsView() {
		if (!S.warnings.length) return null;
		return h(
			"section",
			{ class: "zg-lic__warnings", "aria-label": __("Warnings") },
			S.warnings.map((w) => h("div", { class: "zg-lic__warning", "data-level": w.level, role: w.level === "danger" ? "alert" : "status" }, h("strong", {}, w.level === "danger" ? __("Action needed") : w.level === "warning" ? __("Warning") : __("Note")), " ", w.message))
		);
	}

	function modulesView() {
		const restricted = S.licence.present;
		return h(
			"section",
			{ class: "zg-lic__card" },
			h("h3", {}, __("Module access")),
			h("p", { class: "zg-lic__hint" }, restricted ? __("What the licence includes. Modules it does not include stay readable: existing records can be viewed, printed and cancelled.") : __("No licence: nothing is restricted.")),
			h(
				"div",
				{ class: "zg-lic__modules" },
				S.modules.map((m) =>
					h(
						"details",
						{ class: "zg-lic__module" },
						h("summary", {}, h("span", { class: "zg-lic__module-name" }, m.label), h("span", { class: "zg-lic__count", "data-state": !restricted ? "free" : m.licensed === m.total ? "all" : m.licensed ? "some" : "none" }, restricted ? `${m.licensed}/${m.total}` : __("unrestricted"))),
						h(
							"ul",
							{},
							m.features.map((f) =>
								h(
									"li",
									{ "data-licensed": f.licensed === false ? "0" : "1" },
									h("span", { class: "zg-lic__mark", "aria-hidden": "true" }, f.licensed === false ? "✕" : "✓"),
									h("span", { class: "zg-visually-hidden" }, f.licensed === false ? __("Not licensed") : __("Licensed")),
									h("span", {}, f.label),
									f.licensed !== false && f.actions.length ? h("span", { class: "zg-lic__actions" }, f.actions.join(", ")) : null
								)
							)
						)
					)
				)
			)
		);
	}

	function historyView() {
		const rows = S.history.licences;
		const events = S.history.events;
		return h(
			"section",
			{ class: "zg-lic__card" },
			h("h3", {}, __("Activation history")),
			rows.length
				? h(
						"div",
						{ class: "zg-lic__table-wrap" },
						h(
							"table",
							{ class: "table table-sm zg-lic__table" },
							h("thead", {}, h("tr", {}, [__("Licence"), __("Edition"), __("Status"), __("Valid"), __("Imported"), ""].map((c) => h("th", {}, c)))),
							h(
								"tbody",
								{},
								rows.map((r) =>
									h(
										"tr",
										{},
										h("td", {}, `${r.licence_number} v${r.licence_version}`, r.is_current ? h("span", { class: "indicator-pill blue zg-lic__current" }, __("Current")) : null),
										h("td", {}, r.edition_name),
										h("td", {}, __(r.status)),
										h("td", {}, `${fmt(r.start_date)} – ${r.expiry_date ? fmt(r.expiry_date) : __("no expiry")}`),
										h("td", {}, r.imported_on ? frappe.datetime.str_to_user(r.imported_on) : "-", h("br"), h("small", {}, r.imported_by || "")),
										h("td", {}, S.can_manage ? h("button", { type: "button", class: "btn btn-xs btn-default", onclick: () => downloadLicence(r.name) }, __("Download")) : null)
									)
								)
							)
						)
				  )
				: h("p", { class: "zg-lic__hint" }, __("No licence has been imported on this site.")),
			events.length ? h("h4", {}, __("Events")) : null,
			events.length ? h("ul", { class: "zg-lic__events" }, events.slice(0, 20).map((e) => h("li", {}, h("span", { class: "zg-lic__event" }, e.event.replace(/_/g, " ")), " ", frappe.datetime.str_to_user(e.creation), " · ", e.changed_by, e.reason ? ` · ${e.reason}` : ""))) : null
		);
	}

	// -- issuer ----------------------------------------------------------------------------------------------
	function issueDialog(replaces) {
		const iss = S.issuer;
		if (!iss.editions.length) return frappe.msgprint(__("There is no Active edition to license."));
		const d = new frappe.ui.Dialog({
			title: replaces ? __("Issue a replacement for {0}", [replaces.licence_number]) : __("Issue licence"),
			size: "large",
			fields: [
				{ fieldname: "edition_id", fieldtype: "Select", label: __("Edition"), reqd: 1, options: iss.editions.map((e) => ({ value: e.name, label: `${e.edition_name} (v${e.version})` })), default: replaces ? replaces.edition_id : iss.editions[0].name },
				{ fieldname: "customer_name", fieldtype: "Data", label: __("Customer name"), reqd: 1, default: replaces ? replaces.customer_name : "" },
				{ fieldname: "customer_id", fieldtype: "Data", label: __("Customer ID") },
				{ fieldname: "load_request", fieldtype: "Button", label: __("Load a site identity file") },
				{ fieldname: "site_ids", fieldtype: "Small Text", label: __("Site IDs"), reqd: 1, description: __("One per line, from the customer's site identity file.") },
				{ fieldname: "site_names", fieldtype: "Small Text", label: __("Site names (optional)"), description: __("Also bind to these host names.") },
				{ fieldname: "col", fieldtype: "Column Break" },
				{ fieldname: "licence_type", fieldtype: "Select", label: __("Licence type"), options: [""].concat(iss.licence_types), description: __("Blank = the edition's default.") },
				{ fieldname: "start_date", fieldtype: "Date", label: __("Start date"), default: frappe.datetime.get_today() },
				{ fieldname: "expiry_date", fieldtype: "Date", label: __("Expiry date"), description: __("Blank = start + the edition's duration. Ignored for Lifetime / Perpetual.") },
				{ fieldname: "max_users", fieldtype: "Int", label: __("Maximum users"), description: __("Blank = the edition's default; 0 = no limit.") },
				{ fieldname: "max_companies", fieldtype: "Int", label: __("Maximum companies") },
				{ fieldname: "max_sites", fieldtype: "Int", label: __("Maximum sites"), default: 1 },
			],
			primary_action_label: __("Issue and download"),
			primary_action: (v) => {
				const args = { ...v, replaces: replaces ? replaces.licence_id : "" };
				delete args.col;
				delete args.load_request;
				["max_users", "max_companies"].forEach((k) => {
					if (!v[k] && v[k] !== 0) delete args[k];
				});
				post("issue_licence", args)
					.then((r) => {
						d.hide();
						download(r.filename, r.file);
						frappe.show_alert({ message: __("Licence {0} issued", [r.licence_number]), indicator: "green" });
						return render();
					})
					.catch(fail);
			},
		});
		d.fields_dict.load_request.$input.on("click", () =>
			pickFile(".json,application/json").then((text) => {
				if (!text) return;
				try {
					const req = JSON.parse(text);
					if (req.type !== "zatgo.site_request") throw new Error();
					d.set_value("site_ids", req.site_id || "");
					d.set_value("site_names", req.site_name || "");
				} catch (e) {
					frappe.msgprint(__("That is not a ZatGo site identity file."));
				}
			})
		);
		if (replaces) d.set_value("site_ids", (replaces.site_ids || "").trim());
		d.show();
	}

	function revoke(row) {
		frappe.confirm(__("Revoke licence {0}? You will download a revocation list to send to the customer; their site stops honouring the licence when it is imported.", [row.licence_number]), () =>
			post("revoke_licences", { licence_ids: JSON.stringify([row.licence_id]) })
				.then((r) => {
					download(r.filename, r.file);
					return render();
				})
				.catch(fail)
		);
	}

	function issuerView() {
		if (!S.issuer) return null;
		const rows = S.issuer.issued;
		return h(
			"section",
			{ class: "zg-lic__card zg-lic__issuer" },
			h("div", { class: "zg-lic__hero-head" }, h("h3", {}, __("Issuer: licences signed here")), h("button", { type: "button", class: "btn btn-sm btn-primary", onclick: () => issueDialog(null) }, __("Issue licence"))),
			rows.length
				? h(
						"div",
						{ class: "zg-lic__table-wrap" },
						h(
							"table",
							{ class: "table table-sm zg-lic__table" },
							h("thead", {}, h("tr", {}, [__("Licence"), __("Customer"), __("Edition"), __("Valid"), __("Issued"), ""].map((c) => h("th", {}, c)))),
							h(
								"tbody",
								{},
								rows.map((r) =>
									h(
										"tr",
										{ "data-revoked": r.revoked_on ? "1" : false },
										h("td", {}, `${r.licence_number} v${r.licence_version}`, r.revoked_on ? h("span", { class: "indicator-pill red zg-lic__current" }, __("Revoked")) : null),
										h("td", {}, r.customer_name),
										h("td", {}, r.edition_id),
										h("td", {}, `${fmt(r.start_date)} – ${r.expiry_date ? fmt(r.expiry_date) : __("no expiry")}`),
										h("td", {}, frappe.datetime.str_to_user(r.issued_on)),
										h(
											"td",
											{ class: "zg-lic__row-actions" },
											h("button", { type: "button", class: "btn btn-xs btn-default", onclick: () => call("download_issued", { licence_number: r.licence_number }).then((x) => download(x.filename, x.file)).catch(fail) }, __("Download")),
											r.revoked_on ? null : h("button", { type: "button", class: "btn btn-xs btn-default", onclick: () => frappe.db.get_value("ZG Licence History", r.licence_number, ["site_ids", "customer_name", "edition_id"]).then((x) => issueDialog({ ...r, ...(x.message || {}) })) }, __("Replace")),
											r.revoked_on ? null : h("button", { type: "button", class: "btn btn-xs btn-danger", onclick: () => revoke(r) }, __("Revoke"))
										)
									)
								)
							)
						)
				  )
				: h("p", { class: "zg-lic__hint" }, __("No licence issued yet."))
		);
	}

	function render() {
		root.setAttribute("aria-busy", "true");
		return call("get_page")
			.then((data) => loadCss(data.css).then(() => data))
			.then((data) => {
				S = data;
				toolbar();
				root.replaceChildren(...[warningsView(), h("div", { class: "zg-lic__top" }, overviewView()), modulesView(), historyView(), issuerView()].filter(Boolean));
			})
			.catch((e) => root.replaceChildren(h("div", { class: "zg-banner", role: "alert" }, h("p", {}, e instanceof Error ? e.message : __("Could not load the licence.")))))
			.finally(() => root.removeAttribute("aria-busy"));
	}
	render();
};
