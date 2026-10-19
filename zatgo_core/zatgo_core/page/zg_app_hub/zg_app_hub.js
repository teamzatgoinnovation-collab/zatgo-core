frappe.pages["zg-app-hub"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("App Settings Hub"),
		single_column: true,
	});
	const $root = $('<div class="zg-app-hub"></div>').appendTo(page.main);
	const GROUP_LABELS = {
		core: __("Core settings"),
		ui: __("Desk appearance"),
		bundled: __("Apps"),
		industries: __("Industries"),
	};
	const call = (method, args) =>
		frappe.call({ method: `zatgo_core.api.v1.app_hub.${method}`, args: args || {} }).then((r) => {
			const m = r.message;
			if (m && m.success === false) {
				throw new Error((m.error && m.error.message) || m.message || __("Request failed"));
			}
			return m && m.data !== undefined ? m.data : m;
		});

	function card(app) {
		const $c = $('<div class="zg-hub-card"></div>').css({
			border: "1px solid var(--border-color)",
			borderRadius: "var(--border-radius-md)",
			padding: "var(--padding-md)",
			marginBottom: "var(--margin-md)",
			background: "var(--card-bg)",
		});
		const $head = $('<div class="d-flex justify-content-between align-items-center"></div>').appendTo($c);
		$("<b></b>").text(app.label).appendTo($head);
		if (app.has_switch) {
			const $lbl = $('<label class="checkbox" style="margin:0"></label>').appendTo($head);
			const $cb = $('<input type="checkbox">').prop("checked", app.enabled).appendTo($lbl);
			$("<span class='label-area'></span>").text(" " + __("On")).appendTo($lbl);
			$cb.on("change", () => {
				const want = $cb.prop("checked") ? 1 : 0;
				call("set_switch", { key: app.key, enabled: want })
					.then(() => {
						frappe.show_alert({
							message: want ? __("{0} switched on", [app.label]) : __("{0} switched off", [app.label]),
							indicator: want ? "green" : "orange",
						});
						render();
					})
					.catch((e) => {
						$cb.prop("checked", !want);
						frappe.msgprint(String(e.message || e));
					});
			});
		}
		if (app.description) $('<p class="text-muted small"></p>').text(app.description).appendTo($c);
		if (app.has_switch && !app.enabled) {
			$('<p class="text-muted small"></p>').text(__("Off on this site. Data is kept.")).appendTo($c);
		}
		const $links = $('<div class="zg-hub-links"></div>').appendTo($c);
		app.settings.forEach((s) => {
			$('<a class="btn btn-default btn-xs" style="margin:0 6px 6px 0"></a>')
				.attr("href", s.route)
				.text(s.label)
				.appendTo($links);
		});
		return $c;
	}

	function render() {
		call("get_hub")
			.then((hub) => {
				$root.empty();
				hub.groups.forEach((g) => {
					const apps = hub.apps.filter((a) => a.group === g);
					if (!apps.length) return;
					$("<h5></h5>").text(GROUP_LABELS[g] || g).css("margin", "var(--margin-lg) 0 var(--margin-sm)").appendTo($root);
					const $row = $('<div class="row"></div>').appendTo($root);
					apps.forEach((a) => $('<div class="col-md-4 col-sm-6"></div>').append(card(a)).appendTo($row));
				});
			})
			.catch((e) => $root.text(String(e.message || e)));
	}
	render();
};
