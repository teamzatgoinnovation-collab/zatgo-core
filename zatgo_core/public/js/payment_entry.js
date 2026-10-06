// Shows the selected party's live outstanding balance (computed by
// ERPNext's GL via zatgo_core.services.erpnext_reads.get_party_balance --
// never derived client-side) in the read-only "Party Balance" field, so
// the user can see what is actually owed before entering an amount.

frappe.ui.form.on("Payment Entry", {
	// Narration (`remarks`): once the user writes one, tick ERPNext's own
	// "Custom Remarks" so save doesn't replace it with auto-text. The server
	// does the same for later edits (services/narration.py).
	remarks: function (frm) {
		if (frm.doc.docstatus !== 0) return;
		// Written -> keep it; cleared -> back to ERPNext's auto-text.
		const custom = (frm.doc.remarks || "").trim() ? 1 : 0;
		if (frm.doc.custom_remarks !== custom) frm.set_value("custom_remarks", custom);
	},
	setup: function (frm) {
		frm.set_query("account", "custom_payment_details", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				query: "zatgo_core.api.v1.accounting.payment_methods.account_query",
				filters: { mode_of_payment: row.mode_of_payment, company: doc.company },
			};
		});
	},
	payment_type: function (frm) {
		sync_payment_details_account(frm);
		sync_payment_details_total(frm);
	},
	party: function (frm) {
		show_party_balance(frm);
	},
	party_type: function (frm) {
		show_party_balance(frm);
	},
	company: function (frm) {
		show_party_balance(frm);
	},
	refresh: function (frm) {
		show_party_balance(frm);
		show_payment_details_summary(frm);
	},
});

// Payment Details (ZG Payment Allocation): split the money across payment
// methods / accounts. Picking a method pre-fills its default account; the
// first row's account becomes Account Paid To (Receive) / Paid From (Pay) --
// mandatory on the form, and ERPNext's own handlers then fetch its currency --
// and the rows' total drives Received Amount / Paid Amount. The server
// re-does all of this and posts the GL split
// (services/payment_allocation.py, overrides/payment_entry.py).
frappe.ui.form.on("ZG Payment Allocation", {
	mode_of_payment: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.mode_of_payment || !frm.doc.company) return;
		frappe.call({
			method: "zatgo_core.api.v1.accounting.payment_methods.default_account",
			args: { mode_of_payment: row.mode_of_payment, company: frm.doc.company },
			callback: (r) => frappe.model.set_value(cdt, cdn, "account", r.message || ""),
		});
	},
	account: function (frm) {
		sync_payment_details_account(frm);
	},
	amount: function (frm) {
		sync_payment_details_total(frm);
	},
	custom_payment_details_remove: function (frm) {
		sync_payment_details_account(frm);
		sync_payment_details_total(frm);
	},
});

function sync_payment_details_account(frm) {
	const first = (frm.doc.custom_payment_details || [])[0];
	const side = frm.doc.payment_type === "Receive" ? "paid_to" : frm.doc.payment_type === "Pay" ? "paid_from" : null;
	if (!first || !first.account || !side || frm.doc.docstatus !== 0) return;
	if (frm.doc[side] !== first.account) {
		frm.set_value(side, first.account).then(() => sync_payment_details_total(frm));
	}
}

function payment_details_target(frm) {
	if (frm.doc.payment_type === "Receive") return "received_amount";
	if (frm.doc.payment_type === "Pay") return "paid_amount";
	return null;
}

function sync_payment_details_total(frm) {
	const rows = frm.doc.custom_payment_details || [];
	const target = payment_details_target(frm);
	if (rows.length && target && frm.doc.docstatus === 0) {
		const total = rows.reduce((sum, r) => sum + flt(r.amount), 0);
		if (flt(frm.doc[target]) !== total) frm.set_value(target, total);
		if (target === "received_amount" && frm.doc.paid_from_account_currency === frm.doc.paid_to_account_currency) {
			if (flt(frm.doc.paid_amount) !== total) frm.set_value("paid_amount", total);
		}
	}
	show_payment_details_summary(frm);
}

function show_payment_details_summary(frm) {
	const field = frm.fields_dict.custom_payment_details;
	if (!field || !field.$wrapper) return;
	field.$wrapper.find(".zg-payment-summary").remove();
	const rows = frm.doc.custom_payment_details || [];
	const target = payment_details_target(frm);
	if (!rows.length || !target) return;

	const total = rows.reduce((sum, r) => sum + flt(r.amount), 0);
	const expected = flt(frm.doc[target]);
	const diff = flt(expected - total, precision("paid_amount"));
	const currency = rows[0].account_currency || frm.doc.paid_to_account_currency;
	const fmt = (v) => format_currency(v, currency);
	$(`<div class="zg-payment-summary text-muted small" style="margin-top:6px">
		${target === "received_amount" ? __("Received Amount") : __("Paid Amount")}: <b>${fmt(expected)}</b> &nbsp;·&nbsp;
		${__("Payment Total")}: <b>${fmt(total)}</b> &nbsp;·&nbsp;
		${__("Difference")}: <span class="indicator-pill ${diff === 0 ? "green" : "orange"}">${fmt(diff)}</span>
	</div>`).appendTo(field.$wrapper);
}

function show_party_balance(frm) {
	if (!frm.fields_dict.custom_party_balance) {
		return;
	}

	if (!["Customer", "Supplier"].includes(frm.doc.party_type) || !frm.doc.party || !frm.doc.company) {
		frm.set_value("custom_party_balance", "");
		return;
	}

	frappe.call({
		method: "zatgo_core.api.v1.accounting.payments.party_balance",
		args: {
			party_type: frm.doc.party_type,
			party: frm.doc.party,
			company: frm.doc.company,
		},
		callback: function (r) {
			if (!r.message || !r.message.success) {
				frm.set_value("custom_party_balance", "");
				return;
			}
			const d = r.message.data;
			const amount = format_currency(Math.abs(d.display_amount), d.currency);

			let text;
			if (Math.abs(d.display_amount) < 0.005) {
				text = __("No outstanding balance");
			} else if (d.display_amount > 0) {
				text =
					frm.doc.party_type === "Customer"
						? __("{0} (owes you)", [amount])
						: __("{0} (you owe)", [amount]);
			} else {
				text = __("{0} (credit balance)", [amount]);
			}
			frm.set_value("custom_party_balance", text);
		},
	});
}
