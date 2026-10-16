/**
 * Chat AI frontend tests: pure logic + the markdown/sanitising pipeline, run in node.
 *
 *   NODE_PATH=<dir containing node_modules/jsdom> node --test public/chat_ai/tests/
 *
 * (jsdom is a dev-only dependency, installed outside the repo; the shipped code has no build step.)
 * The XSS tests run real marked + DOMPurify (the vendored files) on hostile input and then parse
 * the OUTPUT, so they check what a browser would actually receive.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const JS = path.join(__dirname, "..", "js");
const logic = require(path.join(JS, "chat_ai_logic.js"));
const i18n = require(path.join(JS, "chat_ai_i18n.js"));
const { createMarkdown } = require(path.join(JS, "chat_ai_markdown.js"));

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "https://erp.example.com/app/home" });
const win = dom.window;
const libs = {
	marked: require(path.join(JS, "vendor", "marked.umd.js")),
	DOMPurify: require(path.join(JS, "vendor", "purify.min.js")),
	hljs: require(path.join(JS, "vendor", "highlight.min.js")),
	katex: require(path.join(JS, "vendor", "katex.min.js")),
};
const md = createMarkdown({ libs, window: win });

function parse(html) {
	const d = new JSDOM("<!doctype html><body>" + html + "</body>").window.document;
	return d;
}

const WEB = logic.normalizeSources([
	{ type: "web", title: "ZATCA", url: "https://zatca.gov.sa/en", domain: "zatca.gov.sa" },
	{ type: "file", title: "plan.docx", attachment: "abc" },
]);

/* ------------------------------------------------------------------ markdown */

test("renderer is ready with all libraries", () => {
	assert.equal(md.ready, true);
});

test("renders common markdown", () => {
	const { html } = md.render("# Title\n\n- one\n- two\n\n1. a\n2. b\n\n**bold** and `code` and [link](https://example.org)\n\n> quote");
	const d = parse(html);
	assert.equal(d.querySelector("h1").textContent, "Title");
	assert.equal(d.querySelectorAll("ul li").length, 2);
	assert.equal(d.querySelectorAll("ol li").length, 2);
	assert.equal(d.querySelector("strong").textContent, "bold");
	assert.equal(d.querySelector("p code").textContent, "code");
	assert.ok(d.querySelector("blockquote"));
	const a = d.querySelector("a[href='https://example.org']");
	assert.equal(a.getAttribute("target"), "_blank");
	assert.match(a.getAttribute("rel"), /noopener/);
	assert.match(a.getAttribute("rel"), /nofollow/);
});

test("tables are wrapped for scrolling", () => {
	const { html } = md.render("| a | b |\n|---|---|\n| 1 | 2 |");
	const d = parse(html);
	assert.ok(d.querySelector(".cai-md-tablewrap table"));
	assert.equal(d.querySelectorAll("td").length, 2);
});

test("code blocks get a header, buttons and syntax highlighting", () => {
	const { html } = md.render("```python\ndef f(x):\n    return x + 1\n```");
	const d = parse(html);
	const block = d.querySelector(".cai-md-codeblock");
	assert.equal(block.getAttribute("data-lang"), "python");
	assert.deepEqual(
		[...block.querySelectorAll("button[data-act]")].map((b) => b.getAttribute("data-act")),
		["copy", "download"]
	);
	assert.ok(block.querySelector("code .hljs-keyword"), "keywords are highlighted");
	assert.equal(block.querySelector("code").textContent.trim(), "def f(x):\n    return x + 1");
});

test("code content is escaped, never executed", () => {
	const { html } = md.render('```html\n<script>alert(1)</script><img src=x onerror=alert(1)>\n```');
	const d = parse(html);
	assert.equal(d.querySelectorAll("script").length, 0);
	assert.equal(d.querySelectorAll("img").length, 0);
	assert.match(d.querySelector("code").textContent, /<script>alert\(1\)<\/script>/);
});

