/**
 * Vue 3 bootstrap for ZatGo Core Desk pages (no Node build required).
 * Uses vendored vue.global.prod.js when Desk does not expose window.Vue.
 * Conventions: Docs/Foundation/DESK_VUE.md
 */
frappe.provide("zatgo.vue");

zatgo.vue.VUE_ASSET = "/assets/zatgo_core/js/vendor/vue.global.prod.js";

zatgo.vue.ensure = function () {
	if (window.Vue && window.Vue.createApp) {
		return Promise.resolve(window.Vue);
	}
	return new Promise((resolve, reject) => {
		frappe.require(zatgo.vue.VUE_ASSET, () => {
			if (window.Vue && window.Vue.createApp) {
				resolve(window.Vue);
			} else {
				reject(new Error("Vue failed to load"));
			}
		});
	});
};

zatgo.vue.mount = async function (el, options) {
	const Vue = await zatgo.vue.ensure();
	const app = Vue.createApp(options);
	app.mount(el);
	return app;
};
