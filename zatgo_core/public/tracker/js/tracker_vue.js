/**
 * Vue 3 bootstrap for Tracker Desk pages (no Node / Vite in bench).
 * See Docs/Foundation/DESK_VUE.md
 */
frappe.provide("tracker.vue");

tracker.vue.VUE_ASSET = "/assets/zatgo_core/tracker/js/vendor/vue.global.prod.js";

tracker.vue.ensure = function () {
	if (window.Vue && window.Vue.createApp) {
		return Promise.resolve(window.Vue);
	}
	return new Promise((resolve, reject) => {
		frappe.require(tracker.vue.VUE_ASSET, () => {
			if (window.Vue && window.Vue.createApp) {
				resolve(window.Vue);
			} else {
				reject(new Error("Vue failed to load from " + tracker.vue.VUE_ASSET));
			}
		});
	});
};

tracker.vue.mount = async function (el, options) {
	const Vue = await tracker.vue.ensure();
	const app = Vue.createApp(options);
	app.mount(el);
	return app;
};

tracker.vue.unmount = function (app) {
	if (app && typeof app.unmount === "function") {
		app.unmount();
	}
};
