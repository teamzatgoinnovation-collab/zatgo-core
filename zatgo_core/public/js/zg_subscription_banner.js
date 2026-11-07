// Trial countdown / read-only notice in the Desk header. Only a site the platform manages (frappe.boot.zatgo_core
// .subscription.managed) shows anything; every other site is untouched. The state is enforced on the server
// (services/subscription_gate.py) -- this is only the message.
(function () {
	if (!window.frappe || !window.$) return;

	const render = () => {
		const sub = (frappe.boot && frappe.boot.zatgo_core && frappe.boot.zatgo_core.subscription) || {};
		$("#zg-subscription-banner").remove();
		if (!sub.managed) return;

		const period = sub.billing_period === "Yearly" ? __("Yearly") : __("Monthly");
		const renews = sub.paid_until ? String(sub.paid_until).slice(0, 10) : null;
		let text;
		let tone = "info";
		if (sub.read_only) {
			tone = "danger";
			text = sub.status === "SUSPENDED"
				? __("Site suspended: read-only.")
				: (sub.status === "PENDING_PAYMENT" || sub.reason === "payment_overdue")
					? __("Payment overdue: this site is read-only. Renew your subscription to edit.")
					: __("Free trial ended: this site is read-only. Activate a subscription to edit.");
		} else if (sub.status === "EXPIRED" || (sub.status === "TRIAL" && sub.remaining_days === 0)) {
			// Enforcement is off: the trial is over but nothing is locked yet.
			tone = "warning";
			text = __("Free trial ended. Subscribe to keep your site.");
		} else if (sub.status === "TRIAL") {
			const days = sub.remaining_days;
			tone = days <= 5 ? "warning" : "info";
			text = days === 1 ? __("Free trial: 1 day left.") : __("Free trial: {0} days left.", [days]);
		} else if (sub.status === "ACTIVE") {
			tone = "success";
			text = renews
				? __("Subscription active · {0} · renews {1}", [period, renews])
				: __("Subscription active");
		} else if (sub.status === "PENDING_PAYMENT") {
			tone = "warning";
			text = __("Payment due: please renew your subscription.");
		} else {
			return;
		}

		// Plan and period changes are made in the customer portal: the banner only links there.
		const portal = sub.manage_url || sub.portal_url;
		const link = portal ? ` <a href="${frappe.utils.escape_html(portal)}" target="_blank" rel="noopener"
			style="color:inherit;text-decoration:underline;margin-inline-start:8px">${__("Manage subscription")}</a>` : "";
		const colors = {
			info: "#1d4ed8", success: "#047857", warning: "#b45309", danger: "#b91c1c",
		};
		$(`<div id="zg-subscription-banner" role="status" style="background:${colors[tone]};color:#fff;
			text-align:center;padding:6px 12px;font-size:13px;font-weight:600">${frappe.utils.escape_html(text)}${link}</div>`)
			.prependTo("body");
	};

	$(document).on("startup", render);
	if (frappe.boot) $(render);
})();
