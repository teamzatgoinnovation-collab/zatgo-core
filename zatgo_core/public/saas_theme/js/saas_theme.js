/*
 * SaaS Theme - Dual Sidebar + User Menu
 *
 * Architecture:
 *   [Workspace Rail 56px] [Sidebar Panel ~220px] [Main Content]
 *
 * The rail shows workspace icons from frappe.boot.desktop_icons.
 * Clicking an icon switches the sidebar panel to that workspace.
 * Rail only shows when the sidebar panel is also visible.
 */

$(document).ready(function () {
	if (!frappe.boot.setup_complete) return;

	frappe.after_ajax(function () {
		saas_theme.sidebar.init();
		saas_theme.attachments.init();
	});

	// Re-init on sidebar_setup in case frappe.after_ajax fired too early
	$(document).on("sidebar_setup", function () {
		if (!saas_theme.sidebar.rail_built) {
			saas_theme.sidebar.init();
		}
		saas_theme.sidebar.setup_user_menu();
	});
});

frappe.provide("saas_theme.sidebar");
frappe.provide("saas_theme.attachments");

// Binds click + Enter/Space so custom div/span "buttons" are keyboard-operable.
function bind_activation($el, handler) {
	$el.on("click", handler);
	$el.on("keydown", function (e) {
		if (e.key === "Enter" || e.key === " ") {
			e.preventDefault();
			handler.call(this, e);
		}
	});
}

