// Renew button: new membership on the same plan starting the day after this
// one ends (rules and permission checks are server-side, api/v1/gym/membership.py).
frappe.ui.form.on("ZG Gym Membership", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status === "Cancelled") return;
		frappe.db.get_value("ZG Gym Membership", { renewed_from: frm.doc.name }, "name").then((r) => {
			if (r.message && r.message.name) {
				frm.dashboard.add_comment(
					__("Renewed as {0}", [`<a href="${frappe.utils.get_form_link("ZG Gym Membership", r.message.name)}">${r.message.name}</a>`]),
					"blue",
					true
				);
				return;
			}
			frm.add_custom_button(__("Renew"), () => {
				frappe.confirm(__("Renew this membership on plan {0}?", [frm.doc.plan]), () => {
					frappe
						.xcall("zatgo_core.api.v1.gym.membership.renew", { membership: frm.doc.name })
						.then((res) => frappe.set_route("Form", "ZG Gym Membership", res.data.name));
				});
			});
		});
	},
});
