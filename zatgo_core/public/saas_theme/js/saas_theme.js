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
		this.initMobileRail();
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

// ===== Mobile navigation drawer =====
/*
 * Below the phone breakpoint (--zg-bp-sm, 576px) the workspace rail is an off-canvas drawer; layout and
 * animation live in css/src/87-responsive.css. This block is the behaviour:
 *   - a menu trigger (div[role=button], same convention as the rail controls) in every page head
 *   - scrim, close button, Esc, route change and leaving the phone width all close the drawer
 *   - aria-expanded / aria-controls on the trigger; focus moves into the drawer and is restored on close
 *   - the rest of the desk is made inert while open (body scroll lock is CSS: body.st-mobile-nav-open)
 *   - choosing a workspace closes the drawer and opens Frappe's own sidebar panel, so the choice is visible
 * initMobileRail() is idempotent (called from sidebar.init(), which can run more than once) and does nothing
 * when the rail has not been built or the page head is absent. Desktop is untouched: every handler is
 * gated on the phone media query, and the trigger/scrim/head are display:none above it.
 */
(function () {
	const BODY_OPEN = "st-mobile-nav-open";
	const RAIL_ID = "st-workspace-rail";
	const INERT_SELECTOR = ".main-section, .body-sidebar-container";

	const state = {
		open: false,
		bound: false,
		mq: null,
		return_focus: null,
		inerted: [],
		timer: null,
	};

	const menu_svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 6h16M4 12h16M4 18h16"/></svg>`;
	const close_svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg>`;

	// Breakpoints come from the stylesheet tokens so JS and CSS switch at the same width.
	function token_px(name, fallback) {
		let px = fallback;
		try {
			const v = parseInt(getComputedStyle(document.documentElement).getPropertyValue(name), 10);
			if (v > 0) px = v;
		} catch (e) {
			// computed style unavailable — keep the fallback
		}
		return px;
	}

	function is_phone() {
		if (state.mq) return state.mq.matches;
		return window.innerWidth <= token_px("--zg-bp-sm", 576);
	}

	// Frappe's own sidebar panel is an off-canvas overlay below its mobile cut-off (768px)
	function is_panel_overlay() {
		const px = token_px("--zg-bp-md", 768) - 0.02;
		return window.matchMedia ? window.matchMedia(`(max-width: ${px}px)`).matches : window.innerWidth < px;
	}

	function rail_available() {
		const $rail = saas_theme.sidebar.$rail;
		return !!($rail && $rail.length && document.body.contains($rail[0]));
	}

	function set_expanded(expanded) {
		$(".st-mobile-nav-trigger").attr("aria-expanded", expanded ? "true" : "false");
	}

	function set_inert(on) {
		if (on) {
			state.inerted = [];
			document.querySelectorAll(INERT_SELECTOR).forEach((el) => {
				if (!el.hasAttribute("inert")) {
					el.setAttribute("inert", "");
					state.inerted.push(el);
				}
			});
		} else {
			state.inerted.forEach((el) => el.removeAttribute("inert"));
			state.inerted = [];
		}
	}

	function focus_el(el) {
		if (el && typeof el.focus === "function") el.focus({ preventScroll: true });
	}

	function restore_focus(el) {
		let node = el;
		if (!node || node === document.body || !document.body.contains(node)) {
			node = $(".st-mobile-nav-trigger:visible").first()[0];
		}
		focus_el(node);
	}

	function focus_into_drawer() {
		const $rail = saas_theme.sidebar.$rail;
		const go = () => {
			const $active = $rail.find(".st-rail-item.active:visible").first();
			const $first = $rail.find(".st-rail-item:visible, .st-mobile-nav-close").first();
			focus_el(($active.length ? $active : $first)[0]);
		};
		go();
		// The drawer turns visible with the open class; if the first attempt ran before that style applied, retry once
		requestAnimationFrame(() => {
			if (state.open && !$rail[0].contains(document.activeElement)) go();
		});
	}

	function open(trigger) {
		if (state.open || !is_phone() || !rail_available()) return;
		state.open = true;
		state.return_focus = trigger || document.activeElement;
		$("body").addClass(BODY_OPEN);
		set_expanded(true);
		set_inert(true);
		focus_into_drawer();
	}

	function close(opts) {
		if (!state.open) return;
		state.open = false;
		const target = state.return_focus;
		state.return_focus = null;
		$("body").removeClass(BODY_OPEN);
		set_expanded(false);
		set_inert(false); // before focusing: inert elements cannot take focus
		if (!opts || opts.restore_focus !== false) restore_focus(target);
	}

	function toggle(trigger) {
		if (state.open) close();
		else open(trigger);
	}

	// A workspace was picked in the drawer. Picking only swaps the sidebar panel's content, which on a phone is
	// off-canvas, so show that panel (Frappe's own overlay mode) and put focus in it.
	function after_workspace_pick() {
		if (!state.open) return;
		close({ restore_focus: false });

		const sidebar = frappe.app && frappe.app.sidebar;
		if (sidebar && typeof sidebar.open === "function" && is_panel_overlay()) {
			sidebar.open();
			if (typeof sidebar.prevent_scroll === "function") sidebar.prevent_scroll();
			setTimeout(() => {
				const link = $(".body-sidebar-container.expanded .body-sidebar-top a.item-anchor[href]:visible")
					.first()[0];
				if (link) focus_el(link);
				else restore_focus(null);
			}, 120);
		} else {
			restore_focus(null);
		}
	}

	// Frappe leaves its overlay-mode panel open after a navigation; on the phone/overlay widths close it so the
	// page the user just chose is not hidden behind a scrim.
	function close_panel_after_navigation() {
		const sidebar = frappe.app && frappe.app.sidebar;
		if (sidebar && sidebar.sidebar_expanded && typeof sidebar.close === "function" && is_panel_overlay()) {
			sidebar.close();
		}
	}

	// Tab cycles inside the open drawer
	function trap_tab(e) {
		if (e.key !== "Tab" || !state.open) return;
		const nodes = saas_theme.sidebar.$rail
			.find(".st-mobile-nav-close, .st-rail-search-box input, .st-rail-search-clear, .st-rail-item")
			.filter(":visible")
			.toArray();
		if (!nodes.length) return;
		const first = nodes[0];
		const last = nodes[nodes.length - 1];
		if (e.shiftKey && document.activeElement === first) {
			e.preventDefault();
			focus_el(last);
		} else if (!e.shiftKey && document.activeElement === last) {
			e.preventDefault();
			focus_el(first);
		}
	}

	// Capture phase, so it sees Esc before the rail search box does
	function on_escape(e) {
		if (e.key !== "Escape" || !state.open) return;
		const t = e.target;
		// With text in the workspace filter, the first Esc only clears it (the rail's own handler)
		if (t && t.matches && t.matches(".st-rail-search-box input") && t.value) return;
		e.preventDefault();
		close();
	}

	function on_page_change() {
		close({ restore_focus: false });
		close_panel_after_navigation();
		schedule_triggers();
	}

	function on_viewport_change() {
		if (!is_phone()) close({ restore_focus: false });
	}

	function build_chrome($rail) {
		if (!$rail.attr("id")) $rail.attr("id", RAIL_ID);

		if (!$rail.children(".st-mobile-nav-head").length) {
			const $head = $(`
				<div class="st-mobile-nav-head">
					<span class="st-mobile-nav-title">${frappe.utils.escape_html(__("Workspaces"))}</span>
					<div class="st-mobile-nav-close" role="button" tabindex="0"
						title="${frappe.utils.escape_html(__("Close"))}"
						aria-label="${frappe.utils.escape_html(__("Close workspace menu"))}">${close_svg}</div>
				</div>
			`);
			$rail.prepend($head);
			bind_activation($head.find(".st-mobile-nav-close"), () => close());
		}

		if (!$(".st-mobile-nav-scrim").length) {
			$('<div class="st-mobile-nav-scrim" aria-hidden="true"></div>')
				.appendTo("body")
				.on("click", () => close());
		}

		if (!$rail.data("stMobileNavBound")) {
			$rail.data("stMobileNavBound", true);
			// Same activation helper as the rail's own items; runs after the switch_workspace handler bound at build time
			bind_activation($rail.find(".st-rail-item"), after_workspace_pick);
			$rail.on("keydown.st_mobile_nav", trap_tab);
		}
	}

	// Page heads are created per page, so every call checks all of them and adds the trigger where it is missing
	function ensure_triggers($rail) {
		const id = $rail.attr("id") || RAIL_ID;
		const label = frappe.utils.escape_html(__("Workspace menu"));

		$(".page-head .page-title").each(function () {
			const $title = $(this);
			if ($title.children(".st-mobile-nav-trigger").length) return;

			const $trigger = $(`
				<div class="st-mobile-nav-trigger" role="button" tabindex="0"
					title="${label}" aria-label="${label}"
					aria-controls="${id}" aria-expanded="${state.open ? "true" : "false"}">${menu_svg}</div>
			`);
			$title.prepend($trigger);
			bind_activation($trigger, function () {
				toggle(this);
			});
		});
	}

	function schedule_triggers() {
		clearTimeout(state.timer);
		state.timer = setTimeout(() => {
			if (rail_available()) ensure_triggers(saas_theme.sidebar.$rail);
		}, 120);
	}

	function bind_globals() {
		if (state.bound) return;
		state.bound = true;

		document.addEventListener("keydown", on_escape, true);
		$(document).on("page-change.st_mobile_nav", on_page_change);
		$(document).on("form-refresh.st_mobile_nav sidebar_setup.st_mobile_nav", schedule_triggers);

		if (state.mq) {
			if (state.mq.addEventListener) state.mq.addEventListener("change", on_viewport_change);
			else if (state.mq.addListener) state.mq.addListener(on_viewport_change);
		}
	}

	saas_theme.sidebar.initMobileRail = function () {
		try {
			const $rail = saas_theme.sidebar.$rail;
			if (!$rail || !$rail.length) return; // rail not built (no workspaces) or DOM absent

			if (!state.mq && window.matchMedia) {
				state.mq = window.matchMedia(`(max-width: ${token_px("--zg-bp-sm", 576)}px)`);
			}
			build_chrome($rail);
			ensure_triggers($rail);
			bind_globals();
		} catch (e) {
			console.error("saas_theme: mobile navigation drawer failed to initialise", e);
		}
	};

	saas_theme.sidebar.openMobileRail = open;
	saas_theme.sidebar.closeMobileRail = close;
})();
// ===== /Mobile navigation drawer =====

// ===== Financial statements: default print format =====
// Balance Sheet, Profit and Loss Statement and Trial Balance print with the modern "ZG ..." format
// (setup/ensure_report_print_formats.py) unless the user picks another in the Print / PDF dialog.
(function () {
	const FORMATS = {
		"Balance Sheet": "ZG Balance Sheet",
		"Profit and Loss Statement": "ZG Profit and Loss Statement",
		"Trial Balance": "ZG Trial Balance",
	};

	function patch() {
		const QR = frappe.views && frappe.views.QueryReport;
		if (!QR || QR.prototype._zg_fs_patched) return !!QR;
		QR.prototype._zg_fs_patched = true;
		const original = QR.prototype.get_custom_format;
		QR.prototype.get_custom_format = async function (print_settings) {
			const name = FORMATS[this.report_name];
			if (name && !print_settings.print_format && !(print_settings.columns || []).length) {
				const format = await this.get_report_print_format(name).catch(() => null);
				if (format) return format;
			}
			return original.call(this, print_settings);
		};
		return true;
	}

	if (!patch()) $(document).one("startup", patch);
})();
// ===== /Financial statements: default print format =====
