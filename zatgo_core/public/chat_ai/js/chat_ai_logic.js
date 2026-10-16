/**
 * Chat AI -- pure UI logic (no DOM, no Vue, no frappe).
 *
 * Everything here is deterministic and unit-tested with plain node
 * (public/chat_ai/tests/chat_ai_logic.test.js). The Vue component only wires
 * these helpers to the DOM and to the whitelisted API.
 */
(function (root, factory) {
	const api = factory();
	if (typeof module === "object" && module.exports) {
		module.exports = api;
	} else {
		root.chat_ai = root.chat_ai || {};
		root.chat_ai.logic = api;
	}
})(typeof self !== "undefined" ? self : this, function () {
	"use strict";

	/* ---------------------------------------------------------------- parsing */

	function parseJSON(value, fallback) {
		if (value && typeof value === "object") return value;
		if (typeof value !== "string" || !value) return fallback;
		try {
			const parsed = JSON.parse(value);
			return parsed && typeof parsed === "object" ? parsed : fallback;
		} catch (e) {
			return fallback;
		}
	}

	function clip(value, max) {
		const s = value == null ? "" : String(value);
		return s.length > max ? s.slice(0, max - 1) + "…" : s;
	}

	function safeWebUrl(url) {
		const raw = String(url || "").replace(/[\u0000- ]/g, "");
		return /^https?:\/\//i.test(raw) ? String(url).trim() : "";
	}

	/**
	 * Sources exactly as the server returned them. Position is the citation
	 * number: [n] in the answer is sources[n - 1], so entries are never dropped
	 * or re-ordered (an entry that cannot be shown keeps its slot with
	 * type "other" and is simply not rendered / not linkable).
	 */
	function normalizeSources(raw) {
		if (!Array.isArray(raw)) return [];
		return raw.map((s, i) => {
			const n = i + 1;
			if (!s || typeof s !== "object") return { n, type: "other" };
			let type = s.type;
			if (type !== "web" && type !== "file") {
				type = s.attachment ? "file" : s.url ? "web" : "other";
			}
			if (type === "other") return { n, type };
			const out = {
				n,
				type,
				title: clip(s.title || s.file_name || s.domain || "", 200),
				snippet: clip(s.snippet || "", 400),
			};
			if (type === "web") {
				out.url = safeWebUrl(s.url);
				out.domain = clip(s.domain || hostOf(out.url), 100);
				if (!out.title) out.title = out.domain || out.url;
			} else {
				out.attachment = clip(s.attachment || "", 140);
				out.chunk = typeof s.chunk_index === "number" ? s.chunk_index : null;
				if (!out.title) out.title = out.attachment;
			}
			return out;
		});
	}

	function hostOf(url) {
		const m = /^https?:\/\/([^/?#:]+)/i.exec(url || "");
		return m ? m[1].replace(/^www\./i, "") : "";
	}

	/** {web: [...], file: [...]} -- only entries the server returned, in order. */
	function groupSources(sources) {
		const out = { web: [], file: [] };
		(sources || []).forEach((s) => {
			if (s && (s.type === "web" || s.type === "file")) out[s.type].push(s);
		});
		return out;
	}

	function sourceCount(sources) {
		const g = groupSources(sources);
		return g.web.length + g.file.length;
	}

	/* --------------------------------------------------------------- messages */

	let _localSeq = 0;
	function localId(prefix) {
		_localSeq += 1;
		return (prefix || "m") + "-" + _localSeq + "-" + Math.random().toString(36).slice(2, 7);
	}

	function emptyMessage(role, text) {
		return {
			id: localId("l"),
			serverId: "",
			role,
			text: text || "",
			blocks: [],
			sources: [],
			meta: null,
			attachments: [],
			creation: "",
			status: "done", // pending | streaming | done | error | queued
			error: null, // {message, code, retryable}
			steps: [],
			stepsOpen: false,
			srcOpen: null,
			needs_confirmation: false,
			needs_plan_approval: false,
			pending_plan: [],
			pending_assumptions: [],
			confirmation_token: "",
			confirmState: "",
			persisted: false,
		};
	}

	/** A persisted AI Chat Message row (history API) -> UI message. */
	function rowToMessage(row) {
		const cj = parseJSON(row.content_json, {});
		const role = row.role === "user" ? "user" : "assistant";
		const msg = emptyMessage(role, row.content || "");
		msg.id = "s-" + row.name;
		msg.serverId = row.name;
		msg.persisted = true;
		msg.creation = row.creation || "";
		if (role === "assistant") {
			msg.blocks = Array.isArray(cj.blocks) ? cj.blocks : [];
			msg.sources = normalizeSources(cj.sources);
			msg.meta = cj.meta && typeof cj.meta === "object" ? cj.meta : null;
			if (!msg.meta && row.model) msg.meta = { model: row.model };
			if (row.error && String(row.error) !== "0") {
				msg.status = "error";
				msg.error = { message: "", code: "interrupted", retryable: true };
			}
		} else {
			const atts = parseJSON(row.attachments, []);
			msg.attachments = Array.isArray(atts)
				? atts
						.filter((a) => a && typeof a === "object")
						.map((a) => ({
							name: a.name || "",
							file_name: clip(a.file_name || a.name || "", 120),
							kind: a.kind || "",
						}))
				: [];
		}
		return msg;
	}

	/**
	 * Merge a history page into the loaded messages without duplicating.
	 *   mode "prepend": `incoming` is an OLDER page -> goes before what is shown
	 *   mode "replace": `incoming` is the newest page -> becomes the whole list
	 * Messages that are not persisted yet (no serverId: the in-flight turn)
	 * stay at the end in both modes.
	 */
	function mergeHistory(existing, incoming, mode) {
		const persisted = (existing || []).filter((m) => m.serverId);
		const local = (existing || []).filter((m) => !m.serverId);
		const seen = new Set();
		const take = (list) =>
			list.filter((m) => {
				if (!m.serverId) return true;
				if (seen.has(m.serverId)) return false;
				seen.add(m.serverId);
				return true;
			});
		if (mode === "prepend") {
			const older = incoming.filter((m) => !persisted.some((p) => p.serverId === m.serverId));
			return take([...older, ...persisted]).concat(local);
		}
		return take(incoming).concat(local);
	}

	/** Cursor for the next (older) history page: creation of the oldest persisted message. */
	function oldestCursor(messages) {
		for (const m of messages || []) {
			if (m.serverId && m.creation) return m.creation;
		}
		return "";
	}

	/** Messages up to and including index `idx` (what stays after "edit from here"). */
	function truncateAfter(messages, idx) {
		return (messages || []).slice(0, idx + 1);
	}

	function lastIndexOfRole(messages, role) {
		for (let i = (messages || []).length - 1; i >= 0; i--) {
			if (messages[i].role === role) return i;
		}
		return -1;
	}

	/** Regenerate is offered on the last assistant message that follows a user message. */
	function canRegenerate(messages, msg) {
		if (!msg || msg.role !== "assistant") return false;
		const list = messages || [];
		const idx = list.findIndex((m) => m.id === msg.id);
		if (idx < 1 || idx !== list.length - 1) return false;
		return list[idx - 1].role === "user";
	}

	/* ------------------------------------------------------------- stream state */

	/**
	 * Live text of the current turn. Realtime chunks are only queued (cheap);
	 * take() moves them into `text` once per animation frame so a burst of
	 * deltas costs one render. reset drops everything shown or queued so far.
	 */
	class StreamBuffer {
		constructor() {
			this.text = "";
			this.pending = "";
			this.done = false;
			this.resets = 0;
			this.started = false;
		}

		push(evt) {
			if (!evt) return this;
			if (evt.reset) {
				this.text = "";
				this.pending = "";
				this.resets += 1;
			}
			if (evt.chunk) {
				this.pending += String(evt.chunk);
				this.started = true;
			}
			if (evt.done) this.done = true;
			return this;
		}

		/** Move queued text into `text`; true when something changed. */
		take() {
			if (!this.pending) return false;
			this.text += this.pending;
			this.pending = "";
			return true;
		}

		flushAll() {
			this.take();
			return this.text;
		}
	}

	/**
	 * Should a realtime event be applied to the in-flight turn? Events carry the
	 * session they belong to; anything for another conversation, or arriving after
	 * the turn was finalised by the send() response, is ignored.
	 */
	function eventBelongsToTurn(evt, turn) {
		if (!evt || !turn || turn.finalized) return false;
		if (evt.session && turn.session && evt.session !== turn.session) return false;
		return true;
	}

	/* ------------------------------------------------------------------ errors */

	/** frappe.call failure shapes -> "the connection broke, the server may still be working". */
	function isNetworkError(err) {
		if (!err) return false;
		const status = Number(err.status != null ? err.status : err.statusCode);
		if (status === 0 || status === 502 || status === 503 || status === 504 || status === 524) return true;
		if (Number.isFinite(status) && status >= 400) return false;
		const text = String(err.statusText || err.message || err.textStatus || "").toLowerCase();
		if (err.name === "TypeError" && /fetch|network/.test(text)) return true;
		return /(network|failed to fetch|timeout|timed out|abort|offline|connection)/.test(text);
	}

	/** ok:false envelope -> friendly error object for the message. */
	function errorFromPayload(payload) {
		const p = payload || {};
		return {
			message: String(p.error || "").trim(),
			code: p.code || "",
			retryable: p.retryable === true,
		};
	}

	const RETRYABLE_CODES = ["rate_limited", "timeout", "provider_unavailable", "network", "internal", "interrupted"];
	function canRetry(error) {
		return !!error && (error.retryable === true || RETRYABLE_CODES.includes(error.code));
	}

	/* ------------------------------------------------------------------- files */

	const FILE_TYPES = {
		pdf: "document",
		docx: "document",
		xlsx: "spreadsheet",
		csv: "spreadsheet",
		txt: "text",
		md: "text",
		png: "image",
		jpg: "image",
		jpeg: "image",
		gif: "image",
		webp: "image",
	};

	function extOf(name) {
		const m = /\.([A-Za-z0-9]+)$/.exec(String(name || ""));
		return m ? m[1].toLowerCase() : "";
	}

	function humanSize(bytes) {
		const n = Number(bytes) || 0;
		if (n < 1024) return n + " B";
		if (n < 1024 * 1024) return (n / 1024).toFixed(n < 10240 ? 1 : 0) + " KB";
		return (n / 1024 / 1024).toFixed(1) + " MB";
	}

	/**
	 * Client-side hint only (the server validates type, magic bytes and size).
	 * features: {file_upload, vision}; maxMb from list_models.
	 */
	function clientFileCheck(file, opts) {
		const o = opts || {};
		const name = (file && file.name) || "";
		const size = (file && file.size) || 0;
		if (o.fileUpload === false) return { ok: false, reason: "disabled" };
		if (!size) return { ok: false, reason: "empty" };
		const kind = FILE_TYPES[extOf(name)];
		if (!kind) return { ok: false, reason: "type" };
		if (kind === "image" && o.vision === false) return { ok: false, reason: "vision" };
		if (o.maxMb && size > o.maxMb * 1024 * 1024) return { ok: false, reason: "size" };
		return { ok: true, kind };
	}

	function acceptAttr(opts) {
		const o = opts || {};
		return Object.keys(FILE_TYPES)
			.filter((e) => o.vision !== false || FILE_TYPES[e] !== "image")
			.map((e) => "." + e)
			.join(",");
	}

	/* ----------------------------------------------------------------- display */

	const CODE_EXT = {
		javascript: "js", js: "js", typescript: "ts", ts: "ts", python: "py", py: "py", json: "json", html: "html",
		xml: "xml", css: "css", scss: "scss", sql: "sql", bash: "sh", shell: "sh", sh: "sh", yaml: "yml", yml: "yml",
		markdown: "md", md: "md", java: "java", c: "c", cpp: "cpp", csharp: "cs", go: "go", rust: "rs", php: "php",
		ruby: "rb", swift: "swift", kotlin: "kt", diff: "diff", ini: "ini", csv: "csv", text: "txt", plaintext: "txt",
	};

	function codeFilename(lang) {
		const l = String(lang || "").toLowerCase();
		return "code." + (CODE_EXT[l] || (/^[a-z0-9]{1,6}$/.test(l) ? l : "txt"));
	}

	function slug(text) {
		const s = String(text || "")
			.normalize("NFKD")
			.replace(/[^\w\s-]/g, "")
			.trim()
			.replace(/[\s_]+/g, "-")
			.toLowerCase();
		return s.slice(0, 50) || "chat";
	}

	function exportFilename(title, date) {
		const d = date || new Date();
		const pad = (n) => String(n).padStart(2, "0");
		return `${slug(title)}-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}.md`;
	}

	/** Answer badge: which model answered, by which route, and whether a fallback was used. */
	function metaBadge(meta) {
		if (!meta || typeof meta !== "object") return null;
		const model = String(meta.model || "").trim();
		if (!model) return null;
		return {
			model,
			route: String(meta.route || ""),
			fallbackFrom: String(meta.fallback_from || ""),
		};
	}

	function previewText(text, max) {
		return String(text || "")
			.replace(/```[\s\S]*?```/g, " ")
			.replace(/[#*_`>|~-]+/g, " ")
			.replace(/\[(\d+)\]/g, " ")
			.replace(/\s+/g, " ")
			.trim()
			.slice(0, max || 160);
	}

	/** Session list grouping by recency (pinned first). `now` injectable for tests. */
	function groupSessions(sessions, now) {
		const t0 = new Date(now || Date.now());
		const startOfDay = new Date(t0.getFullYear(), t0.getMonth(), t0.getDate()).getTime();
		const DAY = 86400000;
		const buckets = { pinned: [], today: [], yesterday: [], week: [], older: [] };
		(sessions || []).forEach((s) => {
			if (s.is_pinned) {
				buckets.pinned.push(s);
				return;
			}
			const when = Date.parse(String(s.last_message_at || s.modified || "").replace(" ", "T"));
			if (!Number.isFinite(when) || when < startOfDay - 7 * DAY) buckets.older.push(s);
			else if (when >= startOfDay) buckets.today.push(s);
			else if (when >= startOfDay - DAY) buckets.yesterday.push(s);
			else buckets.week.push(s);
		});
		return ["pinned", "today", "yesterday", "week", "older"]
			.filter((k) => buckets[k].length)
			.map((k) => ({ key: k, items: buckets[k] }));
	}

	/** Split text around case-insensitive hits of the query words for <mark> rendering (no HTML). */
	function highlightParts(text, query) {
		const s = String(text || "");
		const words = String(query || "")
			.split(/\s+/)
			.map((w) => w.trim())
			.filter((w) => w.length > 1)
			.slice(0, 5);
		if (!s || !words.length) return [{ text: s, hit: false }];
		const re = new RegExp("(" + words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "ig");
		const parts = [];
		let last = 0;
		let m;
		while ((m = re.exec(s))) {
			if (m.index > last) parts.push({ text: s.slice(last, m.index), hit: false });
			parts.push({ text: m[0], hit: true });
			last = m.index + m[0].length;
			if (m[0].length === 0) re.lastIndex++;
		}
		if (last < s.length) parts.push({ text: s.slice(last), hit: false });
		return parts;
	}

	function fmtCell(cell) {
		if (cell == null) return "";
		if (typeof cell === "object") {
			try {
				return JSON.stringify(cell);
			} catch (e) {
				return String(cell);
			}
		}
		return String(cell);
	}

	function csvEscape(v) {
		let s = fmtCell(v);
		// Neutralise spreadsheet formula injection in exported files.
		if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
		return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
	}

	function tableToCsv(data) {
		const d = data || {};
		const rows = [d.headers || []].concat(d.rows || []);
		return rows.map((r) => (r || []).map(csvEscape).join(",")).join("\r\n");
	}

	/* --------------------------------------------------------------- shortcuts */

	/**
	 * Keyboard shortcuts of the chat panel. `ctx`: {open, inPanel, typing,
	 * overlay (a menu/dialog is open), busy, frappeModal}. Returns an action
	 * name or "". Chat shortcuts that could clash with Desk / the browser are
	 * only active while focus is inside the panel; Ctrl+Shift+J (toggle) is the
	 * one global shortcut and is not used by Frappe.
	 */
	function matchShortcut(e, ctx) {
		const c = ctx || {};
		const key = String(e.key || "");
		const lower = key.toLowerCase();
		const mod = !!(e.ctrlKey || e.metaKey);
		if (mod && e.shiftKey && !e.altKey && lower === "j") return "toggle";
		if (!c.open) return "";
		if (key === "Escape") {
			if (c.frappeModal) return "";
			if (c.overlay) return "close-overlay";
			if (c.busy && c.inPanel) return "stop";
			if (c.inPanel) return "close";
			return "";
		}
		if (!c.inPanel) return "";
		if (mod && !e.shiftKey && !e.altKey && lower === "k") return "focus-search";
		if (mod && e.shiftKey && !e.altKey && lower === "o") return "new-chat";
		if (!mod && !e.altKey && key === "?" && !c.typing) return "help";
		if (!mod && !e.altKey && key === "/" && !c.typing) return "focus-input";
		return "";
	}

	return {
		parseJSON,
		clip,
		safeWebUrl,
		normalizeSources,
		groupSources,
		sourceCount,
		localId,
		emptyMessage,
		rowToMessage,
		mergeHistory,
		oldestCursor,
		truncateAfter,
		lastIndexOfRole,
		canRegenerate,
		StreamBuffer,
		eventBelongsToTurn,
		isNetworkError,
		errorFromPayload,
		canRetry,
		FILE_TYPES,
		extOf,
		humanSize,
		clientFileCheck,
		acceptAttr,
		codeFilename,
		slug,
		exportFilename,
		metaBadge,
		previewText,
		groupSessions,
		highlightParts,
		fmtCell,
		tableToCsv,
		matchShortcut,
	};
});
