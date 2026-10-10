/**
 * Desk Vue bootstrap for Chat AI (vendored Vue 3, no Vite).
 * See Docs/Foundation/DESK_VUE.md
 */
frappe.provide("chat_ai.vue");

chat_ai.vue.VUE_ASSET = "/assets/zatgo_core/chat_ai/js/vendor/vue.global.prod.js";

chat_ai.vue.ensure = function () {
	return new Promise((resolve, reject) => {
		if (window.Vue && window.Vue.createApp) {
			resolve(window.Vue);
			return;
		}
		frappe.require(chat_ai.vue.VUE_ASSET, () => {
			if (window.Vue && window.Vue.createApp) {
				resolve(window.Vue);
			} else {
				reject(new Error("Vue failed to load from " + chat_ai.vue.VUE_ASSET));
			}
		});
	});
};

chat_ai.vue.mount = async function (el, options) {
	const Vue = await chat_ai.vue.ensure();
	const app = Vue.createApp(options);
	app.mount(el);
	return app;
};
