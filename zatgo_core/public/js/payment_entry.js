// Shows the selected party's live outstanding balance (computed by
// ERPNext's GL via zatgo_core.services.erpnext_reads.get_party_balance --
// never derived client-side) in the read-only "Party Balance" field, so
// the user can see what is actually owed before entering an amount.

frappe.ui.form.on("Payment Entry", {
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
	},
});

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