saas_theme.sidebar = {
	rail_built: false,

	init() {
		this.restore_rail_state();
		this.build_workspace_rail();
		this.setup_user_menu();
		if (!this._listeners_bound) {
			this.listen_for_changes();
			this._listeners_bound = true;
		}
		this.toggle_rail_visibility();
	},

	/* ============================================
	   WORKSPACE RAIL
	   ============================================ */

	build_workspace_rail() {
		if (this.rail_built) return;

		const workspaces = this.get_workspaces();
		if (!workspaces.length) return;

		let icons_html = "";
		workspaces.forEach((ws) => {
			const icon_content = this.get_icon_for_workspace(ws);
			const escaped_label = frappe.utils.escape_html(ws.label);
			icons_html += `
				<div class="st-rail-item"
					role="button" tabindex="0" aria-label="${escaped_label}"
					data-workspace="${escaped_label}">
					<div class="st-rail-icon">
						${icon_content}
					</div>
					<span class="st-rail-label">${escaped_label}</span>
					<span class="st-rail-tooltip">${escaped_label}</span>
				</div>`;
		});

		const search_svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`;
		const chevrons_svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 17 5-5-5-5"/><path d="m13 17 5-5-5-5"/></svg>`;

		this.$rail = $(`
			<div class="st-workspace-rail" role="navigation" aria-label="${__("Workspaces")}">
				<div class="st-rail-search">
					<div class="st-rail-search-btn" role="button" tabindex="0" title="${__("Search workspaces")}" aria-label="${__("Search workspaces")}">
						${search_svg}
					</div>
					<div class="st-rail-search-box">
						${search_svg}
						<input type="text" placeholder="${__("Search")}" aria-label="${__("Search workspaces")}" spellcheck="false">
						<span class="st-rail-search-clear" role="button" tabindex="0" title="${__("Clear")}" aria-label="${__("Clear search")}">&times;</span>
					</div>
				</div>
				<div class="st-rail-top">
					${icons_html}
				</div>
				<div class="st-rail-empty">${__("No workspaces found")}</div>
				<div class="st-rail-bottom">
					<div class="st-rail-toggle" role="button" tabindex="0" aria-expanded="false" title="${__("Expand / collapse")}" aria-label="${__("Expand or collapse workspace rail")}">
						${chevrons_svg}
					</div>
				</div>
				<div class="st-rail-resizer" role="separator" aria-orientation="vertical" tabindex="0" aria-label="${__("Resize workspace rail")}"></div>
			</div>
		`);

		$(".body-sidebar-container").before(this.$rail);

		// Click/keyboard handler
		bind_activation(this.$rail.find(".st-rail-item"), function () {
			const ws_name = $(this).data("workspace");
			saas_theme.sidebar.switch_workspace(ws_name);
		});

		// Tooltips — move to body and position with JS
		this.$rail.find(".st-rail-tooltip").each(function () {
			$(this).appendTo("body");
		});

		this.$rail.find(".st-rail-item").on("mouseenter", function () {
			// Labels are visible in expanded mode — no tooltip needed
			if (document.body.classList.contains("st-rail-expanded")) return;

			const label = $(this).data("workspace");
			const $tip = $("body > .st-rail-tooltip").filter(function () {
				return $(this).text().trim() === label;
			});
			if (!$tip.length) return;

			const rect = this.getBoundingClientRect();
			$tip.css({
				top: rect.top + rect.height / 2 - $tip.outerHeight() / 2,
				left: rect.right + 10,
			}).addClass("visible");
		}).on("mouseleave", function () {
			$("body > .st-rail-tooltip").removeClass("visible");
		});

		this.setup_rail_search();
		this.setup_rail_toggle();
		this.setup_rail_resizer();

		this.$rail.find(".st-rail-toggle").attr("aria-expanded", $("body").hasClass("st-rail-expanded"));

		this.rail_built = true;
		this.update_rail_active();
	},

	/* ============================================
	   RAIL EXPAND / COLLAPSE + SEARCH
	   ============================================ */

	restore_rail_state() {
		let expanded = false;
		try {
			expanded = localStorage.getItem("st_rail_expanded") === "1";
		} catch (e) {
			// localStorage unavailable — stay collapsed
		}
		$("body").toggleClass("st-rail-expanded", expanded);
	},

	set_rail_expanded(expanded) {
		$("body").toggleClass("st-rail-expanded", !!expanded);
		try {
			localStorage.setItem("st_rail_expanded", expanded ? "1" : "0");
		} catch (e) {
			// non-persistent, still works for the session
		}
		$("body > .st-rail-tooltip").removeClass("visible");
		if (this.$rail) {
			this.$rail.find(".st-rail-toggle").attr("aria-expanded", !!expanded);
		}
		if (!expanded && this.$rail) {
			// Collapsing hides the search box — drop any active filter with it
			this.$rail.find(".st-rail-search-box input").val("");
			this.filter_rail("");
		}
	},

	setup_rail_toggle() {
		const me = this;
		bind_activation(this.$rail.find(".st-rail-toggle"), () => {
			me.set_rail_expanded(!$("body").hasClass("st-rail-expanded"));
		});
	},

	setup_rail_search() {
		const me = this;
		const $input = this.$rail.find(".st-rail-search-box input");

		// Collapsed mode: the search icon expands the rail and focuses the input
		bind_activation(this.$rail.find(".st-rail-search-btn"), () => {
			me.set_rail_expanded(true);
			setTimeout(() => $input.trigger("focus"), 220);
		});

		$input.on("input", () => me.filter_rail($input.val()));

		$input.on("keydown", (e) => {
			if (e.key === "Escape") {
				$input.val("");
				me.filter_rail("");
				$input.trigger("blur");
			} else if (e.key === "Enter") {
				const $first = me.$rail.find(".st-rail-item:not(.st-rail-hidden)").first();
				if ($first.length) $first.trigger("click");
			}
		});

		bind_activation(this.$rail.find(".st-rail-search-clear"), () => {
			$input.val("");
			me.filter_rail("");
			$input.trigger("focus");
		});
	},

	filter_rail(query) {
		if (!this.$rail) return;
		const q = (query || "").toLowerCase().trim();
		let visible = 0;

		this.$rail.find(".st-rail-item").each(function () {
			const ws = String($(this).data("workspace") || "").toLowerCase();
			const match = !q || ws.includes(q);
			$(this).toggleClass("st-rail-hidden", !match);
			if (match) visible++;
		});

		this.$rail.toggleClass("st-filtering", !!q);
		this.$rail.find(".st-rail-empty").toggleClass("visible", !!q && visible === 0);
	},

	setup_rail_resizer() {
		const me = this;
		const rail = this.$rail[0];
		const MIN = 60;
		const MAX = 184;
		const $resizer = this.$rail.find(".st-rail-resizer");

		// Dragging only has a meaningful keyboard equivalent as a binary
		// expand/collapse toggle, not continuous width — mirror that.
		$resizer.on("keydown", (e) => {
			if (e.key === "ArrowLeft") {
				e.preventDefault();
				me.set_rail_expanded(false);
			} else if (e.key === "ArrowRight") {
				e.preventDefault();
				me.set_rail_expanded(true);
			} else if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				me.set_rail_expanded(!$("body").hasClass("st-rail-expanded"));
			}
		});

		$resizer.on("mousedown", function (e) {
			e.preventDefault();
			const start_x = e.clientX;
			const start_w = rail.getBoundingClientRect().width;
			$("body").addClass("st-rail-resizing");

			const on_move = (ev) => {
				const w = Math.min(MAX, Math.max(MIN, start_w + (ev.clientX - start_x)));
				rail.style.width = w + "px";
				rail.style.minWidth = w + "px";
			};

			const on_up = () => {
				$(document).off("mousemove", on_move).off("mouseup", on_up);
				$("body").removeClass("st-rail-resizing");
				const w = rail.getBoundingClientRect().width;
				rail.style.width = "";
				rail.style.minWidth = "";
				// Snap to the nearest state
				me.set_rail_expanded(w > (MIN + MAX) / 2);
			};

			$(document).on("mousemove", on_move).on("mouseup", on_up);
		});
	},

	get_workspaces() {
		const icons = frappe.boot.desktop_icons || [];
		const sidebar_items = frappe.boot.workspace_sidebar_item || {};

		return icons.filter((icon) => {
			return (
				icon.hidden !== 1 &&
				icon.link_type === "Workspace Sidebar" &&
				sidebar_items[icon.label.toLowerCase()]
			);
		});
	},

	get_icon_for_workspace(ws) {
		const sidebar_data = frappe.boot.workspace_sidebar_item[ws.label.toLowerCase()];
		if (sidebar_data && sidebar_data.header_icon) {
			return frappe.utils.icon(sidebar_data.header_icon, "md", "", "", "", true);
		}

		const letter = ws.label.charAt(0).toUpperCase();
		return `<span class="st-rail-initials">${letter}</span>`;
	},

	switch_workspace(workspace_name) {
		if (!workspace_name) return;
		frappe.app.sidebar.setup(workspace_name);
		this.update_rail_active();
	},

	update_rail_active() {
		const current = (frappe.app.sidebar.sidebar_title || "").toLowerCase();

		$(".st-rail-item").removeClass("active");
		$(".st-rail-item").each(function () {
			const ws = $(this).data("workspace");
			if (ws && ws.toLowerCase() === current) {
				$(this).addClass("active");
			}
		});
	},

	toggle_rail_visibility() {
		if (!this.$rail) return;

		const sidebar_visible = $(".body-sidebar-container").is(":visible");
		const page = frappe.container?.page?.page;
		const hide = page?.hide_sidebar;

		if (sidebar_visible && !hide) {
			this.$rail.show();
			$("body").addClass("st-dual-sidebar");
		} else {
			this.$rail.hide();
			$("body").removeClass("st-dual-sidebar");
		}
	},

	ensure_sidebar_content() {
		// If sidebar panel is visible but has no items, force a re-setup
		const $top = $(".body-sidebar .body-sidebar-top");
		if (!$top.length) return;

		const has_items = $top.find(".standard-sidebar-item").length > 0;
		if (has_items) return;

		// Try to find the right workspace for the current route
		const route = frappe.get_route();
		if (!route || !route.length) return;

		const entity = route.length >= 2 ? route[1] : route[0];
		if (!entity || !frappe.app.sidebar) return;

		// Check if entity maps to a workspace
		const sidebars = frappe.app.sidebar.get_workspace_sidebars
			? frappe.app.sidebar.get_workspace_sidebars(entity)
			: [];

		if (sidebars.length) {
			frappe.app.sidebar.setup(sidebars[0]);
		} else if (frappe.app.sidebar.sidebar_title) {
			// Re-setup current sidebar to force re-render
			frappe.app.sidebar.setup(frappe.app.sidebar.sidebar_title);
		}
	},

	listen_for_changes() {
		const me = this;

		$(document).on("sidebar_setup", () => {
			setTimeout(() => {
				me.update_rail_active();
				me.toggle_rail_visibility();
			}, 50);
		});

		$(document).on("page-change", () => {
			setTimeout(() => {
				me.update_rail_active();
				me.toggle_rail_visibility();
				me.ensure_sidebar_content();
			}, 100);
		});

		$(document).on("form-refresh", () => {
			setTimeout(() => {
				me.toggle_rail_visibility();
				me.ensure_sidebar_content();
			}, 200);
		});
	},

	/* ============================================
	   USER MENU
	   ============================================ */

	setup_user_menu() {
		const $sidebar = $(".body-sidebar");
		const $user_btn = $sidebar.find(
			".dropdown-navbar-user .sidebar-user-button"
		);

		if (!$user_btn.length) return;

		$user_btn.removeAttr("onclick");
		$user_btn.off("click keydown.saas_user_menu");
		$user_btn.attr({
			role: "button",
			tabindex: $user_btn.attr("tabindex") || "0",
			"aria-haspopup": "true",
			"aria-expanded": "false",
		});

		$user_btn.on("click", (e) => {
			e.preventDefault();
			e.stopPropagation();
			this.toggle_user_menu();
		});

		$user_btn.on("keydown.saas_user_menu", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				e.stopPropagation();
				this.toggle_user_menu();
			}
		});

		if (!this._user_menu_doc_bound) {
			$(document).on("click.saas_user_menu", (e) => {
				if (
					!$(e.target).closest(".saas-user-menu").length &&
					!$(e.target).closest(".dropdown-navbar-user").length
				) {
					this.close_user_menu();
				}
			});
			this._user_menu_doc_bound = true;
		}
	},

	toggle_user_menu() {
		if ($(".saas-user-menu").length) {
			this.close_user_menu();
			return;
		}
		this.show_user_menu();
	},

	close_user_menu(return_focus) {
		$(".saas-user-menu").remove();
		$(".dropdown-navbar-user .sidebar-user-button").attr("aria-expanded", "false");
		if (return_focus) {
			$(".dropdown-navbar-user .sidebar-user-button").trigger("focus");
		}
	},

	show_user_menu() {
		const user_fullname = frappe.utils.escape_html(frappe.session.user_fullname);
		const user_email = frappe.utils.escape_html(frappe.session.user_email);
		const user_avatar = frappe.avatar(frappe.session.user, "avatar-large");
		const version = frappe.boot.versions?.frappe
			? `v${frappe.boot.versions.frappe}`
			: "";

		const menu_items = [
			{ label: __("Integrations"), icon: "folder", href: "/app/installed-applications" },
			{ label: __("History"), icon: "clock", href: "/app/activity-log" },
			{ highlight: true, label: __("Update App"), action: "update" },
			{ divider: true },
			{ label: __("Logout"), icon: "logout", action: "logout" },
		];

		let items_html = "";
		menu_items.forEach((item) => {
			if (item.divider) {
				items_html += '<div class="saas-user-menu-divider" role="separator"></div>';
			} else if (item.highlight) {
				items_html += `
					<a class="saas-user-menu-item highlight" role="menuitem" tabindex="-1"
						${item.href ? `href="${item.href}"` : ""}
						data-action="${item.action || ""}">
						<span class="saas-menu-dot"></span>
						<span>${item.label}</span>
					</a>`;
			} else {
				items_html += `
					<a class="saas-user-menu-item" role="menuitem" tabindex="-1"
						${item.href ? `href="${item.href}"` : ""}
						data-action="${item.action || ""}">
						${item.icon ? `<span class="saas-menu-icon">${frappe.utils.icon(item.icon, "sm")}</span>` : ""}
						<span>${item.label}</span>
					</a>`;
			}
		});

		const $menu = $(`
			<div class="saas-user-menu" role="menu" aria-label="${__("User menu")}">
				<div class="saas-user-menu-header">
					<div class="saas-user-menu-avatar">${user_avatar}</div>
					<div class="saas-user-menu-info">
						<div class="saas-user-menu-name">${user_fullname}</div>
						<div class="saas-user-menu-email">${user_email}</div>
					</div>
				</div>
				<div class="saas-user-menu-divider"></div>
				<div class="saas-user-menu-items">${items_html}</div>
				${version ? `<div class="saas-user-menu-footer">${version} &middot; Terms &amp; Conditions</div>` : ""}
			</div>
		`);

		$(".body-sidebar").append($menu);
		$(".dropdown-navbar-user .sidebar-user-button").attr("aria-expanded", "true");

		const $items = $menu.find(".saas-user-menu-item");
		$items.first().attr("tabindex", "0");
		$items.first().trigger("focus");

		$items.on("click", function (e) {
			const action = $(this).data("action");
			if (action) {
				e.preventDefault();
				saas_theme.sidebar.handle_menu_action(action);
				saas_theme.sidebar.close_user_menu();
			}
		});

		this.setup_user_menu_keynav($menu, $items);
	},

	setup_user_menu_keynav($menu, $items) {
		const focus_item = (index) => {
			$items.attr("tabindex", "-1");
			const $target = $items.eq((index + $items.length) % $items.length);
			$target.attr("tabindex", "0").trigger("focus");
		};

		$menu.on("keydown", (e) => {
			const current = $items.index(document.activeElement);

			if (e.key === "ArrowDown") {
				e.preventDefault();
				focus_item(current + 1);
			} else if (e.key === "ArrowUp") {
				e.preventDefault();
				focus_item(current - 1);
			} else if (e.key === "Home") {
				e.preventDefault();
				focus_item(0);
			} else if (e.key === "End") {
				e.preventDefault();
				focus_item($items.length - 1);
			} else if (e.key === "Escape") {
				e.preventDefault();
				this.close_user_menu(true);
			}
		});

		// Close if focus leaves the menu entirely (e.g. Tab past the last item).
		$menu.on("focusout", (e) => {
			setTimeout(() => {
				if (!$menu.get(0).contains(document.activeElement)) {
					this.close_user_menu();
				}
			}, 0);
		});
	},

	handle_menu_action(action) {
		switch (action) {
			case "logout":
				frappe.app.logout();
				break;
			case "update":
				frappe.msgprint(__("App is up to date."));
				break;
		}
	},
};

