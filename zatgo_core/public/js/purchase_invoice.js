// Payment Type UX hint for Purchase Invoice (custom_payment_type,
// patches/v0_2_3/add_purchase_invoice_payment_type_field.py). Purely
// visual -- the actual Cash/Credit handling lives server-side in
// zatgo_core.services.invoice_cash_payment_service. Mirrors
// public/js/sales_invoice.js (Pay direction instead of Receive).
//
// Also filters + pre-fills Cash Account (custom_cash_account,
// patches/v0_2_3/add_purchase_invoice_cash_account_field.py): the picker
// only ever offers this company's actual Cash-type ledger accounts
// (matching the same account_type check the server re-validates anyway),
// and picking "Cash" pre-fills it from the "Cash" Mode of Payment's
// configured default account for this company -- just a starting
// suggestion, still editable for companies running more than one till.
// The field is genuinely required server-side (not just cosmetically via
// mandatory_depends_on -- see invoice_cash_payment_service.py for why
// that alone isn't enough).
//
// Payment Type "Bank" works the same way with Bank Account
// (custom_bank_account, patches/v0_2_8/add_purchase_invoice_bank_payment_fields.py):
// only Bank-type ledger accounts, pre-filled from the Bank-type Mode of
// Payment's default account for this company.

frappe.ui.form.on("Purchase Invoice", {
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
	},
	custom_payment_type(frm) {
		show_payment_type_hint(frm);
		prefill_cash_account(frm);
		prefill_bank_account(frm);
	},
	refresh(frm) {
		show_payment_type_hint(frm);
	},
});

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
			"Cash — payment will be made to the supplier immediately. Submitting " +
				"will auto-create and submit a Payment Entry for the full amount.",
			"green"
		);
	} else if (frm.doc.custom_payment_type === "Bank") {
		frm.dashboard.set_headline_alert(
			"Bank — payment will be made to the supplier from the selected bank account. " +
				"Submitting will auto-create and submit a Payment Entry for the full amount.",
			"blue"
		);
	} else if (frm.doc.custom_payment_type === "Credit") {
		frm.dashboard.set_headline_alert(
			"Credit — no payment will be made now. The amount will remain " +
				"outstanding after submit.",
			"orange"
		);
	}
}
