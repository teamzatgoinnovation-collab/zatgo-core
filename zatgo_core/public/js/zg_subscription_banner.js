// Trial countdown / read-only notice in the Desk header. Only a site the platform manages (frappe.boot.zatgo_core
// .subscription.managed) shows anything; every other site is untouched. The state is enforced on the server
// (services/subscription_gate.py) -- this is only the message.
(function () {
	if (!window.frappe || !window.$) return;

	const render = () => {
		const sub = (frappe.boot && frappe.boot.zatgo_core && frappe.boot.zatgo_core.subscription) || {};
		$("#zg-subscription-banner").remove();
		if (!sub.managed || sub.status === "ACTIVE") return;

		let text;
		let tone = "info";
		if (sub.read_only) {
			tone = "danger";
			text = sub.status === "SUSPENDED"
				? __("Site suspended: read-only.")
				: __("Free trial ended: this site is read-only. Activate a monthly subscription to edit.");
		} else if (sub.status === "TRIAL") {
			const days = sub.remaining_days;
			tone = days <= 5 ? "warning" : "info";
			text = days === 1 ? __("Free trial: 1 day left.") : __("Free trial: {0} days left.", [days]);
		} else {
			return;
		}

		const portal = sub.portal_url;
		const link = portal ? ` <a href="${frappe.utils.escape_html(portal)}" target="_blank" rel="noopener"
			style="color:inherit;text-decoration:underline;margin-inline-start:8px">${__("Manage subscription")}</a>` : "";
		const colors = {
			info: "#1d4ed8", warning: "#b45309", danger: "#b91c1c",
		};
		$(`<div id="zg-subscription-banner" role="status" style="background:${colors[tone]};color:#fff;
			text-align:center;padding:6px 12px;font-size:13px;font-weight:600">${frappe.utils.escape_html(text)}${link}</div>`)
			.prependTo("body");
	};

	$(document).on("startup", render);
	if (frappe.boot) $(render);
})();
