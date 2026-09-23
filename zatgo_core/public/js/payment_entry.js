// Shows the selected party's live outstanding balance (computed by
// ERPNext's GL via zatgo_core.services.erpnext_reads.get_party_balance --
// never derived client-side) as a headline alert on Payment Entry, so the
// user can see what is actually owed before entering an amount.

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
	frm.dashboard.clear_headline();

	if (!["Customer", "Supplier"].includes(frm.doc.party_type) || !frm.doc.party || !frm.doc.company) {
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
				return;
			}
			const d = r.message.data;
			const party_label = frm.doc.party_name || frm.doc.party;
			const amount = format_currency(Math.abs(d.display_amount), d.currency);

			if (Math.abs(d.display_amount) < 0.005) {
				frm.dashboard.set_headline_alert(__("{0} has no outstanding balance", [party_label]), "blue");
			} else if (d.display_amount > 0) {
				const message =
					frm.doc.party_type === "Customer"
						? __("{0} owes you {1}", [party_label, amount])
						: __("You owe {0}: {1}", [party_label, amount]);
				frm.dashboard.set_headline_alert(message, "orange");
			} else {
				const message =
					frm.doc.party_type === "Customer"
						? __("{0} has a credit balance of {1}", [party_label, amount])
						: __("{0} has a credit balance of {1} with you", [party_label, amount]);
				frm.dashboard.set_headline_alert(message, "green");
			}
		},
	});
}
