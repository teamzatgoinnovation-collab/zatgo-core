frappe.pages["tracker-org"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Task Management Org Setup"),
		single_column: true,
	});

	page.main.html('<div class="tracker-org-root"></div>');
	const el = page.main.find(".tracker-org-root")[0];

	const OrgApp = {
		data() {
			return {
				company: "",
				employees: [],
				caps: {
					can_create_top: false,
					can_assign_org: false,
					can_create_sub: false,
					can_create_worker: false,
				},
				hasBranch: false,
				busy: false,
				/** collapsed node keys: company root uses "__company__", else employee name */
				collapsed: {},
				selected: null,
			};
		},
		computed: {
			roleOptions() {
				const opts = [];
				if (this.caps.can_create_sub) opts.push("Sub");
				if (this.caps.can_create_worker) opts.push("Worker");
				return opts.length ? opts : ["Sub", "Worker"];
			},
			childrenMap() {
				const map = {};
				(this.employees || []).forEach((e) => {
					const p = e.reports_to || "";
					(map[p] = map[p] || []).push(e);
				});
				Object.keys(map).forEach((k) => {
					map[k].sort((a, b) =>
						String(a.employee_name || a.name).localeCompare(
							String(b.employee_name || b.name)
						)
					);
				});
				return map;
			},
			rootEmployees() {
				const byName = {};
				(this.employees || []).forEach((e) => (byName[e.name] = e));
				return (this.employees || []).filter(
					(e) => !e.reports_to || !byName[e.reports_to]
				);
			},
			/** Flattened visible rows like Chart of Accounts list */
			coaRows() {
				const out = [];
				const walk = (emp, depth) => {
					const kids = this.childrenMap[emp.name] || [];
					const key = emp.name;
					const isOpen = !this.collapsed[key];
					out.push({
						type: "employee",
						key,
						emp,
						depth,
						hasChildren: kids.length > 0,
						isOpen,
						childCount: kids.length,
					});
					if (isOpen) {
						kids.forEach((c) => walk(c, depth + 1));
					}
				};
				// Company root (like CoA company node)
				const companyOpen = !this.collapsed.__company__;
				out.push({
					type: "company",
					key: "__company__",
					depth: 0,
					hasChildren: this.rootEmployees.length > 0,
					isOpen: companyOpen,
					childCount: this.rootEmployees.length,
					label: this.company || __("Company"),
				});
				if (companyOpen) {
					this.rootEmployees.forEach((r) => walk(r, 1));
				}
				return out;
			},
			isSystemManager() {
				return (
					frappe.session.user === "Administrator" ||
					(frappe.user_roles || []).includes("System Manager") ||
					!!this.caps.can_create_top
				);
			},
		},
		mounted() {
			this.refresh();
		},
		methods: {
			call(method, args) {
				return new Promise((resolve, reject) => {
					frappe.call({
						method,
						args: args || {},
						callback: (r) => {
							const msg = r.message;
							if (msg && msg.success === false) {
								const err =
									(msg.error && msg.error.message) ||
									msg.message ||
									"Request failed";
								reject(new Error(err));
								return;
							}
							resolve(msg && msg.data !== undefined ? msg.data : msg);
						},
						error: (e) => reject(e),
					});
				});
			},
			async refresh() {
				try {
					const [tree, caps] = await Promise.all([
						this.call("zatgo_core.tracker.api.v1.hierarchy.org_tree"),
						this.call("zatgo_core.tracker.api.v1.hierarchy.my_tree"),
					]);
					this.company = (tree && tree.company) || "";
					this.employees = (tree && tree.employees) || [];
					this.hasBranch = this.employees.some((e) =>
						Object.prototype.hasOwnProperty.call(e || {}, "branch")
					);
					this.caps = {
						can_create_top: !!(caps && caps.can_create_top),
						can_assign_org: !!(caps && caps.can_assign_org),
						can_create_sub: !!(caps && caps.can_create_sub),
						can_create_worker: !!(caps && caps.can_create_worker),
					};
				} catch (e) {
					frappe.msgprint({
						title: __("Org"),
						message: String(e.message || e),
						indicator: "red",
					});
				}
			},
			toggle(key) {
				this.collapsed = {
					...this.collapsed,
					[key]: !this.collapsed[key],
				};
			},
			expandAll() {
				this.collapsed = {};
			},
			collapseAll() {
				const next = { __company__: true };
				(this.employees || []).forEach((e) => {
					if ((this.childrenMap[e.name] || []).length) next[e.name] = true;
				});
				this.collapsed = next;
			},
			selectRow(key) {
				this.selected = key;
			},
			roleBadgeClass(role) {
				const r = (role || "").toLowerCase();
				if (r === "top") return "tracker-role-badge role-top";
				if (r === "sub") return "tracker-role-badge role-sub";
				if (r === "worker") return "tracker-role-badge role-worker";
				return "tracker-role-badge";
			},
			showPassword(pwd, email) {
				if (!pwd) return;
				frappe.msgprint({
					title: __("Temporary password"),
					message: __(
						"Copy this password now — it will not be shown again.<br>User {0}: <code>{1}</code>",
						[
							frappe.utils.escape_html(email || ""),
							frappe.utils.escape_html(String(pwd)),
						]
					),
					indicator: "orange",
				});
			},
			/** Add under company root = Create Top; under person = Assign as child */
			openAddUnder(parentEmp) {
				if (!parentEmp) {
					this.openCreateTopDialog();
					return;
				}
				this.openAssignDialog(parentEmp);
			},
			openCreateTopDialog() {
				if (!this.caps.can_create_top && !this.isSystemManager) {
					frappe.msgprint(__("Only System Manager can create Top."));
					return;
				}
				const fields = [
					{ fieldname: "email", label: __("Email"), fieldtype: "Data", reqd: 1 },
					{
						fieldname: "full_name",
						label: __("Full name"),
						fieldtype: "Data",
						reqd: 1,
					},
					{
						fieldname: "company",
						label: __("Company"),
						fieldtype: "Link",
						options: "Company",
						reqd: 1,
						default: this.company,
					},
				];
				if (this.hasBranch) {
					fields.push({
						fieldname: "branch",
						label: __("Branch"),
						fieldtype: "Data",
					});
				}
				const d = new frappe.ui.Dialog({
					title: __("Add Top under {0}", [this.company || __("Company")]),
					fields,
					primary_action_label: __("Create Top"),
					primary_action: async (values) => {
						this.busy = true;
						try {
							const args = { ...values };
							if (!args.branch) delete args.branch;
							const data = await this.call(
								"zatgo_core.tracker.api.v1.hierarchy.create_top_member",
								args
							);
							this.showPassword(data && data.temporary_password, args.email);
							d.hide();
							frappe.show_alert({
								message: __("Top created"),
								indicator: "green",
							});
							await this.refresh();
						} catch (e) {
							frappe.msgprint({
								title: __("Create Top failed"),
								message: String(e.message || e),
								indicator: "red",
							});
						} finally {
							this.busy = false;
						}
					},
				});
				d.show();
			},
			openAssignDialog(parentEmp) {
				if (!this.caps.can_assign_org) {
					frappe.msgprint(__("You cannot assign under this person."));
					return;
				}
				const roleOpts = this.roleOptions.join("\n");
				const fields = [
					{ fieldname: "email", label: __("Email"), fieldtype: "Data", reqd: 1 },
					{
						fieldname: "full_name",
						label: __("Full name"),
						fieldtype: "Data",
						reqd: 1,
					},
					{
						fieldname: "company",
						label: __("Company"),
						fieldtype: "Link",
						options: "Company",
						reqd: 1,
						default: this.company,
					},
					{
						fieldname: "role",
						label: __("Role"),
						fieldtype: "Select",
						options: roleOpts,
						reqd: 1,
						default: this.roleOptions[0] || "Worker",
					},
					{
						fieldname: "reports_to_note",
						fieldtype: "HTML",
						options: `<p class="text-muted small">${__(
							"Will report to"
						)}: <strong>${frappe.utils.escape_html(
							parentEmp.employee_name || parentEmp.name
						)}</strong></p>`,
					},
				];
				if (this.hasBranch) {
					fields.splice(3, 0, {
						fieldname: "branch",
						label: __("Branch"),
						fieldtype: "Data",
					});
				}
				const d = new frappe.ui.Dialog({
					title: __("Add under {0}", [parentEmp.employee_name || parentEmp.name]),
					fields,
					primary_action_label: __("Add"),
					primary_action: async (values) => {
						this.busy = true;
						try {
							const args = {
								email: values.email,
								full_name: values.full_name,
								company: values.company,
								role: values.role,
								reports_to: parentEmp.name,
							};
							if (values.branch) args.branch = values.branch;
							const data = await this.call(
								"zatgo_core.tracker.api.v1.hierarchy.assign_org_member",
								args
							);
							this.showPassword(data && data.temporary_password, args.email);
							d.hide();
							frappe.show_alert({
								message: __("Member assigned"),
								indicator: "green",
							});
							// keep parent expanded
							const next = { ...this.collapsed };
							delete next[parentEmp.name];
							this.collapsed = next;
							await this.refresh();
						} catch (e) {
							frappe.msgprint({
								title: __("Assign failed"),
								message: String(e.message || e),
								indicator: "red",
							});
						} finally {
							this.busy = false;
						}
					},
				});
				d.show();
			},
			editEmployee(name) {
				const emp = (this.employees || []).find((e) => e.name === name);
				if (!emp) return;
				const d = new frappe.ui.Dialog({
					title: __("Edit") + ": " + (emp.employee_name || name),
					fields: [
						{
							fieldname: "tracker_org_role",
							label: __("Org Role"),
							fieldtype: "Select",
							options: "\nTop\nSub\nWorker",
							default: emp.tracker_org_role || "",
						},
						{
							fieldname: "reports_to",
							label: __("Reports To"),
							fieldtype: "Link",
							options: "Employee",
							default: emp.reports_to || "",
						},
						{
							fieldname: "tracker_role",
							label: __("Frappe Role"),
							fieldtype: "Select",
							options: "\nTracker Top\nTracker Sub\nTracker Worker",
							default: (emp.roles && emp.roles[0]) || "",
						},
					],
					primary_action_label: __("Save"),
					primary_action: async (values) => {
						try {
							await this.call("zatgo_core.tracker.api.v1.hierarchy.update_employee_org", {
								employee: name,
								tracker_org_role: values.tracker_org_role || "",
								reports_to: values.reports_to || "",
								tracker_role: values.tracker_role || "",
							});
							d.hide();
							await this.refresh();
						} catch (e) {
							frappe.msgprint({
								title: __("Save failed"),
								message: String(e.message || e),
								indicator: "red",
							});
						}
					},
				});
				d.show();
			},
			canAddUnder(row) {
				if (row.type === "company") {
					return !!(this.caps.can_create_top || this.isSystemManager);
				}
				if (row.type === "employee") {
					const role = (row.emp.tracker_org_role || "").toLowerCase();
					if (role === "worker") return false;
					return !!this.caps.can_assign_org;
				}
				return false;
			},
			async seedDemo() {
				frappe.confirm(__("Seed demo org users? Password Tracker@123."), async () => {
					try {
						await this.call("zatgo_core.tracker.api.v1.hierarchy.seed_demo");
						frappe.show_alert({ message: __("Demo org seeded"), indicator: "green" });
						await this.refresh();
					} catch (e) {
						frappe.msgprint(String(e.message || e));
					}
				});
			},
			async seedWork() {
				frappe.confirm(
					__("Seed full demo: org, project, tasks, tickets, timesheets?"),
					async () => {
						try {
							await this.call("zatgo_core.tracker.api.v1.hierarchy.seed_demo_work");
							frappe.show_alert({
								message: __("Demo work seeded"),
								indicator: "green",
							});
							await this.refresh();
						} catch (e) {
							frappe.msgprint(String(e.message || e));
						}
					}
				);
			},
		},
		template: `
		<div class="tracker-org tracker-page">
			<div class="tracker-brand">
				<div class="tracker-brand-left">
					<h2 class="tracker-brand-title">{{ __("Org Setup") }}</h2>
				</div>
				<span class="tracker-company-pill">{{ __("Company") }}: <strong>{{ company || "—" }}</strong></span>
			</div>
			<p class="tracker-brand-sub">
				{{ __("Organization chart — expand nodes and Add under a person, same idea as Chart of Accounts.") }}
			</p>

			<div class="tracker-coa-toolbar">
				<button class="btn btn-default btn-xs" type="button" @click="expandAll">{{ __("Expand All") }}</button>
				<button class="btn btn-default btn-xs" type="button" @click="collapseAll">{{ __("Collapse All") }}</button>
				<button
					class="btn btn-primary btn-xs"
					type="button"
					v-if="caps.can_create_top || isSystemManager"
					@click="openCreateTopDialog"
				>{{ __("Add Top") }}</button>
				<span class="text-muted small" style="margin-left:auto">{{ employees.length }} {{ __("people") }}</span>
				<template v-if="isSystemManager">
					<button class="btn btn-default btn-xs" type="button" @click="seedDemo">{{ __("Seed org") }}</button>
					<button class="btn btn-warning btn-xs" type="button" @click="seedWork">{{ __("Seed work") }}</button>
				</template>
			</div>

			<div class="tracker-coa-tree">
				<div v-if="!employees.length && !(caps.can_create_top || isSystemManager)" class="tracker-empty">
					<div class="tracker-empty-title">{{ __("No active employees") }}</div>
					<div class="tracker-empty-hint">{{ __("Ask a System Manager to create a Top for this company.") }}</div>
				</div>
				<div v-else-if="!employees.length" class="tracker-empty">
					<div class="tracker-empty-title">{{ __("Empty organization") }}</div>
					<div class="tracker-empty-hint">{{ __("Add Top under the company node to start the tree.") }}</div>
					<button class="btn btn-primary btn-sm" type="button" @click="openCreateTopDialog">{{ __("Add Top") }}</button>
				</div>

				<div
					v-for="row in coaRows"
					:key="row.key"
					class="tracker-coa-row"
					:class="{
						selected: selected === row.key,
						'is-company': row.type === 'company',
						'is-group': row.hasChildren,
						'is-leaf': !row.hasChildren && row.type === 'employee'
					}"
					:style="{ paddingLeft: (12 + row.depth * 22) + 'px' }"
					@click="selectRow(row.key)"
				>
					<button
						type="button"
						class="tracker-coa-toggle"
						:class="{ invisible: !row.hasChildren }"
						@click.stop="row.hasChildren && toggle(row.key)"
						:aria-label="row.isOpen ? __('Collapse') : __('Expand')"
					>
						<span class="tracker-coa-chevron" :class="{ open: row.isOpen }">▸</span>
					</button>

					<span class="tracker-coa-icon" :class="'icon-' + (row.type === 'company' ? 'company' : (row.hasChildren ? 'group' : 'leaf'))" aria-hidden="true"></span>

					<div class="tracker-coa-label">
						<template v-if="row.type === 'company'">
							<strong class="tracker-coa-name">{{ row.label }}</strong>
							<span class="tracker-coa-meta">{{ __("Company") }} · {{ row.childCount }} {{ __("roots") }}</span>
						</template>
						<template v-else>
							<strong class="tracker-coa-name">{{ row.emp.employee_name || row.emp.name }}</strong>
							<span class="tracker-coa-meta">
								{{ row.emp.user_id || __("no user") }}
								<span v-if="row.emp.branch"> · {{ row.emp.branch }}</span>
								<span v-if="row.hasChildren"> · {{ row.childCount }} {{ __("reports") }}</span>
							</span>
						</template>
					</div>

					<span
						v-if="row.type === 'employee'"
						:class="roleBadgeClass(row.emp.tracker_org_role)"
					>{{ row.emp.tracker_org_role || "—" }}</span>

					<div class="tracker-coa-actions" @click.stop>
						<button
							v-if="canAddUnder(row)"
							type="button"
							class="btn btn-xs btn-default"
							@click="row.type === 'company' ? openCreateTopDialog() : openAddUnder(row.emp)"
						>{{ __("Add Child") }}</button>
						<button
							v-if="row.type === 'employee'"
							type="button"
							class="btn btn-xs btn-default"
							@click="editEmployee(row.emp.name)"
						>{{ __("Edit") }}</button>
					</div>
				</div>
			</div>
		</div>
		`,
	};

	tracker.vue.mount(el, OrgApp).then((app) => {
		wrapper.tracker_org_vue = app;
	});

	page.set_primary_action(__("Refresh"), () => {
		const proxy =
			wrapper.tracker_org_vue &&
			wrapper.tracker_org_vue._instance &&
			wrapper.tracker_org_vue._instance.proxy;
		if (proxy && proxy.refresh) proxy.refresh();
	});
};

frappe.pages["tracker-org"].on_page_show = function (wrapper) {
	const now = Date.now();
	if (wrapper._tracker_org_show && now - wrapper._tracker_org_show < 1000) return;
	wrapper._tracker_org_show = now;
	const proxy =
		wrapper.tracker_org_vue &&
		wrapper.tracker_org_vue._instance &&
		wrapper.tracker_org_vue._instance.proxy;
	if (proxy && proxy.refresh) proxy.refresh();
};
