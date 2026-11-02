/* Duplicate Prevention: live lookup while a NEW record is typed (Desk).
 *
 * Registered for every DocType a duplicate rule can exist for; the rule itself (watched fields, whether live
 * lookup is on, whether this user may override) comes from zatgo_core.api.v1.duplicate.lookup.form_config and
 * is asked once per DocType. Nothing here decides anything: the server re-checks on every save.
 * The panel is inline under the field being typed (no dialog per keystroke); a single confirm appears at
 * save time only for warn-level matches.
 */
(function () {
	const API = "zatgo_core.api.v1.duplicate.lookup.";
	const DEBOUNCE_MS = 400;
	const DOCTYPES = [
		"Item", "Customer", "Supplier", "Employee", "Contact", "Address", "Warehouse", "Account", "UOM", "Brand",
		"Manufacturer", "Sales Partner", "Territory", "Lead", "Opportunity", "Purchase Invoice", "Sales Invoice",
	];
	const configs = {}; // doctype -> Promise<config|null>
	const registered = new Set(); // child-table handlers are registered once per page load

	function get_config(doctype) {
		if (!configs[doctype]) {
			configs[doctype] = new Promise((resolve) => {
				frappe.call({ method: API + "form_config", args: { doctype }, type: "GET", silent: true })
					.then((r) => resolve((r.message && r.message.data) || null))
					.catch(() => resolve(null));
			});
		}
		return configs[doctype];
	}

	function values_of(frm, cfg, typed) {
		const values = {};
		(cfg.watch || []).forEach((f) => {
			const v = frm.doc[f];
			if (Array.isArray(v)) {
				const field = (cfg.children || []).find((c) => c.table === f);
				values[f] = v.map((row) => ({ [field ? field.fieldname : ""]: row[field ? field.fieldname : ""] })).filter((r) => Object.values(r)[0]);
			} else if (v) {
				values[f] = v;
			}
		});
		if (typed && typed.field) values[typed.field] = typed.value;
		return values;
	}

	function panel_for(frm, field) {
		if (!frm.__zg_dup_panel) frm.__zg_dup_panel = $('<div class="zg-dup" role="status" aria-live="polite"></div>');
		const target = frm.fields_dict[field] && frm.fields_dict[field].$wrapper;
		if (target && !$.contains(target[0], frm.__zg_dup_panel[0])) target.append(frm.__zg_dup_panel);
		return frm.__zg_dup_panel;
	}

	function use_existing(frm, name) {
		try {
			if (frappe._from_link) {
				frappe.ui.form.update_calling_link({ doctype: frm.doctype, name });
				if (cur_dialog) cur_dialog.hide();
				return;
			}
		} catch (e) { /* fall through to opening the record */ }
		frappe.set_route("Form", frm.doctype, name);
	}

	function render(frm, cfg, data, field) {
		const $p = panel_for(frm, field);
		const matches = (data && data.matches) || [];
		frm.__zg_dup_state = { level: data && data.level, action: data && data.action, names: matches.filter((m) => !m.restricted).map((m) => m.name) };
		if (!matches.length) return $p.empty().hide();
		const e = frappe.utils.escape_html;
		const level = data.level || "suggest";
		const blocking = data.action === "Block" && level !== "suggest";
		const heading = {
			strong: blocking ? __("Existing {0} found — this looks like a duplicate", [__(frm.doctype)]) : __("Existing {0} found", [__(frm.doctype)]),
			possible: __("Possible existing {0}. Please verify before saving.", [__(frm.doctype)]),
			suggest: __("Similar {0} found", [__(frm.doctype)]),
		}[level];
		const rows = matches.map((m) => {
			if (m.restricted) return `<li class="zg-dup__item zg-dup__restricted">${__("A matching record exists that you cannot view")}</li>`;
			const fields = [...new Set(m.matched_on.map((x) => x.field))].join(", ");
			const details = (m.details || []).map((d) => `<span>${e(d.label)}: <b>${e(String(d.value))}</b></span>`).join("");
			return `<li class="zg-dup__item" data-name="${e(m.name)}">
				<div class="zg-dup__head"><span class="indicator-pill ${m.level === "strong" ? "red" : m.level === "possible" ? "orange" : "blue"}">${e(m.name)}</span>
				<b>${e(m.title || m.name)}</b> <span class="text-muted">(${__("matched")}: ${e(fields)})</span></div>
				<div class="zg-dup__details">${details}</div>
				<div class="zg-dup__actions">
					<button type="button" class="btn btn-xs btn-default zg-dup-open">${__("Open Existing")}</button>
					<button type="button" class="btn btn-xs btn-primary zg-dup-use">${__("Use Existing")}</button>
				</div></li>`;
		}).join("");
		const override = blocking && data.can_override
			? `<div class="zg-dup__override"><button type="button" class="btn btn-xs btn-default zg-dup-override">${__("Override (authorized)")}</button></div>` : "";
		$p.attr("class", `zg-dup zg-dup--${level}${blocking ? " zg-dup--block" : ""}`)
			.html(`<div class="zg-dup__title">${heading}</div><ul class="zg-dup__list">${rows}</ul>${override}`).show();
		$p.find(".zg-dup-open").on("click", function () { window.open(frappe.utils.get_form_link(frm.doctype, $(this).closest("li").data("name")), "_blank"); });
		$p.find(".zg-dup-use").on("click", function () { use_existing(frm, $(this).closest("li").data("name")); });
		$p.find(".zg-dup-override").on("click", () => {
			frappe.prompt([{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: cfg.needs_reason ? 1 : 0 }],
				(v) => frappe.call({ method: API + "override", args: { doctype: frm.doctype, names: frm.__zg_dup_state.names, reason: v.reason } })
					.then(() => { frm.__zg_dup_state.overridden = true; frappe.show_alert({ message: __("Override registered. You can save now."), indicator: "orange" }); }),
				__("Override duplicate prevention"), __("Register override"));
		});
	}

	function lookup(frm, cfg, field, value) {
		const values = values_of(frm, cfg, { field, value });
		const key = JSON.stringify(values);
		if (frm.__zg_dup_last === key) return;
		frm.__zg_dup_last = key;
		const ticket = (frm.__zg_dup_ticket = (frm.__zg_dup_ticket || 0) + 1);
		frappe.call({ method: API + "check", args: { doctype: frm.doctype, values }, type: "POST", silent: true })
			.then((r) => { if (ticket === frm.__zg_dup_ticket) render(frm, cfg, r.message && r.message.data, field); })
			.catch(() => {});
	}

	function setup(frm, cfg) {
		if (!cfg || !cfg.live || !frm.is_new() || frm.__zg_dup_bound) return;
		frm.__zg_dup_bound = true;
		const run = frappe.utils.debounce((field, value) => lookup(frm, cfg, field, value), DEBOUNCE_MS);
		frm.__zg_dup_run = (table) => run(table, frm.doc[table]);
		(cfg.watch || []).forEach((field) => {
			const control = frm.fields_dict[field];
			if (!control || !control.$input) return;
			control.$input.on("input.zgdup change.zgdup", () => run(field, control.$input.val()));
		});
		(cfg.children || []).forEach((c) => {
			if (!registered.has(c.doctype + c.fieldname)) {
				registered.add(c.doctype + c.fieldname);
				frappe.ui.form.on(c.doctype, c.fieldname, (f) => (cur_frm && cur_frm.__zg_dup_run) && cur_frm.__zg_dup_run(c.table));
			}
		});
		run((cfg.watch || [])[0], "");
	}

	DOCTYPES.forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			refresh(frm) {
				if (!frm.is_new()) return;
				get_config(doctype).then((cfg) => setup(frm, cfg));
			},
			before_save(frm) {
				const state = frm.__zg_dup_state;
				if (!frm.is_new() || !state || frm.__zg_dup_ack || state.overridden || !state.names.length) return;
				if (state.action === "Warn" && state.level !== "suggest") {
					frappe.validated = false;
					frappe.confirm(__("A similar {0} already exists ({1}). Save anyway?", [__(doctype), state.names.join(", ")]), () => {
						frm.__zg_dup_ack = true;
						frm.save();
					});
				}
			},
		});
	});
})();
