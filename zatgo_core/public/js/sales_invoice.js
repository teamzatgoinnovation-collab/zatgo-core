// Payment Type UX hint for Sales Invoice (custom_payment_type,
// patches/v0_2_2/add_payment_type_field.py). Purely visual -- the actual
// Cash/Credit handling lives server-side in
// zatgo_core.services.sales_invoice_payment_service.
//
// Also filters + pre-fills Cash Account (custom_cash_account,
// patches/v0_2_2/add_cash_account_field.py): the picker only ever offers
// this company's actual Cash-type ledger accounts (matching the same
// account_type check the server re-validates anyway), and picking "Cash"
// pre-fills it from the "Cash" Mode of Payment's configured default
// account for this company -- just a starting suggestion, still editable
// for companies running more than one till. The field is genuinely
// required server-side (not just cosmetically via mandatory_depends_on --
// see sales_invoice_payment_service.py for why that alone isn't enough).
//
// Payment Type "Bank" works the same way with Bank Account
// (custom_bank_account, patches/v0_2_7/add_bank_payment_fields.py): only
// Bank-type ledger accounts, pre-filled from the Bank-type Mode of Payment's
// default account for this company.

frappe.ui.form.on("Sales Invoice", {
	setup(frm) {
		frm.set_query("custom_cash_account", () => ({
			filters: {
				company: frm.doc.company,
				account_type: "Cash",
				is_group: 0,
			},
		}));
		frm.set_query("custom_bank_account", () => ({
			filters: {
				company: frm.doc.company,
				account_type: "Bank",
				is_group: 0,
			},
		}));
		// Payment rows (ERPNext's own POS `payments` table): only the accounts
		// configured for the row's Payment Method in this company. The server
		// re-validates every row (services/payment_allocation.py).
		frm.set_query("account", "payments", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				query: "zatgo_core.api.v1.accounting.payment_methods.account_query",
				filters: { mode_of_payment: row.mode_of_payment, company: doc.company },
			};
		});
	},
	paid_amount(frm) {
		show_payment_summary(frm);
	},
	grand_total(frm) {
		show_payment_summary(frm);
	},
	outstanding_amount(frm) {
		show_payment_summary(frm);
	},
	custom_payment_type(frm) {
		show_payment_type_hint(frm);
		prefill_cash_account(frm);
		prefill_bank_account(frm);
	},
	refresh(frm) {
		show_payment_type_hint(frm);
		show_user_naming_series(frm);
		show_payment_summary(frm);
	},
	company(frm) {
		show_user_naming_series(frm);
	},
	is_return(frm) {
		show_user_naming_series(frm);
	},
});

// User-wise naming series (ZG Sales Invoice Naming Settings). The server sets
// naming_series on insert regardless (zatgo_core/events/sales_invoice_naming.py);
// this only shows the user the series the invoice is actually going to get.
function show_user_naming_series(frm) {
	if (!frm.is_new() || frm.doc.amended_from) return;
	const rules = (frappe.boot.zatgo_core && frappe.boot.zatgo_core.sales_invoice_naming) || {};
	const rule = rules[frm.doc.company];
	frm.set_df_property("naming_series", "read_only", rule ? 1 : 0);
	if (!rule) return;
	const series = frm.doc.is_return ? rule.return_series : rule.normal_series;
	if (frm.doc.naming_series !== series) frm.set_value("naming_series", series);
}

function prefill_cash_account(frm) {
	if (frm.doc.custom_payment_type !== "Cash" || frm.doc.custom_cash_account || !frm.doc.company) {
		return;
	}
	frappe.db
		.get_value(
			"Mode of Payment Account",
			{ parent: "Cash", company: frm.doc.company },
			"default_account",
			null,
			"Mode of Payment" // child table: Frappe refuses the read without its parent doctype
		)
		.then((r) => {
			const account = r && r.message && r.message.default_account;
			if (account && frm.doc.custom_payment_type === "Cash" && !frm.doc.custom_cash_account) {
				frm.set_value("custom_cash_account", account);
			}
		});
}