const PAYLOADS = [
	"<img src=x onerror=alert(1)>",
	"<script>alert(1)</script>",
	"<svg onload=alert(1)></svg>",
	"<svg><script>alert(1)</script></svg>",
	"<iframe src='javascript:alert(1)'></iframe>",
	"<iframe srcdoc='<script>alert(1)</script>'></iframe>",
	"<object data='javascript:alert(1)'></object><embed src='javascript:alert(1)'>",
	"<style>*{background:url(javascript:alert(1))}</style>",
	"<form action='javascript:alert(1)'><input name=x><button formaction='javascript:alert(1)'>x</button></form>",
	"<a href='javascript:alert(1)'>click</a>",
	"[click](javascript:alert(1))",
	"[click](JaVaScRiPt:alert(1))",
	"[click]( javascript:alert(1))",
	"[click](&#106;avascript:alert(1))",
	"[click](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
	"[click](vbscript:msgbox(1))",
	"[click](//evil.example/phish)",
	"<a href='//evil.example'>x</a>",
	"![x](https://evil.example/track.png)",
	"![x](javascript:alert(1))",
	"![x](data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+)",
	"<img src='https://evil.example/pixel.gif'>",
	"<div style='position:fixed;inset:0' onclick='alert(1)'>cover</div>",
	"<div class='cai-launcher cai-btn--danger'>spoof</div>",
	"<button data-act='delete' onclick='alert(1)'>x</button>",
	"<a id='x' name='y' href='https://ok.example'>x</a>",
	"<math><mtext><table><mglyph><style><!--</style><img title=\"--&gt;&lt;img src=x onerror=alert(1)&gt;\">",
	"<noscript><p title=\"</noscript><img src=x onerror=alert(1)>\">",
	"<details open ontoggle=alert(1)>x</details>",
	"<video><source onerror=alert(1)></video>",
	"<base href='https://evil.example/'><a href='x'>x</a>",
	"<meta http-equiv='refresh' content='0;url=https://evil.example'>",
	"<link rel=stylesheet href='https://evil.example/x.css'>",
	"<input autofocus onfocus=alert(1)>",
	"<a href=\"https://ok.example\" onmouseover=\"alert(1)\">x</a>",
	"<table><tr><td><img src=x onerror=alert(1)></td></tr></table>",
	"- item\n  <img src=x onerror=alert(1)>",
	"$$\\href{javascript:alert(1)}{x}$$",
	"\\[ \\url{javascript:alert(1)} \\]",
	"<annotation-xml encoding='text/html'><img src=x onerror=alert(1)></annotation-xml>",
];

