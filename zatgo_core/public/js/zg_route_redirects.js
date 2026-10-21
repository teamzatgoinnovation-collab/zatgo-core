// Old Desk routes of the apps renamed "ZatGo ..." (ZatGo AI, ZatGo Tracker, ZatGo VanSaleX): a bookmark or
// link such as /desk/tracker opens the renamed workspace instead of "not found". frappe.re_route is Desk's
// own route remap (router.js re_route()): key = the old sub-path, value = the new one.
(function () {
	if (!window.frappe) return;
	frappe.re_route = frappe.re_route || {};
	Object.assign(frappe.re_route, {
		"tracker": "zatgo-tracker",
		"task-management": "zatgo-tracker",
		"ai-admin": "zatgo-ai",
		"chat-ai": "zatgo-ai",
		"vansalex": "zatgo-vansalex",
	});
})();