// Default account of the company's Bank-type Mode of Payment ("Bank" first
// when there are several). A suggestion only; the server validates the pick.
function prefill_bank_account(frm) {
	if (frm.doc.custom_payment_type !== "Bank" || frm.doc.custom_bank_account || !frm.doc.company) {
		return;
	}
	frappe.db
		.get_list("Mode of Payment", { filters: { type: "Bank", enabled: 1 }, pluck: "name" })
		.then((modes) => {
			if (!modes || !modes.length) return;
			modes.sort((a, b) => (b.toLowerCase() === "bank") - (a.toLowerCase() === "bank"));
			const next = (i) => {
				if (i >= modes.length) return;
				frappe.db
					.get_value(
						"Mode of Payment Account",
						{ parent: modes[i], company: frm.doc.company },
						"default_account",
						null,
						"Mode of Payment"
					)
					.then((r) => {
						const account = r && r.message && r.message.default_account;
						if (!account) return next(i + 1);
						if (frm.doc.custom_payment_type === "Bank" && !frm.doc.custom_bank_account) {
							frm.set_value("custom_bank_account", account);
						}
					});
			};
			next(0);
		});
}

function show_payment_type_hint(frm) {
	frm.dashboard.clear_headline();

	if (frm.doc.custom_payment_type === "Cash") {
		frm.dashboard.set_headline_alert(
			"Cash — payment will be collected immediately. Submitting will " +
				"auto-create and submit a Payment Entry for the full amount.",
			"green"
		);
	} else if (frm.doc.custom_payment_type === "Bank") {
		frm.dashboard.set_headline_alert(
			"Bank — payment is received into the selected bank account. Submitting will " +
				"auto-create and submit a Payment Entry for the full amount.",
			"blue"
		);
	} else if (frm.doc.custom_payment_type === "Credit") {
		frm.dashboard.set_headline_alert(
			"Credit — no payment will be collected now. The amount will " +
				"remain outstanding after submit.",
			"orange"
		);
	}
}

frappe.ui.form.on("Sales Invoice Payment", {
	amount(frm) {
		show_payment_summary(frm);
	},
	payments_remove(frm) {
		show_payment_summary(frm);
	},
});

// Invoice Total / Payment Total / Difference under the payments grid. Display
// only -- the numbers are ERPNext's own paid_amount / outstanding_amount, and
// the submit-time rule (full payment unless Payment Type = Credit) is enforced
// server-side.
function show_payment_summary(frm) {
	const field = frm.fields_dict.payments;
	if (!field || !field.$wrapper) return;
	field.$wrapper.find(".zg-payment-summary").remove();
	if (!frm.doc.is_pos || !(frm.doc.payments || []).length || frm.doc.is_return) return;

	const total = flt(frm.doc.rounded_total) || flt(frm.doc.grand_total);
	const paid = flt(frm.doc.paid_amount);
	const diff = flt(total - paid, precision("outstanding_amount"));
	const fmt = (v) => format_currency(v, frm.doc.currency);
	const tone = diff === 0 ? "green" : "orange";
	const note =
		diff > 0 && frm.doc.custom_payment_type !== "Credit"
			? __("Allocate the full amount, or set Payment Type to Credit to leave it outstanding.")
			: diff < 0
			? __("Payments exceed the invoice total.")
			: "";
	$(`<div class="zg-payment-summary text-muted small" style="margin-top:6px">
		${__("Invoice Total")}: <b>${fmt(total)}</b> &nbsp;·&nbsp;
		${__("Payment Total")}: <b>${fmt(paid)}</b> &nbsp;·&nbsp;
		${__("Difference")}: <span class="indicator-pill ${tone}">${fmt(diff)}</span>
		${note ? `<div class="text-warning">${note}</div>` : ""}
	</div>`).appendTo(field.$wrapper);
}
