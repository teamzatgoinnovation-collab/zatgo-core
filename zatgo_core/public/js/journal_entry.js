// Narration (`remark`): once the user writes one, tick ERPNext's own
// "Custom Remark" so save doesn't rebuild it from the references. The server
// does the same for later edits (zatgo_core/services/narration.py).

frappe.ui.form.on("Journal Entry", {
	remark(frm) {
		if (frm.doc.docstatus !== 0) return;
		// Written -> keep it; cleared -> back to ERPNext's auto-text.
		const custom = (frm.doc.remark || "").trim() ? 1 : 0;
		if (frm.doc.custom_remark !== custom) frm.set_value("custom_remark", custom);
	},
});
