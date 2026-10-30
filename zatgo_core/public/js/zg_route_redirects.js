// Old Desk routes of the apps: a bookmark or link such as /desk/tracker or /desk/zatgo-vansalex opens the app's
// workspace (its own sidebar opens with it) instead of "not found". frappe.re_route is
// Desk's own route remap (router.js re_route()): key = the old sub-path, value = the new one.
//
// The first block is the fixed history (the names before the apps were renamed "ZatGo ..."); the server's
// list (frappe.boot.zatgo_core.app_routes, services/app_page.py::old_url_redirects) comes after it and covers
// every app's workspace name, current or old, and the retired /desk/zg-app/<app> pages, so it wins where both name a key.
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
	const boot = (frappe.boot && frappe.boot.zatgo_core) || {};
	Object.assign(frappe.re_route, boot.app_routes || {});
})();