function assertHarmless(html, source) {
	const d = parse(html);
	for (const el of d.querySelectorAll("*")) {
		assert.ok(
			!/^(script|iframe|object|embed|style|form|input|svg|link|meta|base|video|audio|source|template|textarea|select)$/i.test(el.tagName),
			`forbidden tag <${el.tagName}> from: ${source}`
		);
		for (const attr of el.attributes) {
			assert.ok(!/^on/i.test(attr.name), `event handler ${attr.name} from: ${source}`);
			assert.ok(!["style", "srcdoc", "formaction", "action", "id", "name"].includes(attr.name), `attr ${attr.name} from: ${source}`);
		}
		if (el.hasAttribute("href")) {
			const href = el.getAttribute("href").replace(/[\u0000- ]/g, "");
			assert.match(href, /^(https?:|mailto:|tel:|\/app\/|#cai-src-\d+$)/i, `href ${href} from: ${source}`);
			assert.ok(!href.startsWith("//"), `protocol-relative href from: ${source}`);
		}
		if (el.hasAttribute("src")) {
			const src = el.getAttribute("src");
			assert.match(src, /^(data:image\/(png|jpe?g|gif|webp);base64,|https:\/\/erp\.example\.com\/(files|private\/files|assets)\/)/i, `img src ${src} from: ${source}`);
		}
		const cls = el.getAttribute("class");
		if (cls) {
			for (const c of cls.split(/\s+/)) {
				assert.match(c, /^(hljs(-[a-z_]+)*|language-[\w+#.-]+|cai-md-[a-z-]+)$/, `class ${c} from: ${source}`);
			}
		}
	}
	// A model-supplied <button> may survive only as an inert, disabled element; the only live
	// buttons are the renderer's own code-block actions.
	for (const b of d.querySelectorAll("button")) {
		const act = b.getAttribute("data-act");
		assert.ok(act === "copy" || act === "download" || b.hasAttribute("disabled"), `live stray button from: ${source}`);
		assert.equal(b.getAttribute("type"), "button", `button without type=button from: ${source}`);
	}
}

for (const payload of PAYLOADS) {
	test("hostile input is neutralised: " + payload.slice(0, 60).replace(/\n/g, " "), () => {
		assertHarmless(md.render(payload, { sources: WEB }).html, payload);
		assertHarmless(md.render("Intro\n\n" + payload + "\n\nOutro", { sources: WEB }).html, payload);
	});
}

test("legitimate external links survive and are hardened; lookalike classes do not", () => {
	const d = parse(md.render("[ok](https://example.org/a?b=1) <a class='cai-btn' href='/app/customer/ACME'>internal</a>").html);
	const [ext, internal] = d.querySelectorAll("a");
	assert.equal(ext.getAttribute("href"), "https://example.org/a?b=1");
	assert.equal(ext.getAttribute("target"), "_blank");
	assert.equal(internal.getAttribute("href"), "/app/customer/ACME");
	assert.equal(internal.getAttribute("class"), null);
});

test("an image that cannot load leaves a hidden, alt-text-bearing shell (no empty element for screen readers)", () => {
	const d = parse(md.render("<img src=x onerror=alert(1)> ![chart](https://evil.example/c.png)").html);
	const imgs = [...d.querySelectorAll("img")];
	for (const img of imgs) {
		assert.equal(img.hasAttribute("src"), false);
		assert.equal(img.hasAttribute("hidden"), true);
		assert.equal(img.hasAttribute("alt"), true);
	}
	assert.equal(d.querySelectorAll("img:not([alt])").length, 0);
});

test("images only load from inline raster data or the site's own files", () => {
	const png = "data:image/png;base64,iVBORw0KGgo=";
	const d = parse(md.render(`![a](${png}) ![b](/files/x.png) ![c](https://erp.example.com/private/files/y.png) ![d](/files/../etc/passwd)`).html);
	const srcs = [...d.querySelectorAll("img")].map((i) => i.getAttribute("src")).filter(Boolean);
	assert.deepEqual(srcs, [png, "/files/x.png", "https://erp.example.com/private/files/y.png"]);
	for (const img of d.querySelectorAll("img[src]")) assert.equal(img.getAttribute("referrerpolicy"), "no-referrer");
});

test("citations link to the returned sources only", () => {
	const d = parse(md.render("Phase 2 is live [1] and the plan agrees [2]. Not a source [3]. A link [1](https://x.example).", { sources: WEB }).html);
	const cites = [...d.querySelectorAll("a[data-cite]")];
	assert.deepEqual(cites.map((a) => a.getAttribute("data-cite")), ["1", "2"]);
	assert.equal(cites[0].getAttribute("href"), "#cai-src-1");
	assert.match(cites[0].getAttribute("title"), /ZATCA/);
	assert.match(d.body.textContent, /\[3\]/, "unknown reference stays as text");
	assert.ok(d.querySelector("a[href='https://x.example']"), "[1](url) is a normal link, not a citation");
});

test("without sources, [n] is plain text (no invented citations)", () => {
	const d = parse(md.render("The answer is 42 [1].").html);
	assert.equal(d.querySelectorAll("a").length, 0);
	assert.match(d.body.textContent, /\[1\]/);
});

test("math renders as MathML without inline styles", () => {
	const d = parse(md.render("Energy: $$E = mc^2$$\n\n$$\n\\frac{a}{b}\n$$").html);
	assert.ok(d.querySelector("math"), "MathML present");
	assert.equal(d.querySelectorAll("[style]").length, 0);
	assertHarmless(md.render("$$\\frac{a}{b}$$").html, "math");
});

test("math falls back to code while KaTeX is not loaded, and says so", () => {
	const noMath = createMarkdown({ libs: { marked: libs.marked, DOMPurify: libs.DOMPurify, hljs: libs.hljs }, window: win });
	const r = noMath.render("$$x^2$$");
	assert.equal(r.needsMath, true);
	assert.match(r.html, /cai-md-math-pending/);
});

test("oversized answers render as escaped text instead of freezing the UI", () => {
	const r = md.render("<b>x</b>" + "a".repeat(160000));
	assert.equal(r.fallback, true);
	assert.ok(!/<b>/.test(r.html));
});

test("without the libraries everything is escaped plain text", () => {
	const bare = createMarkdown({ libs: {}, window: win });
	assert.equal(bare.ready, false);
	const r = bare.render("# hi <img src=x onerror=alert(1)>\nline2");
	assert.equal(r.fallback, true);
	assert.ok(!/<img/.test(r.html));
	assert.match(r.html, /&lt;img/);
	assert.ok(!/onerror=alert/.test(bare.sanitize("<img src=x onerror=alert(1)>")));
});

test("model output cannot borrow the UI's own classes", () => {
	const d = parse(md.render("<span class='cai-send cai-launcher cai-btn--primary hljs'>x</span>").html);
	const cls = (d.querySelector("span") || {}).getAttribute && d.querySelector("span").getAttribute("class");
	assert.ok(!cls || cls === "hljs", `got ${cls}`);
});

/* --------------------------------------------------------------------- logic */

test("sources keep their position, so [n] is always sources[n-1]", () => {
	const s = logic.normalizeSources([
		{ type: "web", title: "A", url: "javascript:alert(1)" },
		null,
		{ type: "web", title: "B", url: "https://b.example/x" },
		{ attachment: "att1", chunk_index: 2, title: "f.docx" },
	]);
	assert.equal(s.length, 4);
	assert.deepEqual(s.map((x) => x.n), [1, 2, 3, 4]);
	assert.equal(s[0].url, "", "javascript: URLs are dropped, the slot stays");
	assert.equal(s[1].type, "other");
	assert.equal(s[2].domain, "b.example");
	assert.equal(s[3].type, "file");
	assert.deepEqual(logic.groupSources(s).web.map((x) => x.n), [1, 3]);
	assert.equal(logic.sourceCount(s), 3);
	assert.deepEqual(logic.normalizeSources(undefined), []);
});

test("history pages merge without duplicates and keep the in-flight turn last", () => {
	const row = (n, role, c) => ({ name: n, role, content: c, creation: "2026-01-01 00:00:0" + n });
	const msgs = (...rows) => rows.map((r) => logic.rowToMessage(r));
	const newest = msgs(row(3, "user", "c"), row(4, "assistant", "d"));
	const local = logic.emptyMessage("user", "typing now");
	let shown = logic.mergeHistory([local], newest, "replace");
	assert.deepEqual(shown.map((m) => m.text), ["c", "d", "typing now"]);
	const older = msgs(row(1, "user", "a"), row(2, "assistant", "b"), row(3, "user", "c"));
	shown = logic.mergeHistory(shown, older, "prepend");
	assert.deepEqual(shown.map((m) => m.text), ["a", "b", "c", "d", "typing now"]);
	assert.equal(logic.oldestCursor(shown), "2026-01-01 00:00:01");
	assert.equal(logic.mergeHistory(shown, newest, "replace").length, 3);
});

test("persisted rows become UI messages (errors, attachments, sources)", () => {
	const a = logic.rowToMessage({
		name: "m1", role: "assistant", content: "Hi [1]", creation: "x", error: "1", model: "m-x",
		content_json: JSON.stringify({ sources: [{ type: "web", title: "T", url: "https://t.example" }], meta: { model: "m-x", fallback_from: "m-y" }, blocks: [{ type: "badge", data: "b" }] }),
	});
	assert.equal(a.status, "error");
	assert.equal(a.sources[0].domain, "t.example");
	assert.equal(logic.metaBadge(a.meta).fallbackFrom, "m-y");
	const u = logic.rowToMessage({ name: "m2", role: "user", content: "see file", attachments: JSON.stringify([{ name: "A1", file_name: "x.csv", kind: "spreadsheet" }]) });
	assert.equal(u.attachments[0].file_name, "x.csv");
	assert.equal(logic.rowToMessage({ name: "m3", role: "assistant", content: "x", content_json: "{not json" }).blocks.length, 0);
});

test("stream buffer: batching and reset", () => {
	const b = new logic.StreamBuffer();
	b.push({ chunk: "Hel" }).push({ chunk: "lo" });
	assert.equal(b.text, "");
	assert.equal(b.take(), true);
	assert.equal(b.text, "Hello");
	assert.equal(b.take(), false);
	b.push({ chunk: " narration" }).push({ reset: true }).push({ chunk: "Final" });
	assert.equal(b.flushAll(), "Final", "reset drops shown and queued text");
	b.push({ chunk: "", done: true });
	assert.equal(b.done, true);
});

test("realtime events only apply to the live turn of the same session", () => {
	const turn = { session: "S1", finalized: false };
	assert.equal(logic.eventBelongsToTurn({ session: "S1" }, turn), true);
	assert.equal(logic.eventBelongsToTurn({ session: "S2" }, turn), false);
	assert.equal(logic.eventBelongsToTurn({ session: "S1" }, { ...turn, finalized: true }), false);
	assert.equal(logic.eventBelongsToTurn({ session: "S1" }, null), false);
});

test("error classification", () => {
	assert.equal(logic.isNetworkError({ status: 0 }), true);
	assert.equal(logic.isNetworkError({ status: 504 }), true);
	assert.equal(logic.isNetworkError({ status: 403 }), false);
	assert.equal(logic.isNetworkError({ name: "TypeError", message: "Failed to fetch" }), true);
	assert.equal(logic.isNetworkError(null), false);
	const e = logic.errorFromPayload({ ok: false, error: "slow down", code: "rate_limited", retryable: true });
	assert.deepEqual(e, { message: "slow down", code: "rate_limited", retryable: true });
	assert.equal(logic.canRetry(e), true);
	assert.equal(logic.canRetry({ code: "auth", retryable: false }), false);
	assert.equal(logic.canRetry(null), false);
});

test("regenerate is offered only on the last answer", () => {
	const u = logic.emptyMessage("user", "q");
	const a1 = logic.emptyMessage("assistant", "a");
	const u2 = logic.emptyMessage("user", "q2");
	const a2 = logic.emptyMessage("assistant", "a2");
	const list = [u, a1, u2, a2];
	assert.equal(logic.canRegenerate(list, a2), true);
	assert.equal(logic.canRegenerate(list, a1), false);
	assert.equal(logic.canRegenerate(list, u2), false);
	assert.equal(logic.canRegenerate([a1], a1), false);
	assert.equal(logic.lastIndexOfRole(list, "user"), 2);
	assert.equal(logic.truncateAfter(list, 1).length, 2);
});

test("client-side file hints mirror the server rules", () => {
	const f = (name, size) => ({ name, size });
	assert.equal(logic.clientFileCheck(f("a.pdf", 10), { maxMb: 5 }).ok, true);
	assert.equal(logic.clientFileCheck(f("a.exe", 10), {}).reason, "type");
	assert.equal(logic.clientFileCheck(f("a.pdf", 6 * 1024 * 1024), { maxMb: 5 }).reason, "size");
	assert.equal(logic.clientFileCheck(f("a.pdf", 0), {}).reason, "empty");
	assert.equal(logic.clientFileCheck(f("a.png", 5), { vision: false }).reason, "vision");
	assert.equal(logic.clientFileCheck(f("a.pdf", 5), { fileUpload: false }).reason, "disabled");
	assert.equal(logic.clientFileCheck(f("A.DOCX", 5), {}).kind, "document");
	assert.ok(!logic.acceptAttr({ vision: false }).includes(".png"));
	assert.ok(logic.acceptAttr({}).includes(".xlsx"));
	assert.equal(logic.humanSize(2048), "2.0 KB");
});

test("exported filenames and code filenames are safe", () => {
	assert.equal(logic.exportFilename("Q3 VAT: review / 2026!", new Date(2026, 9, 5)), "q3-vat-review-2026-20261005.md");
	assert.equal(logic.exportFilename("../../etc/passwd", new Date(2026, 0, 2)), "etcpasswd-20260102.md");
	assert.equal(logic.exportFilename("", new Date(2026, 0, 2)), "chat-20260102.md");
	assert.equal(logic.codeFilename("python"), "code.py");
	assert.equal(logic.codeFilename("weird lang!"), "code.txt");
});

test("CSV export neutralises spreadsheet formula injection", () => {
	const csv = logic.tableToCsv({ headers: ["a", "b"], rows: [["=HYPERLINK(\"http://evil\")", "+1"], ["ok", "say \"hi\", ok"], ["@cmd", null]] });
	const lines = csv.split("\r\n");
	assert.equal(lines[0], "a,b");
	assert.match(lines[1], /^"'=HYPERLINK\(""http:\/\/evil""\)",'\+1$/);
	assert.equal(lines[2], 'ok,"say ""hi"", ok"');
	assert.equal(lines[3], "'@cmd,");
});

test("sessions group by recency with pinned first", () => {
	const now = new Date(2026, 9, 15, 12, 0, 0).getTime();
	const d = (days) => new Date(now - days * 86400000).toISOString().replace("T", " ").slice(0, 19);
	const groups = logic.groupSessions(
		[
			{ name: "a", last_message_at: d(0) },
			{ name: "b", last_message_at: d(1) },
			{ name: "c", last_message_at: d(4) },
			{ name: "d", last_message_at: d(40) },
			{ name: "p", is_pinned: 1, last_message_at: d(40) },
			{ name: "n" },
		],
		now
	);
	assert.deepEqual(groups.map((g) => g.key), ["pinned", "today", "yesterday", "week", "older"]);
	assert.deepEqual(groups.find((g) => g.key === "older").items.map((s) => s.name), ["d", "n"]);
});

test("search highlighting is regex-safe", () => {
	const parts = logic.highlightParts("Price (USD) is $5.00 [net]", "(usd) $5.00 [net] .*");
	assert.equal(parts.map((p) => p.text).join(""), "Price (USD) is $5.00 [net]");
	assert.ok(parts.some((p) => p.hit && p.text === "(USD)"));
	assert.deepEqual(logic.highlightParts("abc", ""), [{ text: "abc", hit: false }]);
	assert.doesNotThrow(() => logic.highlightParts("x", "\\ ( ["));
});

test("keyboard shortcuts do not hijack Desk outside the panel", () => {
	const ev = (key, o = {}) => ({ key, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, ...o });
	const ctx = (o = {}) => ({ open: true, inPanel: true, typing: false, overlay: false, busy: false, frappeModal: false, ...o });
	assert.equal(logic.matchShortcut(ev("J", { ctrlKey: true, shiftKey: true }), ctx({ open: false, inPanel: false })), "toggle");
	assert.equal(logic.matchShortcut(ev("k", { ctrlKey: true }), ctx({ inPanel: false })), "", "Ctrl+K stays Desk's search outside the panel");
	assert.equal(logic.matchShortcut(ev("k", { ctrlKey: true }), ctx()), "focus-search");
	assert.equal(logic.matchShortcut(ev("O", { metaKey: true, shiftKey: true }), ctx()), "new-chat");
	assert.equal(logic.matchShortcut(ev("?"), ctx()), "help");
	assert.equal(logic.matchShortcut(ev("?"), ctx({ typing: true })), "", "typing a ? must not open help");
	assert.equal(logic.matchShortcut(ev("/"), ctx({ typing: true })), "");
	assert.equal(logic.matchShortcut(ev("Escape"), ctx({ overlay: true })), "close-overlay");
	assert.equal(logic.matchShortcut(ev("Escape"), ctx({ busy: true })), "stop");
	assert.equal(logic.matchShortcut(ev("Escape"), ctx()), "close");
	assert.equal(logic.matchShortcut(ev("Escape"), ctx({ frappeModal: true })), "", "a Frappe dialog owns Escape");
	assert.equal(logic.matchShortcut(ev("Escape"), ctx({ inPanel: false })), "");
	assert.equal(logic.matchShortcut(ev("k", { ctrlKey: true }), ctx({ open: false })), "");
});

/* ---------------------------------------------------------------------- i18n */

test("every language falls back to English for missing keys, and placeholders fill", () => {
	const en = i18n.strings("en");
	for (const code of ["ar", "ml", "xx"]) {
		const s = i18n.strings(code);
		for (const k of Object.keys(en)) assert.ok(typeof s[k] === "string" && s[k].length, `${code}.${k}`);
	}
	assert.notEqual(i18n.strings("ar").send, en.send);
	assert.equal(i18n.fmt("{n} steps, {x}", { n: 3 }), "3 steps, {x}");
});

test("Arabic covers every English string", () => {
	const en = i18n.dictionaries.en;
	const ar = i18n.dictionaries.ar;
	const missing = Object.keys(en).filter((k) => !(k in ar));
	assert.deepEqual(missing, []);
	for (const k of Object.keys(en)) {
		const ph = (v) => (String(v).match(/\{\w+\}/g) || []).sort().join();
		assert.equal(ph(ar[k]), ph(en[k]), `placeholders of ${k}`);
	}
});
