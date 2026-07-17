frappe.pages["zg-core"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("ZatGo Core"),
		single_column: true,
	});

	page.add_inner_button(__("Seed Manifests"), () => {
		frappe.call({
			method: "zatgo_core.api.v1.config.seed_bundled_manifests",
			freeze: true,
			callback() {
				frappe.show_alert({ message: __("Manifests seeded"), indicator: "green" });
				if (wrapper._zg_core_vue && wrapper._zg_core_vue.refresh) {
					wrapper._zg_core_vue.refresh();
				}
			},
		});
	});

	$(wrapper)
		.find(".layout-main-section")
		.html('<div id="zg-core-app" class="zg-core-root"></div>');
	wrapper._zg_page = page;
	zatgo.core_page.mount(wrapper);
};

frappe.pages["zg-core"].on_page_show = function (wrapper) {
	if (wrapper && wrapper._zg_core_vue && wrapper._zg_core_vue.refresh) {
		wrapper._zg_core_vue.refresh();
	}
};

frappe.provide("zatgo.core_page");

zatgo.core_page.mount = async function (wrapper) {
	const root = wrapper.querySelector("#zg-core-app");
	if (!root) return;
	if (wrapper._zg_core_app) {
		wrapper._zg_core_app.unmount();
		wrapper._zg_core_app = null;
	}

	const Vue = await zatgo.vue.ensure();
	const { ref, computed, onMounted, watch } = Vue;

	const NAV = [
		{ key: "dashboard", label: __("Dashboard"), icon: "dashboard" },
		{ key: "applications", label: __("Applications"), icon: "folder-normal" },
		{ key: "system", label: __("System"), icon: "setting", doctype: "ZG System Settings" },
		{ key: "security", label: __("Security"), icon: "lock", doctype: "ZG Security Settings" },
		{ key: "users", label: __("Users"), icon: "users", route: ["List", "User"] },
		{ key: "permissions", label: __("Permissions"), icon: "shield", route: ["permission-manager"] },
		{ key: "integrations", label: __("Integrations"), icon: "integration", doctype: "ZG Integration Settings" },
		{ key: "logs", label: __("Logs"), icon: "list", doctype: "ZG Audit Log" },
		{ key: "developer", label: __("Developer"), icon: "code", doctype: "ZG Registered Application" },
		{ key: "help", label: __("Help"), icon: "help" },
	];

	const app = Vue.createApp({
		setup() {
			const loading = ref(true);
			const collapsed = ref(false);
			const view = ref("dashboard");
			const dashboard = ref({});
			const applications = ref([]);
			const selectedApp = ref(null);
			const appDetail = ref(null);
			const selectedSection = ref(null);
			const sectionPayload = ref(null);
			const search = ref("");
			const searchHits = ref([]);
			const prefState = ref({});

			const call = (method, args) =>
				frappe
					.call({ method, args })
					.then((r) => (r.message && r.message.data) || r.message);

			const refresh = async () => {
				loading.value = true;
				try {
					const [dash, apps] = await Promise.all([
						call("zatgo_core.api.v1.config.get_dashboard"),
						call("zatgo_core.api.v1.config.get_applications"),
					]);
					dashboard.value = dash || {};
					applications.value = apps || [];
				} finally {
					loading.value = false;
				}
			};

			const selectNav = (item) => {
				if (item.doctype) {
					frappe.set_route("Form", item.doctype);
					return;
				}
				if (item.route) {
					frappe.set_route(...item.route);
					return;
				}
				view.value = item.key;
				if (item.key === "applications" && !selectedApp.value && applications.value.length) {
					openApp(applications.value[0]);
				}
			};

			const openApp = async (row) => {
				selectedApp.value = row.app_key;
				selectedSection.value = null;
				sectionPayload.value = null;
				view.value = "applications";
				appDetail.value = await call("zatgo_core.api.v1.config.get_application", {
					app_key: row.app_key,
				});
			};

			const openSection = async (section) => {
				selectedSection.value = section.section_key;
				sectionPayload.value = await call("zatgo_core.api.v1.config.get_settings", {
					app_key: selectedApp.value,
					section_key: section.section_key,
				});
				const host = sectionPayload.value && sectionPayload.value.host;
				if (host && host.type === "doctype" && host.doctype) {
					const meta = frappe.boot && frappe.get_meta
						? null
						: null;
					// Open list vs single in Desk
					frappe.model.with_doctype(host.doctype, () => {
						const m = frappe.get_meta(host.doctype);
						if (m && m.issingle) {
							frappe.set_route("Form", host.doctype);
						} else {
							frappe.set_route("List", host.doctype);
						}
					});
				}
				if (host && host.component === "module_preferences") {
					prefState.value = Object.assign({}, sectionPayload.value.data || {});
				}
			};

			const savePreferences = async () => {
				await call("zatgo_core.api.v1.config.update_settings", {
					app_key: selectedApp.value,
					section_key: selectedSection.value,
					values: JSON.stringify(prefState.value),
				});
				frappe.show_alert({ message: __("Saved"), indicator: "green" });
				await openSection({ section_key: selectedSection.value });
			};

			const runSearch = async () => {
				if (!search.value || search.value.length < 2) {
					searchHits.value = [];
					return;
				}
				searchHits.value = await call("zatgo_core.api.v1.config.search_settings", {
					query: search.value,
				});
			};

			watch(search, () => {
				frappe.utils.debounce(runSearch, 300)();
			});

			const cards = computed(() => [
				{ label: __("Installed"), value: dashboard.value.installed_apps || 0 },
				{ label: __("Enabled"), value: dashboard.value.enabled_apps || 0 },
				{ label: __("Disabled"), value: dashboard.value.disabled_apps || 0 },
				{ label: __("Pending"), value: dashboard.value.pending_configuration || 0 },
			]);

			onMounted(refresh);

			const api = { refresh };
			wrapper._zg_core_vue = api;

			return {
				loading,
				collapsed,
				view,
				dashboard,
				applications,
				selectedApp,
				appDetail,
				selectedSection,
				sectionPayload,
				search,
				searchHits,
				prefState,
				NAV,
				cards,
				selectNav,
				openApp,
				openSection,
				savePreferences,
				runSearch,
				refresh,
			};
		},
		template: `
		<div class="zg-core-shell">
			<aside class="zg-core-nav" :class="{collapsed}">
				<div class="zg-core-nav-item" @click="collapsed = !collapsed">
					<span>{{ collapsed ? '»' : '«' }}</span>
					<span v-if="!collapsed">{{ __('Collapse') }}</span>
				</div>
				<div
					v-for="item in NAV"
					:key="item.key"
					class="zg-core-nav-item"
					:class="{active: view === item.key}"
					@click="selectNav(item)"
				>
					<span>{{ item.label[0] }}</span>
					<span v-if="!collapsed">{{ item.label }}</span>
				</div>
			</aside>

			<div class="zg-core-main" v-if="view === 'dashboard'">
				<div class="zg-core-content" style="width:100%">
					<div class="zg-core-toolbar">
						<strong>{{ __('Dashboard') }}</strong>
						<button class="btn btn-default btn-sm" @click="refresh">{{ __('Refresh') }}</button>
					</div>
					<div v-if="loading" class="text-muted">{{ __('Loading…') }}</div>
					<div v-else>
						<div class="zg-core-cards">
							<div class="zg-core-card" v-for="c in cards" :key="c.label">
								<div class="text-muted">{{ c.label }}</div>
								<div class="value">{{ c.value }}</div>
							</div>
						</div>
						<p class="text-muted">{{ __('Version') }}: {{ dashboard.version || '0.1.0' }}</p>
						<p class="text-muted" v-if="dashboard.health">
							Redis: {{ dashboard.health.redis_ok ? 'OK' : 'Down' }}
							· Queues: {{ dashboard.health.queue_depth }}
							· Online: {{ dashboard.health.users_online }}
						</p>
						<h5>{{ __('Recent Changes') }}</h5>
						<ul>
							<li v-for="r in (dashboard.recent_changes || [])" :key="r.name">
								{{ r.action }} {{ r.application || '' }} {{ r.section_key || '' }}
								<span class="text-muted"> — {{ r.changed_by }}</span>
							</li>
						</ul>
					</div>
				</div>
			</div>

			<div class="zg-core-main" v-else-if="view === 'applications'">
				<aside class="zg-core-apps">
					<div class="zg-core-toolbar" style="padding:10px">
						<input class="form-control input-sm" v-model="search" :placeholder="__('Search settings…')" />
					</div>
					<div v-if="searchHits.length" style="padding:8px 12px">
						<div class="text-muted" style="font-size:11px">{{ __('Results') }}</div>
						<div
							v-for="hit in searchHits"
							:key="hit.name"
							class="zg-core-section"
							@click="openApp({app_key: hit.app_key}); openSection(hit)"
						>
							{{ hit.app_title }} / {{ hit.label }}
						</div>
					</div>
					<div
						v-for="a in applications"
						:key="a.app_key"
						class="zg-core-app-row"
						:class="{active: selectedApp === a.app_key}"
						@click="openApp(a)"
					>
						<strong>{{ a.title }}</strong>
						<div class="text-muted" style="font-size:11px">{{ a.category }} · v{{ a.version }}</div>
						<template v-if="selectedApp === a.app_key && appDetail">
							<div
								v-for="s in (appDetail.sections || [])"
								:key="s.section_key"
								class="zg-core-section"
								:class="{active: selectedSection === s.section_key}"
								@click.stop="openSection(s)"
							>
								{{ s.label }}
							</div>
						</template>
					</div>
				</aside>
				<div class="zg-core-content">
					<div v-if="!selectedApp" class="zg-core-pending">{{ __('Select an application') }}</div>
					<div v-else-if="!sectionPayload">
						<h4>{{ appDetail && appDetail.title }}</h4>
						<p class="text-muted">{{ appDetail && appDetail.description }}</p>
						<p>{{ __('Choose a settings section from the left.') }}</p>
					</div>
					<div v-else>
						<div class="zg-core-toolbar">
							<strong>{{ sectionPayload.label }}</strong>
						</div>
						<div v-if="sectionPayload.host && sectionPayload.host.component === 'module_preferences'">
							<div class="zg-core-pref-grid">
								<label class="zg-core-pref-item" v-for="(val, key) in prefState" :key="key">
									<span>{{ key.replaceAll('_', ' ') }}</span>
									<input type="checkbox" v-model="prefState[key]" true-value="1" false-value="0" />
								</label>
							</div>
							<button class="btn btn-primary btn-sm mt-3" @click="savePreferences">{{ __('Save') }}</button>
						</div>
						<div v-else-if="sectionPayload.host && sectionPayload.host.component === 'about'" class="zg-core-card">
							<div><strong>{{ sectionPayload.data.title }}</strong></div>
							<div>{{ __('Version') }}: {{ sectionPayload.data.version }}</div>
							<div class="text-muted">{{ sectionPayload.data.description }}</div>
							<div class="text-muted">{{ sectionPayload.data.app_key }}</div>
						</div>
						<div v-else-if="sectionPayload.host && sectionPayload.host.component === 'pending'" class="zg-core-pending">
							{{ (sectionPayload.data && sectionPayload.data.message) || __('Pending configuration') }}
						</div>
						<div v-else-if="sectionPayload.host && sectionPayload.host.type === 'doctype'" class="text-muted">
							{{ __('Opened Desk form for') }} {{ sectionPayload.host.doctype }}
						</div>
						<pre v-else style="font-size:12px">{{ JSON.stringify(sectionPayload.data, null, 2) }}</pre>
					</div>
				</div>
			</div>

			<div class="zg-core-main" v-else-if="view === 'help'">
				<div class="zg-core-content" style="width:100%">
					<h4>{{ __('Help') }}</h4>
					<p>{{ __('ZatGo Core is the configuration center for all ZatGo applications.') }}</p>
					<p>{{ __('Product apps register via manifests — menus are never hardcoded in Core.') }}</p>
					<p>{{ __('See docs/plugin_guide.md in the zatgo_core repository.') }}</p>
				</div>
			</div>
		</div>
		`,
	});

	wrapper._zg_core_app = app;
	app.mount(root);
};
