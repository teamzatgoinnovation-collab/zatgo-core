/**
 * Language Switcher — native-language Desk navbar switcher.
 *
 * Injects a small "globe + current language" control into the Desk navbar, backed
 * entirely by Frappe's own User.language field and translation system. No parallel
 * translation engine, no custom doctype — this file only owns the switcher UI and
 * the call to change the current user's own language preference.
 */

frappe.provide("language_switcher");

$(document).on("app_ready", function () {
	language_switcher.init();
});

language_switcher.init = function () {
	if (document.querySelector(".language-switcher")) {
		return;
	}

	const target = language_switcher._find_target();
	if (!target) {
		console.warn("language_switcher: could not locate the Desk navbar; language switcher not injected.");
		return;
	}

	language_switcher._inject(target);
	language_switcher._observe(target.container.parentElement || document.body);
};

// The real Desk navbar (header.desktop-navbar) already has an icon row — the same one
// holding notifications and the user avatar — so the widget slots in there, right before
// the avatar, instead of appending as a mismatched extra child of <header> itself (which
// has its own fixed 3-child layout for logo/search/icon-row and doesn't expect a 4th).
// Falls back to a bare <header> for any page that doesn't have this structure (e.g. the
// setup wizard's placeholder header).
language_switcher._find_target = function () {
	const avatar = document.querySelector(".desktop-navbar .desktop-avatar");
	if (avatar && avatar.parentElement) {
		return { container: avatar.parentElement, before: avatar, in_icon_row: true };
	}

	const header = document.querySelector(".main-section > header") || document.querySelector("header");
	if (header) {
		return { container: header, before: null, in_icon_row: false };
	}

	return null;
};

language_switcher._observe = function (target) {
	if (!target || language_switcher._observer) {
		return;
	}

	const observer = new MutationObserver(function () {
		if (!document.querySelector(".language-switcher")) {
			const found = language_switcher._find_target();
			if (found) {
				language_switcher._inject(found);
			}
		}
	});

	observer.observe(target, { childList: true, subtree: false });
	language_switcher._observer = observer;

	// Defensive net only: nothing in Frappe legitimately replaces the navbar again
	// after Application.startup() finishes, so this isn't an ongoing polling loop.
	setTimeout(function () {
		observer.disconnect();
		language_switcher._observer = null;
	}, 15000);
};

language_switcher._inject = function (target) {
	const current_lang = (window.frappe && frappe.boot && frappe.boot.lang) || "en";

	// Deliberately not using data-toggle="dropdown": Frappe's dropdown plugin only
	// wires up positioning for elements present at its own page-load init time, so a
	// widget injected afterward (like this one) can end up with no positioning applied
	// at all, or inherit a stale position meant for a different element. Opening/closing
	// and positioning this specific dropdown are handled entirely below instead.
	const $widget = $(`
		<div class="language-switcher${target.in_icon_row ? " language-switcher-in-navbar" : ""}">
			<button type="button"
				class="language-switcher-trigger${target.in_icon_row ? " btn-reset nav-link text-muted" : " btn btn-default btn-sm"}"
				aria-haspopup="true"
				aria-expanded="false"
				title="${frappe.utils.escape_html(__("Language"))}">
				${frappe.utils.icon("globe", "sm")}
				<span class="language-switcher-label"></span>
				${frappe.utils.icon("chevron-down", "xs")}
			</button>
		</div>
	`);

	// The dropdown panel is appended to <body>, not nested inside the widget, and
	// positioned purely from the trigger's getBoundingClientRect() every time it opens.
	// Nesting it inside the widget made it inherit whatever positioning context the
	// widget's ancestor happened to impose (an empty zero-width setup-wizard header, a
	// real navbar's icon row, an RTL dir flip) -- three different real pages have each
	// broken that in a different way. A body-level, JS-positioned element has no
	// ancestor to inherit a broken context from.
	const $menu = $('<div class="dropdown-menu language-switcher-dropdown" role="menu"></div>');
	$menu.appendTo(document.body);

	if (target.in_icon_row) {
		target.container.insertBefore($widget[0], target.before);
	} else {
		// No real navbar icon row was found (see _find_target) -- anchor the trigger
		// itself directly to the viewport instead of appending into the fallback header
		// and trusting its CSS layout. That header's own display/width behavior isn't
		// predictable across pages/Frappe versions (block vs flex, stretched vs
		// shrink-to-fit), and margin:auto only "pushes to the edge" when the parent is
		// itself a flex/grid container -- it wasn't here, so the widget rendered pinned
		// to the start edge. Same fix already applied to the dropdown panel below.
		document.body.appendChild($widget[0]);
	}

	language_switcher._current_code = current_lang;
	language_switcher._load_languages($menu);

	const $trigger = $widget.find(".language-switcher-trigger");

	$trigger.on("click", function (e) {
		e.stopPropagation();
		language_switcher._toggle($widget, $menu, $trigger[0]);
	});

	$menu.on("click", ".language-switcher-option", function (e) {
		e.preventDefault();
		const code = $(this).attr("data-lang");
		language_switcher._close($widget, $menu);
		if (code && code !== language_switcher._current_code) {
			language_switcher._set_language(code);
		}
	});

	// One shared listener for the whole document (not per-widget, since init() only
	// ever injects a single widget instance) to close on an outside click or Escape.
	$(document).on("click.language-switcher", function (e) {
		const $target = $(e.target);
		if (!$target.closest(".language-switcher").length && !$target.closest(".language-switcher-dropdown").length) {
			language_switcher._close($widget, $menu);
		}
	});
	$(document).on("keydown.language-switcher", function (e) {
		if (e.key === "Escape") {
			language_switcher._close($widget, $menu);
		}
	});
};

