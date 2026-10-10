frappe.pages["tracker-workbench"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Task Management"),
		single_column: true,
	});

	page.main.html('<div class="tracker-workbench-root"></div>');
	const el = page.main.find(".tracker-workbench-root")[0];

	const emptyCaps = () => ({
		can_manage_work: false,
		can_review: false,
		can_submit_timesheets: false,
		can_approve_timesheets: false,
		can_close_project: false,
		can_create_top: false,
		can_assign_org: false,
		can_create_sub: false,
		can_create_worker: false,
		is_worker_only: false,
		is_top: false,
		is_lead_or_above: false,
	});

	const WorkbenchApp = {
		data() {
			return {
				caps: emptyCaps(),
				roleLabel: "",
				tab: "tasks",
				tasks: [],
				tickets: [],
				running: [],
				review: [],
				activityFeed: [],
				activityScope: "team",
				activityAction: "",
				overview: {
					counts: {},
					status: "Pending Review",
					items: [],
					running: 0,
					timesheet_drafts: 0,
				},
				selected: null,
				selectedTicket: null,
				active: null,
				scope: "mine",
				projectFilter: "",
				statusFilter: "",
				people: [],
				activityTypes: [],
				activityType: "",
				busy: false,
				elapsedTimer: null,
				tick: 0,
			};
		},
		computed: {
			showOverview() {
				return !!(this.caps.can_review || this.caps.is_top);
			},
			activeLabel() {
				if (!this.active) return __("None");
				const t = this.active.task || this.active.project || this.active.name;
				const at = this.active.activity_type ? ` · ${this.active.activity_type}` : "";
				return `${this.active.status}: ${t}${at}`;
			},
			elapsedText() {
				void this.tick;
				if (!this.active) return "";
				let sec = Number(this.active.elapsed_seconds || this.active.duration_seconds || 0);
				if (this.active.status === "Running" && this.active._tick_at) {
					sec += (Date.now() - this.active._tick_at) / 1000;
				}
				const h = Math.floor(sec / 3600);
				const m = Math.floor((sec % 3600) / 60);
				const s = Math.floor(sec % 60);
				return __("Elapsed") + ": " + `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
			},
			canStart() {
				if (!this.selected || this.busy) return false;
				if (this.active && this.active.status === "Running" && this.active.task === this.selected) {
					return false;
				}
				const row =
					(this.tasks || []).find((t) => t.name === this.selected) ||
					(this.overview.items || []).find((t) => t.name === this.selected) ||
					(this.review || []).find((t) => t.name === this.selected);
				if (row && Array.isArray(row.assignees) && row.assignees.length) {
					return row.assignees.includes(frappe.session.user);
				}
				// Unknown assignees (e.g. overview without enrich) — allow click; backend enforces
				return true;
			},
			canPause() {
				return !!(this.active && this.active.status === "Running");
			},
			canStop() {
				return !!(
					this.active &&
					(this.active.status === "Running" || this.active.status === "Paused")
				);
			},
			statusChips() {
				const order = ["Open", "Working", "Pending Review", "Completed"];
				const counts = this.overview.counts || {};
				const keys = [
					...order.filter((k) => counts[k] != null || true),
					...Object.keys(counts).filter((k) => !order.includes(k)),
				];
				// unique
				const seen = new Set();
				return keys
					.filter((k) => {
						if (seen.has(k)) return false;
						seen.add(k);
						return true;
					})
					.map((k) => ({ status: k, count: counts[k] || 0 }));
			},
			taskTree() {
				const list = this.tasks || [];
				const byParent = {};
				list.forEach((t) => {
					const p = t.parent_task || "";
					(byParent[p] = byParent[p] || []).push(t);
				});
				const out = [];
				const walk = (t, depth) => {
					out.push({ row: t, depth });
					(byParent[t.name] || []).forEach((c) => walk(c, depth + 1));
				};
				const roots = list.filter((t) => !t.parent_task);
				if (roots.length) roots.forEach((r) => walk(r, 0));
				else list.forEach((t) => out.push({ row: t, depth: 0 }));
				return out;
			},
		},
		mounted() {
			this.boot();
			this.elapsedTimer = setInterval(() => {
				if (this.active && this.active.status === "Running") this.tick++;
			}, 1000);
		},
		unmounted() {
			if (this.elapsedTimer) clearInterval(this.elapsedTimer);
		},
		methods: {
			statusClass(status) {
				const s = (status || "").toLowerCase().replace(/\s+/g, "-");
				return `tracker-status tracker-status-${s || "other"}`;
			},
			call(method, args) {
				return new Promise((resolve, reject) => {
					frappe.call({
						method,
						args: args || {},
						callback: (r) => {
							const msg = r.message;
							if (msg && msg.success === false) {
								const err = (msg.error && msg.error.message) || msg.message || "Request failed";
								reject(new Error(err));
								return;
							}
							resolve(msg && msg.data !== undefined ? msg : msg);
						},
						error: (err) => reject(err),
					});
				});
			},
			unwrap(msg) {
				if (!msg) return null;
				if (msg.data !== undefined) return msg.data;
				return msg;
			},
			async boot() {
				try {
					await this.loadCaps();
					await this.loadActivityTypes();
					if (this.showOverview) this.tab = "overview";
					await Promise.all([this.refreshActive(), this.refreshTab()]);
				} catch (e) {
					frappe.msgprint({
						title: __("Task Management"),
						message: String(e.message || e),
						indicator: "red",
					});
				}
			},
			async loadCaps() {
				try {
					const msg = await this.call("zatgo_core.tracker.api.v1.hierarchy.my_tree");
					const data = this.unwrap(msg) || {};
					this.caps = { ...emptyCaps(), ...data };
					this.people = data.people || [];
					if (data.is_top) this.roleLabel = __("Manager");
					else if (data.is_lead_or_above) this.roleLabel = __("Lead");
					else if (data.is_worker_only) this.roleLabel = __("Worker");
					else this.roleLabel = "";
				} catch (e) {
					this.caps = emptyCaps();
					frappe.show_alert({
						message: __("Could not load role capabilities"),
						indicator: "orange",
					});
				}
			},
			async loadActivityTypes() {
				try {
					const msg = await this.call("zatgo_core.tracker.api.v1.activity.activity_types");
					const data = this.unwrap(msg) || {};
					this.activityTypes = data.items || [];
					if (!this.activityType) {
						this.activityType = data.default || (this.activityTypes[0] && this.activityTypes[0].name) || "Execution";
					}
				} catch (e) {
					this.activityTypes = [{ name: "Execution", label: "Execution" }];
					this.activityType = "Execution";
				}
			},
			async refreshActive() {
				const msg = await this.call("zatgo_core.tracker.api.v1.activity.active");
				const data = this.unwrap(msg);
				this.active = data || null;
				if (this.active && this.active.status === "Running") {
					this.active._tick_at = Date.now();
					this.active._tick_base = Number(
						this.active.elapsed_seconds || this.active.duration_seconds || 0
					);
				}
			},
			async refreshTab() {
				if (this.tab === "overview") return this.loadOverview();
				if (this.tab === "tasks") return this.loadTasks();
				if (this.tab === "tickets") return this.loadTickets();
				if (this.tab === "running") return this.loadRunning();
				if (this.tab === "review") return this.loadReview();
				if (this.tab === "activity") return this.loadActivityFeed();
			},
			async loadOverview(status) {
				const st = status || this.overview.status || "Pending Review";
				try {
					const msg = await this.call("zatgo_core.tracker.api.v1.reports.overview", { status: st });
					const data = this.unwrap(msg) || {};
					this.overview = {
						counts: data.counts || {},
						status: data.status || st,
						items: data.items || [],
						running: data.running || 0,
						timesheet_drafts: data.timesheet_drafts || 0,
					};
					this.statusFilter = data.status || st;
				} catch (e) {
					frappe.msgprint({
						title: __("Overview"),
						message: String(e.message || e),
						indicator: "red",
					});
				}
			},
			async loadTasks() {
				const args = { page: 1, page_size: 100, tree: 1 };
				if (this.scope === "mine") args.mine = 1;
				else if (this.scope === "team") args.team = 1;
				else {
					args.mine = 1;
					args.team = 1;
				}
				if (this.projectFilter) args.project = this.projectFilter;
				if (this.statusFilter) args.status = this.statusFilter;
				const msg = await this.call("zatgo_core.tracker.api.v1.tasks.list_tasks", args);
				const data = this.unwrap(msg);
				this.tasks = (data && data.items) || data || [];
			},
			async loadTickets() {
				const args = { page: 1, page_size: 100 };
				if (this.scope === "mine") args.mine = 1;
				else if (this.scope === "team") args.team = 1;
				else {
					args.mine = 1;
					args.team = 1;
				}
				if (this.projectFilter) args.project = this.projectFilter;
				const msg = await this.call("zatgo_core.tracker.api.v1.tickets.list_tickets", args);
				const data = this.unwrap(msg);
				this.tickets = (data && data.items) || data || [];
			},
			async loadRunning() {
				const msg = await this.call("zatgo_core.tracker.api.v1.activity.running_now");
				this.running = this.unwrap(msg) || [];
			},
			async loadReview() {
				const msg = await this.call("zatgo_core.tracker.api.v1.tasks.list_tasks", {
					review_queue: 1,
					page: 1,
					page_size: 100,
				});
				const data = this.unwrap(msg);
				this.review = (data && data.items) || data || [];
			},
			async loadActivityFeed() {
				try {
					const args = {
						limit: 100,
						scope: this.caps.is_worker_only ? "mine" : this.activityScope || "team",
					};
					if (this.activityAction) args.action = this.activityAction;
					const msg = await this.call("zatgo_core.tracker.api.v1.audit.feed", args);
					const data = this.unwrap(msg) || {};
					this.activityFeed = data.items || [];
				} catch (e) {
					frappe.msgprint({
						title: __("Activity"),
						message: String(e.message || e),
						indicator: "red",
					});
				}
			},
			openActivityDoc(row) {
				if (!row || !row.doctype || !row.docname) return;
				frappe.set_route("Form", row.doctype, row.docname);
			},
			formatWhen(ts) {
				if (!ts) return "";
				try {
					return frappe.datetime.prettyDate(ts);
				} catch (e) {
					return String(ts);
				}
			},
			actionBadgeClass(action) {
				const a = (action || "").toLowerCase();
				if (["approve", "create", "create_top", "assign", "assign_org", "start", "resume"].includes(a)) {
					return "tracker-status tracker-status-completed";
				}
				if (["rework", "reject", "pause", "close"].includes(a)) {
					return "tracker-status tracker-status-pending-review";
				}
				if (["stop", "submit_for_review", "submit_team"].includes(a)) {
					return "tracker-status tracker-status-working";
				}
				return "tracker-status tracker-status-other";
			},
			setTab(tab) {
				this.tab = tab;
				this.refreshTab();
			},
			selectTask(name) {
				this.selected = name;
			},
			selectTicket(name) {
				this.selectedTicket = name;
			},
			onChipClick(status) {
				this.statusFilter = status;
				this.loadOverview(status);
			},
			async actStart() {
				if (!this.selected) return;
				this.busy = true;
				try {
					await this.call("zatgo_core.tracker.api.v1.activity.start", {
						task: this.selected,
						activity_type: this.activityType || undefined,
					});
					await this.refreshActive();
					await this.refreshTab();
				} catch (e) {
					frappe.msgprint({
						title: __("Start"),
						message: String(e.message || e),
						indicator: "red",
					});
				} finally {
					this.busy = false;
				}
			},
			async actPause() {
				this.busy = true;
				try {
					await this.call("zatgo_core.tracker.api.v1.activity.pause");
					await this.refreshActive();
				} catch (e) {
					frappe.msgprint({
						title: __("Pause"),
						message: String(e.message || e),
						indicator: "red",
					});
				} finally {
					this.busy = false;
				}
			},
			async actStop() {
				this.busy = true;
				try {
					const msg = await this.call("zatgo_core.tracker.api.v1.activity.stop");
					const data = this.unwrap(msg) || {};
					await this.refreshActive();
					await this.refreshTab();
					if (data.timesheet) {
						frappe.show_alert({
							message: __("Stopped — timesheet {0}", [data.timesheet]),
							indicator: "green",
						});
					} else {
						frappe.show_alert({ message: __("Session stopped"), indicator: "blue" });
					}
				} catch (e) {
					frappe.msgprint({
						title: __("Stop"),
						message: String(e.message || e),
						indicator: "red",
					});
				} finally {
					this.busy = false;
				}
			},
			async submitReview(name) {
				try {
					await this.call("zatgo_core.tracker.api.v1.tasks.submit_for_review", { name });
					frappe.show_alert({ message: __("Submitted for review"), indicator: "green" });
					await this.refreshTab();
				} catch (e) {
					frappe.msgprint(String(e.message || e));
				}
			},
			async approve(name) {
				try {
					await this.call("zatgo_core.tracker.api.v1.tasks.approve", { name });
					frappe.show_alert({ message: __("Approved"), indicator: "green" });
					await this.refreshTab();
				} catch (e) {
					frappe.msgprint(String(e.message || e));
				}
			},
			async rework(name) {
				frappe.prompt(
					[
						{
							fieldname: "note",
							fieldtype: "Small Text",
							label: __("Rework note"),
							reqd: 1,
						},
					],
					async (v) => {
						try {
							await this.call("zatgo_core.tracker.api.v1.tasks.request_rework", {
								name,
								note: v.note,
							});
							frappe.show_alert({
								message: __("Sent for rework"),
								indicator: "orange",
							});
							await this.refreshTab();
						} catch (e) {
							frappe.msgprint(String(e.message || e));
						}
					},
					__("Request rework")
				);
			},
			async newProject() {
				frappe.prompt(
					[
						{
							fieldname: "project_name",
							fieldtype: "Data",
							label: __("Project Name"),
							reqd: 1,
						},
					],
					async (values) => {
						try {
							await this.call("zatgo_core.tracker.api.v1.projects.create_project", values);
							frappe.show_alert({
								message: __("Project created"),
								indicator: "green",
							});
							await this.refreshTab();
						} catch (e) {
							frappe.msgprint(String(e.message || e));
						}
					},
					__("New Project")
				);
			},
			async newTask() {
				const people = this.people || [];
				const d = new frappe.ui.Dialog({
					title: __("New Task"),
					fields: [
						{ fieldname: "subject", fieldtype: "Data", label: __("Subject"), reqd: 1 },
						{
							fieldname: "project",
							fieldtype: "Link",
							options: "Project",
							label: __("Project"),
						},
						{
							fieldname: "assign_to",
							fieldtype: "MultiSelectList",
							label: __("Assign To (multiple)"),
							get_data: (txt) => {
								const q = (txt || "").toLowerCase();
								return people
									.filter(
										(p) =>
											!q ||
											(p.user || "").toLowerCase().includes(q) ||
											(p.full_name || "").toLowerCase().includes(q)
									)
									.map((p) => ({
										value: p.user,
										description: p.full_name || p.user,
									}));
							},
						},
					],
					primary_action_label: __("Create"),
					primary_action: async (values) => {
						try {
							const assign_to = Array.isArray(values.assign_to)
								? values.assign_to.join(",")
								: values.assign_to;
							await this.call("zatgo_core.tracker.api.v1.tasks.create_task", {
								subject: values.subject,
								project: values.project,
								assign_to,
							});
							d.hide();
							frappe.show_alert({ message: __("Task created"), indicator: "green" });
							await this.refreshTab();
						} catch (e) {
							frappe.msgprint(String(e.message || e));
						}
					},
				});
				d.show();
			},
			async newTicket() {
				const people = this.people || [];
				const d = new frappe.ui.Dialog({
					title: __("New Ticket"),
					fields: [
						{ fieldname: "subject", fieldtype: "Data", label: __("Subject"), reqd: 1 },
						{
							fieldname: "project",
							fieldtype: "Link",
							options: "Project",
							label: __("Project"),
						},
						{
							fieldname: "description",
							fieldtype: "Small Text",
							label: __("Description"),
						},
						{
							fieldname: "assign_to",
							fieldtype: "MultiSelectList",
							label: __("Assign To (multiple)"),
							get_data: (txt) => {
								const q = (txt || "").toLowerCase();
								return people
									.filter(
										(p) =>
											!q ||
											(p.user || "").toLowerCase().includes(q) ||
											(p.full_name || "").toLowerCase().includes(q)
									)
									.map((p) => ({
										value: p.user,
										description: p.full_name || p.user,
									}));
							},
						},
					],
					primary_action_label: __("Create"),
					primary_action: async (values) => {
						try {
							const assign_to = Array.isArray(values.assign_to)
								? values.assign_to.join(",")
								: values.assign_to;
							await this.call("zatgo_core.tracker.api.v1.tickets.create_ticket", {
								subject: values.subject,
								project: values.project,
								description: values.description,
								assign_to,
							});
							d.hide();
							frappe.show_alert({
								message: __("Ticket created"),
								indicator: "green",
							});
							this.tab = "tickets";
							await this.refreshTab();
						} catch (e) {
							frappe.msgprint(String(e.message || e));
						}
					},
				});
				d.show();
			},
			async openAssign() {
				const isTicket = this.tab === "tickets";
				const name = isTicket ? this.selectedTicket : this.selected;
				const doctype = isTicket ? "Issue" : "Task";
				if (!name) {
					frappe.msgprint(__("Select a task or ticket first."));
					return;
				}
				const people = this.people || [];
				if (!people.length) {
					frappe.msgprint(__("No assignable people in your org tree."));
					return;
				}
				const d = new frappe.ui.Dialog({
					title: __("Assign") + " " + doctype + " — " + name,
					fields: [
						{
							fieldname: "users",
							fieldtype: "MultiSelectList",
							label: __("Assignees (multiple)"),
							reqd: 1,
							get_data: (txt) => {
								const q = (txt || "").toLowerCase();
								return people
									.filter(
										(p) =>
											!q ||
											(p.user || "").toLowerCase().includes(q) ||
											(p.full_name || "").toLowerCase().includes(q)
									)
									.map((p) => ({
										value: p.user,
										description: p.full_name || p.user,
									}));
							},
						},
					],
					primary_action_label: __("Assign"),
					primary_action: async (values) => {
						try {
							const users = Array.isArray(values.users)
								? values.users.join(",")
								: values.users;
							await this.call("zatgo_core.tracker.api.v1.hierarchy.assign", {
								doctype,
								name,
								users,
							});
							d.hide();
							frappe.show_alert({ message: __("Assigned"), indicator: "green" });
							await this.refreshTab();
						} catch (e) {
							frappe.msgprint(String(e.message || e));
						}
					},
				});
				d.show();
			},
			assigneeText(row) {
				const list = (row && row.assignees) || [];
				if (!list.length) return __("Unassigned");
				return list.join(", ");
			},
			isAssignedToMe(row) {
				const list = (row && row.assignees) || [];
				return list.includes(frappe.session.user);
			},
			async submitTimesheets() {
				frappe.prompt(
					[
						{
							fieldname: "from_date",
							label: __("From"),
							fieldtype: "Date",
							reqd: 1,
							default: frappe.datetime.month_start(),
						},
						{
							fieldname: "to_date",
							label: __("To"),
							fieldtype: "Date",
							reqd: 1,
							default: frappe.datetime.get_today(),
						},
					],
					async (values) => {
						try {
							const msg = await this.call(
								"zatgo_core.tracker.api.v1.timesheets.submit_team",
								values
							);
							const data = this.unwrap(msg) || {};
							frappe.msgprint(
								__("Submitted: {0}. Errors: {1}", [
									(data.submitted || []).length,
									(data.errors || []).length,
								])
							);
						} catch (e) {
							frappe.msgprint(String(e.message || e));
						}
					},
					__("Submit team timesheets")
				);
			},
			taskActions(row) {
				const status = row.status || "";
				const btns = [];
				if (status === "Working") {
					btns.push({
						key: "ready",
						label: __("Ready for Review"),
						fn: () => this.submitReview(row.name),
					});
				}
				if (status === "Pending Review" && this.caps.can_review) {
					btns.push({
						key: "approve",
						label: __("Approve"),
						fn: () => this.approve(row.name),
					});
					btns.push({
						key: "rework",
						label: __("Rework"),
						fn: () => this.rework(row.name),
					});
				}
				return btns;
			},
		},
		template: `
		<div class="tracker-workbench tracker-page">
			<div class="tracker-brand">
				<div class="tracker-brand-left">
					<h2 class="tracker-brand-title">{{ __("Task Management") }}</h2>
					<span v-if="roleLabel" class="tracker-role-chrome">{{ roleLabel }}</span>
				</div>
			</div>
			<p class="tracker-brand-sub">{{ __("Select a task assigned to you, pick Activity Type, then Start / Pause / Stop. Time posts to Timesheet.") }}</p>

			<div
				class="tracker-active"
				:class="{
					'is-idle': !active,
					'is-running': active && active.status === 'Running',
					'is-paused': active && active.status === 'Paused'
				}"
			>
				<div class="tracker-active-meta">
					<div class="tracker-active-kicker">{{ __("Active session") }}</div>
					<div class="tracker-active-label">{{ activeLabel }}</div>
					<div class="tracker-elapsed" v-if="active">{{ elapsedText }}</div>
					<div class="tracker-row-meta" v-if="active">
						<span v-if="active.project">{{ active.project }}</span>
						<span class="dot" v-if="active.project && active.task">·</span>
						<span v-if="active.task">{{ active.task }}</span>
						<span class="dot" v-if="active.activity_type">·</span>
						<span v-if="active.activity_type">{{ active.activity_type }}</span>
						<span class="dot" v-if="active.timesheet">·</span>
						<span v-if="active.timesheet">{{ __("Timesheet") }} {{ active.timesheet }}</span>
					</div>
					<div class="tracker-elapsed" v-else>{{ __("Select a task below to begin") }}</div>
				</div>
				<div class="tracker-btn-row">
					<select class="form-control" style="width:auto;min-width:9rem" v-model="activityType" :disabled="!!(active && active.status==='Running')">
						<option v-for="at in activityTypes" :key="at.name" :value="at.name">{{ at.label || at.name }}</option>
					</select>
					<button class="btn btn-primary btn-sm" :disabled="!canStart || busy" @click="actStart">{{ __("Start") }}</button>
					<button class="btn btn-default btn-sm" :disabled="!canPause || busy" @click="actPause">{{ __("Pause") }}</button>
					<button class="btn btn-danger btn-sm" :disabled="!canStop || busy" @click="actStop">{{ __("Stop") }}</button>
				</div>
			</div>

			<div class="tracker-toolbar">
				<select class="form-control" v-model="scope" @change="refreshTab" v-if="tab==='tasks' || tab==='tickets'">
					<option value="mine">{{ __("My Work") }}</option>
					<option value="team" v-if="caps.is_lead_or_above">{{ __("Team") }}</option>
					<option value="both" v-if="caps.is_lead_or_above">{{ __("Mine + Team") }}</option>
				</select>
				<input class="form-control" v-model="projectFilter" :placeholder="__('Project')" v-if="tab==='tasks' || tab==='tickets'" @change="refreshTab" />
				<input class="form-control" v-model="statusFilter" :placeholder="__('Status')" v-if="tab==='tasks'" @change="loadTasks" />
				<button class="btn btn-default btn-sm" v-if="caps.can_manage_work" @click="newProject">{{ __("New Project") }}</button>
				<button class="btn btn-default btn-sm" v-if="caps.can_manage_work" @click="newTask">{{ __("New Task") }}</button>
				<button class="btn btn-default btn-sm" v-if="caps.can_manage_work" @click="newTicket">{{ __("New Ticket") }}</button>
				<button class="btn btn-default btn-sm" v-if="caps.can_manage_work" @click="openAssign">{{ __("Assign") }}</button>
				<button class="btn btn-default btn-sm" v-if="caps.can_submit_timesheets" @click="submitTimesheets">{{ __("Submit team timesheets") }}</button>
			</div>

			<ul class="nav nav-tabs tracker-tabs">
				<li class="nav-item" v-if="showOverview">
					<a class="nav-link" :class="{active: tab==='overview'}" href="#" @click.prevent="setTab('overview')">{{ __("Overview") }}</a>
				</li>
				<li class="nav-item">
					<a class="nav-link" :class="{active: tab==='tasks'}" href="#" @click.prevent="setTab('tasks')">{{ __("Tasks") }}</a>
				</li>
				<li class="nav-item">
					<a class="nav-link" :class="{active: tab==='tickets'}" href="#" @click.prevent="setTab('tickets')">{{ __("Tickets") }}</a>
				</li>
				<li class="nav-item">
					<a class="nav-link" :class="{active: tab==='running'}" href="#" @click.prevent="setTab('running')">{{ __("Who is Running") }}</a>
				</li>
				<li class="nav-item" v-if="caps.can_review">
					<a class="nav-link" :class="{active: tab==='review'}" href="#" @click.prevent="setTab('review')">{{ __("Review") }}</a>
				</li>
				<li class="nav-item">
					<a class="nav-link" :class="{active: tab==='activity'}" href="#" @click.prevent="setTab('activity')">{{ __("Activity") }}</a>
				</li>
			</ul>

			<div v-if="tab==='overview'" class="tracker-panel">
				<div class="tracker-chip-row">
					<button
						v-for="chip in statusChips"
						:key="chip.status"
						type="button"
						class="btn btn-sm tracker-chip"
						:class="[statusClass(chip.status), {active: overview.status===chip.status}]"
						@click="onChipClick(chip.status)"
					>
						{{ chip.status }} <span class="badge">{{ chip.count }}</span>
					</button>
					<span class="tracker-chip tracker-status-running btn btn-sm disabled">
						{{ __("Running") }} <span class="badge">{{ overview.running }}</span>
					</span>
					<span class="tracker-chip tracker-status-draft-ts btn btn-sm disabled" v-if="caps.can_submit_timesheets">
						{{ __("Draft Timesheets") }} <span class="badge">{{ overview.timesheet_drafts }}</span>
					</span>
				</div>
				<div v-if="!(overview.items||[]).length" class="tracker-empty">
					<div class="tracker-empty-title">{{ __("Nothing in this status") }}</div>
					<div class="tracker-empty-hint">{{ __("Pick another status chip or assign work from Tasks.") }}</div>
				</div>
				<div
					v-for="row in overview.items"
					:key="row.name"
					class="tracker-task-row"
					:class="{selected: selected===row.name}"
					@click="selectTask(row.name)"
				>
					<div class="tracker-row-main">
						<div>
							<span class="tracker-row-title">{{ row.subject || row.name }}</span>
							<span :class="statusClass(row.status)">{{ row.status }}</span>
							<div class="tracker-row-meta">
								<span v-if="row.project">{{ row.project }}</span>
								<span class="dot" v-if="row.project">·</span>
								<span>{{ row.name }}</span>
								<span class="dot">·</span>
								<span>{{ assigneeText(row) }}</span>
							</div>
						</div>
						<div class="tracker-btn-row">
							<button
								v-for="b in taskActions(row)"
								:key="b.key"
								class="btn btn-xs"
								:class="b.key==='approve' ? 'btn-success' : (b.key==='rework' ? 'btn-warning' : 'btn-primary')"
								@click.stop="b.fn()"
							>{{ b.label }}</button>
						</div>
					</div>
				</div>
			</div>

			<div v-if="tab==='tasks'" class="tracker-panel">
				<div v-if="!taskTree.length" class="tracker-empty">
					<div class="tracker-empty-title">{{ __("No tasks yet") }}</div>
					<div class="tracker-empty-hint">{{ __("Create a project and task, or ask your lead to assign work.") }}</div>
				</div>
				<div
					v-for="item in taskTree"
					:key="item.row.name"
					class="tracker-task-row"
					:class="{selected: selected===item.row.name}"
					:style="{paddingLeft: (item.depth * 18 + 14) + 'px'}"
					@click="selectTask(item.row.name)"
				>
					<div class="tracker-row-main">
						<div>
							<span class="tracker-row-title">{{ item.row.subject || item.row.name }}</span>
							<span :class="statusClass(item.row.status)">{{ item.row.status }}</span>
							<div class="tracker-row-meta">
								<span v-if="item.row.project">{{ item.row.project }}</span>
								<span class="dot" v-if="item.row.project">·</span>
								<span>{{ item.row.name }}</span>
								<span class="dot">·</span>
								<span>{{ assigneeText(item.row) }}</span>
							</div>
						</div>
						<div class="tracker-btn-row">
							<button
								v-for="b in taskActions(item.row)"
								:key="b.key"
								class="btn btn-xs"
								:class="b.key==='approve' ? 'btn-success' : (b.key==='rework' ? 'btn-warning' : 'btn-primary')"
								@click.stop="b.fn()"
							>{{ b.label }}</button>
						</div>
					</div>
				</div>
			</div>

			<div v-if="tab==='tickets'" class="tracker-panel">
				<div v-if="!tickets.length" class="tracker-empty">
					<div class="tracker-empty-title">{{ __("No tickets") }}</div>
					<div class="tracker-empty-hint">{{ __("Tickets appear here when Issues are assigned in your scope.") }}</div>
				</div>
				<div
					v-for="row in tickets"
					:key="row.name"
					class="tracker-task-row"
					:class="{selected: selectedTicket===row.name}"
					@click="selectTicket(row.name)"
				>
					<div class="tracker-row-main">
						<div>
							<span class="tracker-row-title">{{ row.subject || row.name }}</span>
							<span :class="statusClass(row.status)">{{ row.status }}</span>
							<div class="tracker-row-meta">
								<span v-if="row.project">{{ row.project }}</span>
								<span class="dot" v-if="row.project">·</span>
								<span>{{ row.name }}</span>
							</div>
						</div>
					</div>
				</div>
			</div>

			<div v-if="tab==='running'" class="tracker-panel">
				<div v-if="!running.length" class="tracker-empty">
					<div class="tracker-empty-title">{{ __("Nobody running") }}</div>
					<div class="tracker-empty-hint">{{ __("Live timers for your team show up here.") }}</div>
				</div>
				<div v-for="row in running" :key="row.name" class="tracker-task-row" style="cursor:default">
					<div class="tracker-row-main">
						<div>
							<span class="tracker-row-title">{{ row.user }}</span>
							<span class="tracker-status tracker-status-working">{{ row.status }}</span>
							<div class="tracker-row-meta">
								<span>{{ row.task || row.project || row.name }}</span>
								<span class="dot" v-if="row.activity_type">·</span>
								<span v-if="row.activity_type">{{ row.activity_type }}</span>
							</div>
						</div>
					</div>
				</div>
			</div>

			<div v-if="tab==='review'" class="tracker-panel">
				<div v-if="!review.length" class="tracker-empty">
					<div class="tracker-empty-title">{{ __("Nothing pending review") }}</div>
					<div class="tracker-empty-hint">{{ __("Tasks submitted for review will land in this queue.") }}</div>
				</div>
				<div v-for="row in review" :key="row.name" class="tracker-task-row" @click="selectTask(row.name)">
					<div class="tracker-row-main">
						<div>
							<span class="tracker-row-title">{{ row.subject || row.name }}</span>
							<span :class="statusClass(row.status)">{{ row.status }}</span>
						</div>
						<div class="tracker-btn-row" v-if="caps.can_review">
							<button class="btn btn-xs btn-success" @click.stop="approve(row.name)">{{ __("Approve") }}</button>
							<button class="btn btn-xs btn-warning" @click.stop="rework(row.name)">{{ __("Rework") }}</button>
						</div>
					</div>
				</div>
			</div>

			<div v-if="tab==='activity'" class="tracker-panel">
				<div class="tracker-chip-row">
					<select
						class="form-control"
						style="width:auto;min-width:8rem"
						v-model="activityScope"
						v-if="!caps.is_worker_only"
						@change="loadActivityFeed"
					>
						<option value="team">{{ __("Team") }}</option>
						<option value="mine">{{ __("Mine") }}</option>
					</select>
					<select class="form-control" style="width:auto;min-width:10rem" v-model="activityAction" @change="loadActivityFeed">
						<option value="">{{ __("All actions") }}</option>
						<option value="start">{{ __("Start") }}</option>
						<option value="pause">{{ __("Pause") }}</option>
						<option value="resume">{{ __("Resume") }}</option>
						<option value="stop">{{ __("Stop") }}</option>
						<option value="create">{{ __("Create") }}</option>
						<option value="assign">{{ __("Assign") }}</option>
						<option value="submit_for_review">{{ __("Submit for review") }}</option>
						<option value="approve">{{ __("Approve") }}</option>
						<option value="rework">{{ __("Rework") }}</option>
						<option value="create_top">{{ __("Create Top") }}</option>
						<option value="assign_org">{{ __("Assign org") }}</option>
						<option value="update_org">{{ __("Update org") }}</option>
						<option value="close">{{ __("Close project") }}</option>
						<option value="submit_team">{{ __("Submit timesheets") }}</option>
					</select>
				</div>
				<div v-if="!activityFeed.length" class="tracker-empty">
					<div class="tracker-empty-title">{{ __("No activity yet") }}</div>
					<div class="tracker-empty-hint">{{ __("Starts, pauses, assigns, approvals, and org changes appear here.") }}</div>
				</div>
				<div
					v-for="row in activityFeed"
					:key="row.name"
					class="tracker-task-row tracker-activity-row"
					@click="openActivityDoc(row)"
				>
					<div class="tracker-row-main">
						<div>
							<span :class="actionBadgeClass(row.action)">{{ row.action_label || row.action }}</span>
							<span class="tracker-row-title">{{ row.subject || row.docname }}</span>
							<div class="tracker-row-meta">
								<span>{{ row.actor }}</span>
								<span class="dot">·</span>
								<span>{{ row.doctype }}</span>
								<span class="dot" v-if="row.to_stage">·</span>
								<span v-if="row.to_stage">{{ row.from_stage || "" }} → {{ row.to_stage }}</span>
								<span class="dot" v-if="row.note">·</span>
								<span v-if="row.note">{{ row.note }}</span>
							</div>
						</div>
						<div class="text-muted small">{{ formatWhen(row.creation) }}</div>
					</div>
				</div>
			</div>
		</div>
		`,
	};

	tracker.vue.mount(el, WorkbenchApp).then((app) => {
		wrapper.tracker_vue_app = app;
	});

	page.set_primary_action(__("Refresh"), () => {
		const proxy =
			wrapper.tracker_vue_app &&
			wrapper.tracker_vue_app._instance &&
			wrapper.tracker_vue_app._instance.proxy;
		if (proxy) {
			proxy.loadCaps().then(() => {
				proxy.refreshActive();
				proxy.refreshTab();
			});
		}
	});
};

frappe.pages["tracker-workbench"].on_page_show = function (wrapper) {
	const now = Date.now();
	if (wrapper._tracker_wb_show && now - wrapper._tracker_wb_show < 1000) return;
	wrapper._tracker_wb_show = now;
	const proxy =
		wrapper.tracker_vue_app &&
		wrapper.tracker_vue_app._instance &&
		wrapper.tracker_vue_app._instance.proxy;
	if (proxy) {
		if (proxy.refreshTab) proxy.refreshTab();
		if (proxy.refreshActive) proxy.refreshActive();
	}
};