/* ============================================
   ATTACHMENT ENHANCEMENTS
   ============================================ */

saas_theme.attachments = {
	ext_map: {
		pdf:  { label: "PDF",  cls: "st-pdf" },
		doc:  { label: "DOC",  cls: "st-doc" },
		docx: { label: "DOC",  cls: "st-doc" },
		xls:  { label: "XLS",  cls: "st-xls" },
		xlsx: { label: "XLS",  cls: "st-xls" },
		csv:  { label: "CSV",  cls: "st-xls" },
		png:  { label: "PNG",  cls: "st-img" },
		jpg:  { label: "JPG",  cls: "st-img" },
		jpeg: { label: "JPG",  cls: "st-img" },
		gif:  { label: "GIF",  cls: "st-img" },
		svg:  { label: "SVG",  cls: "st-img" },
		webp: { label: "IMG",  cls: "st-img" },
		zip:  { label: "ZIP",  cls: "st-zip" },
		gz:   { label: "GZ",   cls: "st-zip" },
		rar:  { label: "RAR",  cls: "st-zip" },
		"7z": { label: "7Z",   cls: "st-zip" },
		js:   { label: "JS",   cls: "st-code" },
		py:   { label: "PY",   cls: "st-code" },
		json: { label: "JSON", cls: "st-code" },
		html: { label: "HTML", cls: "st-code" },
		css:  { label: "CSS",  cls: "st-code" },
		txt:  { label: "TXT",  cls: "st-file" },
		ppt:  { label: "PPT",  cls: "st-doc" },
		pptx: { label: "PPT",  cls: "st-doc" },
	},

	init() {
		this.listen();
	},

	get_file_info(filename) {
		if (!filename) return { label: "FILE", cls: "st-file" };
		const ext = filename.split(".").pop().toLowerCase();
		return this.ext_map[ext] || { label: ext.substring(0, 4).toUpperCase(), cls: "st-file" };
	},

	enhance_all() {
		const me = this;
		$(".form-sidebar .attachment-row:not(.st-enhanced)").each(function () {
			me.enhance_row($(this));
		});
	},

	enhance_row($row) {
		const $pill = $row.find(".data-pill");
		if (!$pill.length) return;

		const $label_link = $pill.find(".attachment-file-label");
		if (!$label_link.length) return;

		$row.addClass("st-enhanced");

		const file_url = $label_link.attr("href") || "";
		const filename = $label_link.attr("title") || $label_link.text().trim();
		const file_info = this.get_file_info(filename);

		const $lock_icon = $pill.find(".attachment-icon");
		const lock_use = $lock_icon.find("use");
		const lock_href_attr = lock_use.length ? lock_use.attr("href") : "";
		const is_private = lock_href_attr === "#es-line-lock";
		const lock_href = $lock_icon.attr("href") || "";

		const $remove = $pill.find(".remove-btn").clone(true);
		const escaped_name = frappe.utils.escape_html(filename);
		const escaped_url = frappe.utils.escape_html(file_url);

		// Replace entire pill content with clean structure
		$pill.empty().addClass("st-attach-card").append(`
			<div class="st-file-icon ${file_info.cls}">${file_info.label}</div>
			<div class="st-attach-details">
				<a class="st-attach-name" href="${escaped_url}" target="_blank" title="${escaped_name}">${escaped_name}</a>
				<span class="st-attach-lock">
					<a href="${frappe.utils.escape_html(lock_href)}" style="color:inherit;text-decoration:none">${is_private ? "Private" : "Public"}</a>
				</span>
			</div>
		`);
		if ($remove.length) {
			$pill.append($remove);
		}
	},

	listen() {
		const me = this;
		const debounced = frappe.utils.debounce(() => me.enhance_all(), 150);

		// Catch form loads
		$(document).on("form-refresh", () => setTimeout(debounced, 300));
		$(document).on("page-change", () => setTimeout(debounced, 500));

		// Observe entire body for attachment rows appearing
		const observer = new MutationObserver(debounced);
		observer.observe(document.body, { childList: true, subtree: true });
	},
};
