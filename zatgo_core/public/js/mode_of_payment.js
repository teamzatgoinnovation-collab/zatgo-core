// Allowed Accounts (custom_zg_accounts, ZG Mode of Payment Account): only
// ledger accounts of the row's company that can actually hold money. The
// server re-validates (services/payment_allocation.validate_mode_of_payment).

frappe.ui.form.on("Mode of Payment", {
	setup(frm) {
		frm.set_query("account", "custom_zg_accounts", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				filters: {
					company: row.company,
					is_group: 0,
					disabled: 0,
					account_type: ["not in", ["Receivable", "Payable"]],
				},
			};
		});
	},
});