language_switcher._toggle = function ($widget, $menu, trigger) {
	if ($widget.hasClass("language-switcher-open")) {
		language_switcher._close($widget, $menu);
	} else {
		language_switcher._open($widget, $menu, trigger);
	}
};

language_switcher._open = function ($widget, $menu, trigger) {
	$widget.addClass("language-switcher-open");
	$widget.find(".language-switcher-trigger").attr("aria-expanded", "true");

	// Reveal at visibility:hidden first -- offsetWidth reads 0 while display:none, and
	// the clamp below needs the menu's true rendered width, not just its CSS min-width.
	$menu.css("visibility", "hidden").addClass("language-switcher-open");
	language_switcher._position_menu($menu, trigger);
	$menu.css("visibility", "");
};

// position:fixed placement computed from the trigger's actual on-screen rect, read
// fresh on every open -- see the note above _inject for why this isn't done in CSS.
// Clamped to the viewport afterward: wherever the navbar/header ends up placing the
// trigger on a given page, the panel itself must never render partially off-screen.
language_switcher._position_menu = function ($menu, trigger) {
	const rect = trigger.getBoundingClientRect();
	const is_rtl = document.documentElement.getAttribute("dir") === "rtl";
	const menu = $menu[0];
	const margin = 8;
	const menu_width = menu.offsetWidth;

	let left = is_rtl ? rect.left : rect.right - menu_width;
	left = Math.max(margin, Math.min(left, window.innerWidth - menu_width - margin));

	menu.style.top = rect.bottom + 4 + "px";
	menu.style.left = left + "px";
	menu.style.right = "auto";
};

language_switcher._close = function ($widget, $menu) {
	$widget.removeClass("language-switcher-open");
	$menu.removeClass("language-switcher-open");
	$widget.find(".language-switcher-trigger").attr("aria-expanded", "false");
};

language_switcher._load_languages = function ($menu) {
	frappe.call({
		method: "zatgo_core.api.v1.language.get_supported_languages",
		callback: function (r) {
			const languages = (r && r.message) || [];
			language_switcher._render_options($menu, languages);
		},
	});
};

language_switcher._render_options = function ($menu, languages) {
	const current_code = language_switcher._current_code;
	const $label = $(".language-switcher-label");

	$menu.empty();

	languages.forEach(function (lang) {
		const is_current = lang.language_code === current_code;
		if (is_current) {
			$label.text(lang.language_name);
		}

		const $item = $(`
			<a href="#" class="dropdown-item language-switcher-option" data-lang="${frappe.utils.escape_html(lang.language_code)}">
				<span class="language-switcher-tick">${is_current ? frappe.utils.icon("check", "xs") : ""}</span>
				<span class="language-switcher-name">${frappe.utils.escape_html(lang.language_name)}</span>
			</a>
		`);
		$menu.append($item);
	});

	if (!$label.text()) {
		$label.text(current_code);
	}
};

language_switcher._set_language = function (code) {
	const $trigger = $(".language-switcher-trigger");
	$trigger.prop("disabled", true);

	frappe.call({
		method: "zatgo_core.api.v1.language.set_language",
		args: { language: code },
		freeze: true,
		freeze_message: __("Changing language..."),
		callback: function () {
			window.location.reload();
		},
		error: function () {
			$trigger.prop("disabled", false);
			frappe.show_alert(
				{
					message: __("Unable to change language. Please try again."),
					indicator: "red",
				},
				5
			);
		},
	});
};
