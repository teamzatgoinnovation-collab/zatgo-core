/**
 * Chat AI -- Markdown renderer: marked -> DOMPurify (strict allowlist).
 *
 * createMarkdown(env) returns {render, sanitize, ready}. env:
 *   libs    {marked, DOMPurify, hljs, katex}  vendored libraries (katex is lazy:
 *           read at render time, so it may appear after creation)
 *   window  the window DOMPurify works on
 *
 * Every string this module returns as HTML has passed through DOMPurify with
 * the allowlist below. Without the libraries (failed to load) render() falls
 * back to escaped plain text, never to unsanitised HTML.
 *
 * Output contract the Vue component relies on (event delegation):
 *   [data-act="copy"|"download"] inside .cai-md-codeblock   code block buttons
 *   a[data-cite="n"]                                         citation markers
 */
(function (root, factory) {
	if (typeof module === "object" && module.exports) {
		module.exports = { createMarkdown: factory };
	} else {
		root.chat_ai = root.chat_ai || {};
		root.chat_ai.createMarkdown = factory;
	}
})(typeof self !== "undefined" ? self : this, function createMarkdown(env) {
	"use strict";

	const libs = env.libs || {};
	const win = env.window || (typeof window !== "undefined" ? window : null);

	const MAX_RENDER_CHARS = 150000; // beyond this, plain text (keeps the UI responsive)
	const MAX_HIGHLIGHT_CHARS = 20000;

	const DEFAULT_LABELS = { copy: "Copy", download: "Download", code: "code", source: "Source" };

	const HTML_TAGS = [
		"p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "b", "i", "u", "s", "del", "ins",
		"sub", "sup", "mark", "kbd", "small", "blockquote", "ul", "ol", "li", "pre", "code", "span", "div", "a",
		"table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col", "img", "button",
		"details", "summary", "dl", "dt", "dd",
	];
	const MATH_TAGS = [
		"math", "mrow", "mi", "mn", "mo", "ms", "mtext", "mspace", "msup", "msub", "msubsup", "mfrac", "msqrt",
		"mroot", "mover", "munder", "munderover", "mtable", "mtr", "mtd", "mstyle", "mpadded", "mphantom",
		"menclose", "mmultiscripts", "merror",
	];
	const MATH_ATTRS = [
		"display", "displaystyle", "mathvariant", "scriptlevel", "mathsize", "stretchy", "fence", "separator",
		"lspace", "rspace", "form", "accent", "accentunder", "columnalign", "rowalign", "columnspan",
		"linethickness", "notation", "depth", "minsize", "maxsize", "symmetric", "largeop", "movablelimits",
	];

	// Only classes this renderer emits (or highlight.js / marked produce) survive: model output can
	// never borrow the UI's own classes (buttons, confirm bars, launcher...).
	const CLASS_OK = /^(?:hljs(?:-[a-z_]+)*|language-[A-Za-z0-9_+#.-]{1,30}|cai-md-[a-z-]+)$/;
	const RASTER_DATA = /^data:image\/(?:png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]*$/i;
	const IMAGE_PATH = /^\/(?:files|private\/files|assets)\/[^\s]*$/;

	const PURIFY_CONFIG = {
		ALLOWED_TAGS: HTML_TAGS.concat(MATH_TAGS),
		ALLOWED_ATTR: [
			"href", "src", "alt", "title", "class", "dir", "lang", "colspan", "rowspan", "align", "start", "type",
			"data-act", "data-cite", "data-lang", "aria-label", "role", "tabindex", "width", "height",
		].concat(MATH_ATTRS),
		ALLOW_DATA_ATTR: false,
		ALLOW_ARIA_ATTR: false,
		ALLOW_UNKNOWN_PROTOCOLS: false,
		FORBID_ATTR: ["style", "srcset", "srcdoc", "formaction", "action", "id", "name", "xlink:href"],
		FORBID_TAGS: [
			"style", "script", "iframe", "object", "embed", "form", "input", "textarea", "select", "option", "svg",
			"link", "meta", "base", "template", "frame", "frameset", "audio", "video", "source", "track", "canvas",
			"dialog", "noscript", "applet",
		],
		SANITIZE_DOM: true,
		SANITIZE_NAMED_PROPS: true,
		KEEP_CONTENT: true,
		WHOLE_DOCUMENT: false,
		RETURN_DOM: false,
		RETURN_DOM_FRAGMENT: false,
		RETURN_TRUSTED_TYPE: false,
	};

	/* ------------------------------------------------------------------- utils */

	function esc(s) {
		return String(s == null ? "" : s)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function plain(text) {
		return '<p dir="auto">' + esc(text).replace(/\r?\n/g, "<br>") + "</p>";
	}

	function normLang(lang) {
		return String(lang || "")
			.trim()
			.split(/\s+/)[0]
			.toLowerCase()
			.replace(/[^a-z0-9_+#.-]/g, "")
			.slice(0, 30);
	}

	function sameOrigin(url) {
		try {
			const base = (win && win.location && win.location.href) || "http://localhost/";
			const u = new URL(url, base);
			return /^https?:$/.test(u.protocol) && u.origin === new URL(base).origin ? u : null;
		} catch (e) {
			return null;
		}
	}

	/** Image sources that may load: inline raster data, or the site's own file / asset paths. */
	function imageSrcAllowed(src) {
		const raw = String(src || "").trim();
		if (RASTER_DATA.test(raw)) return true;
		const u = sameOrigin(raw);
		return !!u && IMAGE_PATH.test(u.pathname) && !u.pathname.includes("..");
	}

	function linkAllowed(href) {
		const raw = String(href || "").replace(/[\u0000- ]/g, "");
		if (/^#cai-src-\d{1,3}$/i.test(raw)) return "cite";
		if (/^(?:https?:|mailto:|tel:)/i.test(raw)) return "external";
		if (/^\/app\//i.test(raw) && !raw.startsWith("//")) return "internal";
		return "";
	}

	/* ------------------------------------------------------------- highlighting */

	const hlCache = new Map();

	function highlight(code, lang) {
		const hljs = libs.hljs;
		if (!hljs || !lang || code.length > MAX_HIGHLIGHT_CHARS || !hljs.getLanguage(lang)) return esc(code);
		const key = lang + "\u0000" + code;
		if (hlCache.has(key)) return hlCache.get(key);
		let html;
		try {
			html = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
		} catch (e) {
			html = esc(code);
		}
		if (hlCache.size > 300) hlCache.delete(hlCache.keys().next().value);
		hlCache.set(key, html);
		return html;
	}

	/* -------------------------------------------------------------------- math */

	let ctx = { sources: [], labels: DEFAULT_LABELS, needsMath: false };

	function renderMath(tex, display) {
		const katex = libs.katex;
		if (!katex || typeof katex.renderToString !== "function") {
			ctx.needsMath = true;
			return '<code class="cai-md-math-pending">' + esc(tex) + "</code>";
		}
		try {
			// MathML only: no inline styles / fonts, so the DOMPurify allowlist stays strict.
			const out = katex.renderToString(tex, {
				output: "mathml",
				displayMode: !!display,
				throwOnError: false,
				strict: "ignore",
				trust: false,
				maxSize: 20,
				maxExpand: 500,
			});
			return out.replace(/<annotation[\s\S]*?<\/annotation>/g, "").replace(/<\/?semantics>/g, "");
		} catch (e) {
			return "<code>" + esc(tex) + "</code>";
		}
	}

	/* ------------------------------------------------------------------ marked */

	let md = null;
	let purify = null;

	function build() {
		if (!libs.marked || !libs.DOMPurify || !win) return;
		const Marked = libs.marked.Marked;
		const Renderer = libs.marked.Renderer;
		if (typeof Marked !== "function") return;

		purify = libs.DOMPurify(win);
		if (!purify || !purify.isSupported) {
			purify = null;
			return;
		}
		installHooks(purify);

		md = new Marked({ gfm: true, breaks: true, async: false });
		md.use({
			extensions: [
				{
					name: "cite",
					level: "inline",
					start(src) {
						const i = src.indexOf("[");
						return i < 0 ? undefined : i;
					},
					tokenizer(src) {
						const m = /^\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\](?!\(|:)/.exec(src);
						if (!m || !ctx.sources || !ctx.sources.length) return undefined;
						const nums = m[1].split(",").map((x) => parseInt(x, 10));
						const valid = nums.filter((n) => ctx.sources[n - 1] && ctx.sources[n - 1].type !== "other");
						if (!valid.length || valid.length !== nums.length) return undefined;
						return { type: "cite", raw: m[0], nums };
					},
					renderer(token) {
						return token.nums
							.map((n) => {
								const s = ctx.sources[n - 1] || {};
								const title = [s.title, s.domain].filter(Boolean).join(" - ");
								return (
									'<sup class="cai-md-cite"><a href="#cai-src-' + n + '" data-cite="' + n + '" title="' +
									esc(title) + '" aria-label="' + esc(ctx.labels.source + " " + n) + '">' + n + "</a></sup>"
								);
							})
							.join("");
					},
				},
				{
					name: "mathBlock",
					level: "block",
					start(src) {
						const m = /(?:^|\n)(?:\$\$|\\\[)/.exec(src);
						return m ? m.index + (src[m.index] === "\n" ? 1 : 0) : undefined;
					},
					tokenizer(src) {
						const m =
							/^\$\$[ \t]*\n?([\s\S]+?)\n?[ \t]*\$\$[ \t]*(?:\n|$)/.exec(src) ||
							/^\\\[[ \t]*\n?([\s\S]+?)\n?[ \t]*\\\][ \t]*(?:\n|$)/.exec(src);
						return m ? { type: "mathBlock", raw: m[0], text: m[1].trim() } : undefined;
					},
					renderer(token) {
						return '<div class="cai-md-math-block">' + renderMath(token.text, true) + "</div>\n";
					},
				},
				{
					name: "mathInline",
					level: "inline",
					start(src) {
						const i = src.search(/\\\(|\$\$/);
						return i < 0 ? undefined : i;
					},
					tokenizer(src) {
						const m = /^\\\(([\s\S]+?)\\\)/.exec(src) || /^\$\$([^\n]+?)\$\$/.exec(src);
						return m ? { type: "mathInline", raw: m[0], text: m[1].trim() } : undefined;
					},
					renderer(token) {
						return '<span class="cai-md-math">' + renderMath(token.text, false) + "</span>";
					},
				},
			],
			renderer: {
				code(token) {
					const lang = normLang(token.lang);
					const code = String(token.text || "");
					const L = ctx.labels;
					return (
						'<div class="cai-md-codeblock" data-lang="' + esc(lang) + '">' +
						'<div class="cai-md-codebar"><span class="cai-md-codelang">' + esc(lang || L.code) + "</span>" +
						'<span class="cai-md-codeactions">' +
						'<button type="button" class="cai-md-codebtn" data-act="copy" aria-label="' + esc(L.copy) + '">' + esc(L.copy) + "</button>" +
						'<button type="button" class="cai-md-codebtn" data-act="download" aria-label="' + esc(L.download) + '">' + esc(L.download) + "</button>" +
						"</span></div>" +
						'<pre dir="ltr"><code class="hljs' + (lang ? " language-" + esc(lang) : "") + '">' + highlight(code, lang) + "</code></pre></div>\n"
					);
				},
				table(token) {
					return '<div class="cai-md-tablewrap" role="region" tabindex="0" aria-label="table">' + Renderer.prototype.table.call(this, token) + "</div>\n";
				},
				checkbox(token) {
					return '<span class="cai-md-check" aria-hidden="true">' + (token.checked ? "☑" : "☐") + "</span> ";
				},
			},
		});
	}

	function installHooks(p) {
		p.addHook("uponSanitizeAttribute", (node, data) => {
			const name = data.attrName;
			const value = String(data.attrValue == null ? "" : data.attrValue);
			if (name === "class") {
				const ok = value.split(/\s+/).filter((t) => CLASS_OK.test(t));
				if (ok.length) data.attrValue = ok.join(" ");
				else data.keepAttr = false;
			} else if (name === "href") {
				// DOMPurify's own URI check stays on (it validates every attribute value);
				// href / src get our narrower policy on top of it.
				if (!linkAllowed(value)) data.keepAttr = false;
			} else if (name === "src") {
				if (!imageSrcAllowed(value)) data.keepAttr = false;
			} else if (name === "data-act") {
				if (!/^(?:copy|download)$/.test(value)) data.keepAttr = false;
			} else if (name === "data-cite") {
				if (!/^\d{1,3}$/.test(value)) data.keepAttr = false;
			} else if (name === "data-lang") {
				if (!/^[A-Za-z0-9_+#.-]{0,30}$/.test(value)) data.keepAttr = false;
			} else if (name === "dir") {
				if (!/^(?:auto|ltr|rtl)$/.test(value)) data.keepAttr = false;
			} else if (name === "role") {
				if (!/^(?:region|doc-noteref)$/.test(value)) data.keepAttr = false;
			} else if (name === "tabindex") {
				if (value !== "0") data.keepAttr = false;
			}
		});

		p.addHook("afterSanitizeAttributes", (node) => {
			const tag = node.tagName;
			if (tag === "A") {
				const kind = linkAllowed(node.getAttribute("href"));
				if (!kind) {
					node.removeAttribute("href");
					node.removeAttribute("target");
					node.removeAttribute("rel");
				} else if (kind === "cite") {
					node.removeAttribute("target");
					node.removeAttribute("rel");
				} else {
					node.setAttribute("target", "_blank");
					node.setAttribute("rel", "noopener noreferrer nofollow");
				}
			} else if (tag === "IMG") {
				const src = node.getAttribute("src");
				if (!node.hasAttribute("alt")) node.setAttribute("alt", "");
				if (!imageSrcAllowed(src)) {
					// Nothing loadable survived: keep no empty shell for screen readers or layout.
					node.removeAttribute("src");
					node.setAttribute("hidden", "");
				} else {
					node.setAttribute("loading", "lazy");
					node.setAttribute("referrerpolicy", "no-referrer");
					node.setAttribute("decoding", "async");
				}
			} else if (tag === "BUTTON") {
				node.setAttribute("type", "button");
				if (!node.getAttribute("data-act")) node.setAttribute("disabled", "");
			} else if (/^(?:P|LI|H[1-6]|BLOCKQUOTE|TD|TH|DT|DD|SUMMARY)$/.test(tag)) {
				if (!node.getAttribute("dir")) node.setAttribute("dir", "auto");
			}
		});
	}

	build();

	/* --------------------------------------------------------------------- API */

	function sanitize(html) {
		if (!purify) return plain(String(html || "").replace(/<[^>]*>/g, ""));
		return purify.sanitize(String(html || ""), PURIFY_CONFIG);
	}

	/**
	 * markdown -> {html, needsMath, fallback}
	 * opts: {sources: normalized server sources (citation numbering), labels}
	 */
	function render(text, opts) {
		const o = opts || {};
		const src = String(text == null ? "" : text);
		if (!md || !purify || src.length > MAX_RENDER_CHARS) {
			return { html: plain(src), needsMath: false, fallback: true };
		}
		ctx = {
			sources: o.sources || [],
			labels: Object.assign({}, DEFAULT_LABELS, o.labels || {}),
			needsMath: false,
		};
		try {
			const raw = md.parse(src.replace(/\r\n?/g, "\n"));
			return { html: purify.sanitize(raw, PURIFY_CONFIG), needsMath: ctx.needsMath, fallback: false };
		} catch (e) {
			return { html: plain(src), needsMath: false, fallback: true };
		}
	}

	return { render, sanitize, esc, ready: !!(md && purify) };
});
