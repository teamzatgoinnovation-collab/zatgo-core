frappe.pages["tracker-hours"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Task Management Hours"),
		single_column: true,
	});

	const today = frappe.datetime.get_today();
	const monthStart = frappe.datetime.month_start();

	const REPORTS = {
		project: {
			label: __("Project"),
			method: "zatgo_core.tracker.api.v1.reports.hours_by_project",
			cols: [
				{ key: "project_name", label: __("Project") },
				{ key: "project", label: __("ID"), muted: true },
				{ key: "hours", label: __("Hours") },
				{ key: "people", label: __("People"), muted: true },
				{ key: "timesheets", label: __("Timesheets"), muted: true },
				{ key: "entries", label: __("Entries"), muted: true },
			],
		},
		user: {
			label: __("User"),
			method: "zatgo_core.tracker.api.v1.reports.hours_by_user",
			cols: [
				{ key: "employee_name", label: __("Employee") },
				{ key: "user", label: __("User"), muted: true },
				{ key: "hours", label: __("Hours") },
				{ key: "projects", label: __("Projects"), muted: true },
				{ key: "tasks", label: __("Tasks"), muted: true },
				{ key: "timesheets", label: __("Timesheets"), muted: true },
				{ key: "entries", label: __("Entries"), muted: true },
			],
		},
		activity: {
			label: __("Activity Type"),
			method: "zatgo_core.tracker.api.v1.reports.hours_by_activity_type",
			cols: [
				{ key: "activity_type", label: __("Activity Type") },
				{ key: "hours", label: __("Hours") },
				{ key: "people", label: __("People"), muted: true },
				{ key: "entries", label: __("Entries"), muted: true },
			],
		},
		task: {
			label: __("Task"),
			method: "zatgo_core.tracker.api.v1.reports.hours_by_task",
			cols: [
				{ key: "task_subject", label: __("Task") },
				{ key: "project", label: __("Project"), muted: true },
				{ key: "employee_name", label: __("User") },
				{ key: "activity_type", label: __("Activity Type") },
				{ key: "hours", label: __("Hours") },
				{ key: "timesheets", label: __("Timesheets"), muted: true },
				{ key: "entries", label: __("Entries"), muted: true },
			],
		},
		timesheet: {
			label: __("Timesheet"),
			method: "zatgo_core.tracker.api.v1.reports.hours_by_timesheet",
			cols: [
				{ key: "timesheet", label: __("Timesheet") },
				{ key: "employee_name", label: __("User") },
				{ key: "start_date", label: __("From"), muted: true },
				{ key: "end_date", label: __("To"), muted: true },
				{ key: "docstatus_label", label: __("Status") },
				{ key: "project", label: __("Project"), muted: true },
				{ key: "hours", label: __("Hours") },
				{ key: "tasks", label: __("Tasks"), muted: true },
				{ key: "entries", label: __("Entries"), muted: true },
			],
		},
		detail: {
			label: __("Detail"),
			method: "zatgo_core.tracker.api.v1.reports.hours_detail",
			page_size: 200,
			cols: [
				{ key: "from_time", label: __("From") },
				{ key: "employee_name", label: __("User") },
				{ key: "timesheet", label: __("Timesheet"), muted: true },
				{ key: "project", label: __("Project") },
				{ key: "task_subject", label: __("Task") },
				{ key: "activity_type", label: __("Activity Type") },
				{ key: "hours", label: __("Hours") },
				{ key: "docstatus_label", label: __("Status"), muted: true },
			],
		},
	};

	const tabHtml = Object.keys(REPORTS)
		.map(
			(key, i) =>
				`<a class="nav-link tracker-report-tab ${i === 0 ? "active" : ""}" href="#" data-report="${key}">${frappe.utils.escape_html(
					REPORTS[key].label
				)}</a>`
		)
		.join("");

	page.main.html(`
		<div class="tracker-hours tracker-page">
			<div class="tracker-brand">
				<div class="tracker-brand-left">
					<h2 class="tracker-brand-title">${__("Hours")}</h2>
				</div>
			</div>
			<p class="tracker-brand-sub">
				${__("Reports by project, user, activity type, task, timesheet, and line detail.")}
			</p>

			<div class="tracker-toolbar">
				<div class="tracker-field">
					<label>${__("From")}</label>
					<input type="date" class="form-control tracker-from" value="${monthStart}" />
				</div>
				<div class="tracker-field">
					<label>${__("To")}</label>
					<input type="date" class="form-control tracker-to" value="${today}" />
				</div>
				<div class="tracker-field tracker-field-action">
					<button class="btn btn-primary btn-sm tracker-btn-load">${__("Load")}</button>
				</div>
			</div>

			<ul class="nav nav-tabs tracker-tabs tracker-report-tabs">${tabHtml}</ul>

			<div class="tracker-hours-card tracker-hours-card-wide tracker-report-panel">
				<div class="tracker-hours-card-head">
					<h5 class="tracker-report-title">${frappe.utils.escape_html(REPORTS.project.label)}</h5>
					<span class="text-muted small tracker-report-count"></span>
				</div>
				<div class="tracker-hours-card-body tracker-report-body"></div>
			</div>
		</div>
	`);

	const $root = $(page.main);
	let currentReport = "project";

	function emptyHtml(title, hint) {
		return `<div class="tracker-empty">
			<div class="tracker-empty-title">${frappe.utils.escape_html(title)}</div>
			<div class="tracker-empty-hint">${frappe.utils.escape_html(hint)}</div>
		</div>`;
	}

	function table(rows, cols) {
		if (!rows.length) {
			return emptyHtml(
				__("No hours in range"),
				__("Stop sessions on the Workbench or widen the date range.")
			);
		}
		const head = cols.map((c) => `<th>${frappe.utils.escape_html(c.label)}</th>`).join("");
		const body = rows
			.map((r) => {
				const cells = cols
					.map((c) => {
						let v = r[c.key];
						if (c.key === "project_name" && !v) v = r.project;
						if (c.key === "task_subject" && !v) v = r.task;
						let cls = "";
						if (c.key === "hours") {
							v = Number(v || 0).toFixed(2);
							cls = "tracker-hours-num";
						}
						if (c.muted) cls = (cls + " tracker-hours-muted").trim();
						if (v == null || v === "") v = "—";
						return `<td class="${cls}">${frappe.utils.escape_html(String(v))}</td>`;
					})
					.join("");
				return `<tr>${cells}</tr>`;
			})
			.join("");
		return `<table class="table table-sm tracker-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
	}

	function errorHtml(message) {
		return `<p class="tracker-error">${frappe.utils.escape_html(
			message || __("Could not load hours.")
		)}</p>`;
	}

	function unwrapRows(res) {
		const m = res.message || {};
		if (m.success === false) {
			const err = (m.error && m.error.message) || __("Request failed.");
			return { rows: [], error: err, total: 0 };
		}
		return { rows: m.data || [], error: null, total: (m.meta && m.meta.total) || (m.data || []).length };
	}

	function sumHours(rows) {
		return rows.reduce((n, r) => n + Number(r.hours || 0), 0);
	}

	function load() {
		const from_date = $root.find(".tracker-from").val();
		const to_date = $root.find(".tracker-to").val();
		if (!from_date || !to_date) {
			frappe.msgprint({
				title: __("Date range"),
				message: __("From and To dates are required."),
				indicator: "orange",
			});
			return;
		}
		if (from_date > to_date) {
			frappe.msgprint({
				title: __("Date range"),
				message: __("From date must be on or before To date."),
				indicator: "orange",
			});
			return;
		}

		const conf = REPORTS[currentReport];
		$root.find(".tracker-report-title").text(conf.label);
		$root.find(".tracker-report-count").text("");
		$root.find(".tracker-report-body").html(
			`<div class="tracker-empty"><div class="tracker-empty-hint">${__("Loading…")}</div></div>`
		);

		frappe
			.call(conf.method, {
				from_date,
				to_date,
				page_size: conf.page_size || 200,
			})
			.then((res) => {
				const result = unwrapRows(res);
				if (result.error) {
					$root.find(".tracker-report-body").html(errorHtml(result.error));
					return;
				}
				$root.find(".tracker-report-count").text(
					__("{0} h · {1} rows", [sumHours(result.rows).toFixed(1), String(result.total)])
				);
				$root.find(".tracker-report-body").html(table(result.rows, conf.cols));
			})
			.catch((e) => {
				const message = e.message || e;
				$root.find(".tracker-report-body").html(errorHtml(message));
				frappe.msgprint({ title: __("Error"), message, indicator: "red" });
			});
	}

	$root.on("click", ".tracker-report-tab", function (e) {
		e.preventDefault();
		const key = $(this).data("report");
		if (!REPORTS[key]) return;
		currentReport = key;
		$root.find(".tracker-report-tab").removeClass("active");
		$(this).addClass("active");
		load();
	});

	$root.find(".tracker-btn-load").on("click", load);
	page.set_primary_action(__("Refresh"), load);
	load();
};
