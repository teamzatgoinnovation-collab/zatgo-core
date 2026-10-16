# Kasib Asia Tax Return Invoice — reference snapshot

Separate, DB-stored Print Format on `kasibasia.zatgoinnovation.com`
(`standard: "No"`, `module: "Accounts"`), always drawn on the return artwork. Not
a zatgo_core fixture; these two files are a plain reference copy of what is
live -- editing them does nothing on their own. Update the live doc directly
(`frappe.get_doc("Print Format", "Kasib Asia Tax Return Invoice")`, set
`.html`/`.css`, `.save()`). Sibling of `../kasib_asia_tax_invoice/`, which also
prints returns via its credit-note branch and is the Sales Invoice default; this
one is an older, simpler variant (black text, no payment badge).
