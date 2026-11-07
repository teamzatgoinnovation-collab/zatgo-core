// Subscription badge next to the user at the bottom of the Desk sidebar: a small heart, green with more than 30 days
// left, yellow with the days left at 30 or fewer, red once expired/read-only. Only a site the platform manages
// (frappe.boot.zatgo_core.subscription.managed) shows anything; every other site is untouched. The state is enforced
// on the server (services/subscription_gate.py) -- this is only the indicator. Hover for the full message, click for
// the customer portal.
(function () {
	if (!window.frappe || !window.$) return;

	const COLORS = { success: "#047857", warning: "#d97706", danger: "#b91c1c" };
	const HEART = "M12 21s-7.5-4.6-9.6-9.2C.9 8.4 2.9 4.5 6.6 4.5c2.1 0 3.6 1.2 4.4 2.5.8-1.3 2.3-2.5 4.4-2.5 "
		+ "3.7 0 5.7 3.9 4.2 7.3C19.5 16.4 12 21 12 21z";

	const describe = (sub) => {
		const period = sub.billing_period === "Yearly" ? __("Yearly") : __("Monthly");
		const renews = sub.paid_until ? String(sub.paid_until).slice(0, 10) : null;
		const days = typeof sub.remaining_days === "number" ? sub.remaining_days : null;
		if (sub.read_only) {
			return {
				tone: "danger",
				text: sub.status === "SUSPENDED"
					? __("Site suspended: read-only.")
					: (sub.status === "PENDING_PAYMENT" || sub.reason === "payment_overdue")
						? __("Payment overdue: this site is read-only. Renew your subscription to edit.")
						: __("Free trial ended: this site is read-only. Activate a subscription to edit."),
			};
		}
		if (sub.status === "EXPIRED" || (sub.status === "TRIAL" && days === 0)) {
			return { tone: "danger", text: __("Free trial ended. Subscribe to keep your site.") };
		}
		if (sub.status === "PENDING_PAYMENT") {
			return { tone: "danger", text: __("Payment due: please renew your subscription.") };
		}
		if (sub.status === "ACTIVE" && days === 0) {
			return { tone: "danger", text: __("Subscription expired: please renew your subscription.") };
		}
		if (sub.status === "TRIAL") {
			const text = days === 1 ? __("Free trial: 1 day left.") : __("Free trial: {0} days left.", [days]);
			return { tone: days !== null && days <= 30 ? "warning" : "success", text, days };
		}
		if (sub.status === "ACTIVE") {
			let text = renews
				? __("Subscription active · {0} · renews {1}", [period, renews])
				: __("Subscription active");
			if (days !== null && days <= 30) {
				text += " · " + (days === 1 ? __("1 day left") : __("{0} days left", [days]));
				return { tone: "warning", text, days };
			}
			return { tone: "success", text };
		}
		return null;
	};

	// Collapsed sidebar (no .expanded): the name/email is hidden, so the heart sits on the avatar's corner
	// instead of spilling past the narrow rail.
	const CSS = `.body-sidebar-container:not(.expanded) .sidebar-user-button{position:relative}
		.body-sidebar-container:not(.expanded) #zg-subscription-badge{position:absolute!important;top:0;
			inset-inline-start:18px;margin:0!important;width:14px!important;height:14px!important}
		.body-sidebar-container:not(.expanded) #zg-subscription-badge svg{width:12px;height:12px}`;

	const render = () => {
		if (!document.getElementById("zg-subscription-badge-css")) {
			$(`<style id="zg-subscription-badge-css">${CSS}</style>`).appendTo("head");
		}
		$("#zg-subscription-banner, #zg-subscription-badge").remove();
		const sub = (frappe.boot && frappe.boot.zatgo_core && frappe.boot.zatgo_core.subscription) || {};
		if (!sub.managed) return;
		const info = describe(sub);
		if (!info) return;
		const $user = $(".body-sidebar .sidebar-user-button").first();
		if (!$user.length) return;

		const portal = sub.manage_url || sub.portal_url;
		const color = COLORS[info.tone];
		const count = info.tone === "warning" && info.days !== undefined
			? `<span style="position:absolute;top:-7px;inset-inline-end:-12px;min-width:15px;height:15px;padding:0 3px;
				border-radius:8px;background:${color};color:#fff;font-size:9px;font-weight:700;line-height:15px;
				text-align:center;box-shadow:0 0 0 2px var(--subtle-fg, #fff)">${cint(info.days)}</span>`
			: "";
		const label = frappe.utils.escape_html(info.text);
		const $badge = $(`<a id="zg-subscription-badge" role="status" title="${label}" aria-label="${label}"
			${portal ? `href="${frappe.utils.escape_html(portal)}" target="_blank" rel="noopener"` : ""}
			style="position:relative;display:inline-flex;align-items:center;justify-content:center;flex:none;
				width:22px;height:22px;margin-inline-start:auto;margin-inline-end:10px;cursor:${portal ? "pointer" : "default"}">
			<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="${HEART}" fill="${color}"/></svg>
			${count}</a>`);
		// The user button routes to the user's profile on click; the badge opens the portal instead.
		$badge.on("click", (e) => {
			e.stopPropagation();
			if (!portal) e.preventDefault();
		});
		$user.append($badge);
	};

	// The sidebar is rebuilt when the workspace changes, so re-attach after every route change.
	const schedule = () => setTimeout(render, 0);
	$(document).on("startup", () => {
		schedule();
		if (frappe.router && frappe.router.on) frappe.router.on("change", schedule);
	});
	if (frappe.boot) $(schedule);
})();
