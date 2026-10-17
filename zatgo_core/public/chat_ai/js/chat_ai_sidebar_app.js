/**
 * ZatGo AI (ZAI) — Vue 3 Desk slide-out.
 *
 * Pure logic lives in chat_ai.logic (chat_ai_logic.js), strings in chat_ai.i18n,
 * markdown + sanitising in chat_ai.createMarkdown (chat_ai_markdown.js). This file wires
 * them to the DOM and to the whitelisted API (zatgo_core.chat_ai.api.chat.*).
 */
frappe.provide("chat_ai.sidebar");
frappe.provide("chat_ai.libs");

const CAI_API = "zatgo_core.chat_ai.api.chat.";
const CAI_VENDOR = "/assets/zatgo_core/chat_ai/js/vendor/";

/* ---------------------------------------------------------------- transport */

/**
 * POST a whitelisted method. Resolves with the method's return value (the
 * {ok, data, ...} envelope); throws {status, message, code, network} for
 * transport / HTTP failures so callers can tell "the connection broke" from "the
 * server said no".
 */
chat_ai.api = async function (method, args, opts) {
	const o = opts || {};
	const body = new URLSearchParams();
	Object.keys(args || {}).forEach((k) => {
		const v = args[k];
		if (v === undefined || v === null) return;
		body.append(k, typeof v === "object" ? JSON.stringify(v) : String(v));
	});
	let res;
	try {
		res = await fetch("/api/method/" + (method.indexOf(".") < 0 ? CAI_API + method : method), {
			method: "POST",
			credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" },
			body,
			signal: o.signal,
		});
	} catch (e) {
		const err = new Error(e && e.message ? e.message : "network");
		err.name = "TypeError";
		err.status = 0;
		err.network = true;
		throw err;
	}
	let json = null;
	try {
		json = await res.json();
	} catch (e) {
		json = null;
	}
	if (!res.ok) {
		const err = new Error(chat_ai.api.serverMessage(json) || res.statusText || "HTTP " + res.status);
		err.status = res.status;
		err.code = res.status === 403 ? "forbidden" : res.status === 429 ? "rate_limited" : "";
		err.network = chat_ai.logic.isNetworkError({ status: res.status });
		throw err;
	}
	return json ? json.message : null;
};

/** Frappe wraps msgprint/throw text in _server_messages (JSON of JSON). */
chat_ai.api.serverMessage = function (json) {
	try {
		if (!json || !json._server_messages) return "";
		const list = JSON.parse(json._server_messages);
		return list
			.map((m) => {
				try {
					return JSON.parse(m).message;
				} catch (e) {
					return String(m);
				}
			})
			.join(" ")
			.replace(/<[^>]*>/g, "")
			.slice(0, 300);
	} catch (e) {
		return "";
	}
};

/* ------------------------------------------------------------ vendor loading */

/* The sidebar script is served with ?v=<content hash> (services/ui_apps.py asset_url); the lazily
 * loaded libraries reuse it, so one deploy invalidates everything together. */
const CAI_VER = (() => {
	const m = document.currentScript && /[?&]v=([\w-]+)/.exec(document.currentScript.src || "");
	return m ? m[1] : "";
})();

chat_ai.libs.load = function (file) {
	return new Promise((resolve, reject) => {
		const s = document.createElement("script");
		s.src = CAI_VENDOR + file + (CAI_VER ? "?v=" + CAI_VER : "");
		s.async = false;
		s.onload = () => resolve(true);
		s.onerror = () => reject(new Error("failed to load " + file));
		document.head.appendChild(s);
	});
};

/** marked + DOMPurify + highlight.js load once, on first mount; KaTeX only when math appears. */
chat_ai.libs.ensure = function () {
	if (chat_ai.libs._p) return chat_ai.libs._p;
	chat_ai.libs._p = Promise.all(["marked.umd.js", "purify.min.js", "highlight.min.js"].map(chat_ai.libs.load))
		.then(() => !!(window.marked && window.DOMPurify))
		.catch(() => false); // rendering falls back to escaped plain text
	return chat_ai.libs._p;
};

chat_ai.libs.ensureKatex = function () {
	if (window.katex) return Promise.resolve(true);
	if (!chat_ai.libs._k) {
		chat_ai.libs._k = chat_ai.libs.load("katex.min.js").then(() => !!window.katex).catch(() => false);
	}
	return chat_ai.libs._k;
};

/* ------------------------------------------------------------------- shell */

chat_ai.sidebar = {
	app: null,
	root: null,

	async init() {
		if (window.chat_ai_sidebar_ready) return;
		window.chat_ai_sidebar_ready = true;

		if (!document.getElementById("cai-root")) {
			const root = document.createElement("div");
			root.id = "cai-root";
			document.body.appendChild(root);
		}
		this.root = document.getElementById("cai-root");
		this.app = await chat_ai.vue.mount(this.root, chat_ai.sidebar.AppOptions);
		this.registerSearch();
	},

	/** Awesome bar: typing "zatgo ai" or "zai" offers to open the assistant. */
	registerSearch() {
		if (!(frappe.search && frappe.search.utils && frappe.search.utils.make_function_searchable)) return;
		const open = () => chat_ai.sidebar._vm && chat_ai.sidebar._vm.toggle(true);
		["ZatGo AI", "ZAI", "ZatGo AI assistant chat"].forEach((label, i) =>
			frappe.search.utils.make_function_searchable(open, i === 2 ? label : "Open " + label)
		);
	},
};

chat_ai.sidebar.AppOptions = {
	name: "ChatAISidebar",
	data() {
		const savedLang = localStorage.getItem("chat_ai_lang") || "en";
		return {
			open: localStorage.getItem("chat_ai_open") === "1",
			session: null,
			mode: "ERP Assistant",
			language: savedLang,
			languages: [
				{ code: "en", label: "English", native: "English", bcp47: "en-US", dir: "ltr" },
				{ code: "ar", label: "Arabic", native: "العربية", bcp47: "ar-SA", dir: "rtl" },
				{ code: "ml", label: "Malayalam", native: "മലയാളം", bcp47: "ml-IN", dir: "ltr" },
			],
			messages: [],
			hasMore: false,
			loadingOlder: false,
			loadingSession: false,
			historyError: false,
			atBottom: true,
			input: "",
			progress: "",
			busy: false,
			stopping: false,
			announce: "",
			// composer
			files: [],
			dragging: false,
			models: [],
			routing: false,
			features: { file_upload: true, vision: true, web_search: false, streaming: true },
			maxUploadMb: 15,
			selectedModel: localStorage.getItem("chat_ai_model") || "",
			webOn: localStorage.getItem("chat_ai_web") !== "0",
			modelMenuOpen: false,
			// voice
			listening: false,
			speakingId: null,
			commands: [],
			paletteOpen: false,
			paletteIndex: 0,
			pending: null,
			enableVoiceIn: true,
			enableVoiceOut: true,
			autoSpeak: false,
			ttsEngine: "Voicebox",
			voiceboxUrl: "http://127.0.0.1:17493",
			voiceboxProfile: "",
			voiceboxEngine: "",
			voiceboxViaServer: false,
			recognition: null,
			liveTranscript: "",
			voicesReady: false,
			// sessions / artifacts / overlays
			sessions: [],
			sessionQuery: "",
			searching: false,
			showSessions: false,
			showArtifacts: false,
			artifacts: [],
			sessionPinned: false,
			menuOpen: false,
			helpOpen: false,
			dlg: null,
			editing: null,
			mdVersion: 0,
			mdReady: false,
			expanded: localStorage.getItem("chat_ai_wide") === "1",
		};
	},
	computed: {
		ui() {
			return chat_ai.i18n.strings(this.language);
		},
		dir() {
			const meta = this.languages.find((l) => l.code === this.language);
			return (meta && meta.dir) || "ltr";
		},
		bcp47() {
			const meta = this.languages.find((l) => l.code === this.language);
			return (meta && meta.bcp47) || "en-US";
		},
		sttLang() {
			/* Prefer browser locale for English; fixed locales for ar/ml. */
			if (this.language === "en") {
				const nav = (navigator.language || "").toLowerCase();
				if (nav.startsWith("en")) return navigator.language;
				return "en-US";
			}
			if (this.language === "ar") return "ar-SA";
			if (this.language === "ml") return "ml-IN";
			return this.bcp47;
		},
		paletteItems() {
			if (!this.input.startsWith("/") || /\s/.test(this.input.trim().slice(1))) return [];
			const q = this.input.slice(1).toLowerCase();
			return (this.commands || []).filter(
				(c) => !q || (c.name || "").toLowerCase().startsWith(q) || (c.label || "").toLowerCase().includes(q)
			);
		},
		voiceAvailable() {
			return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
		},
		ttsAvailable() {
			if (this.ttsEngine === "Voicebox") return true;
			return !!(window.speechSynthesis && window.SpeechSynthesisUtterance);
		},
		groupedSessions() {
			return chat_ai.logic.groupSessions(this.sessions);
		},
		sessionTitle() {
			const s = this.sessions.find((x) => x.name === this.session);
			return (s && s.title) || this.ui.untitled;
		},
		uploading() {
			return this.files.some((f) => f.status === "uploading");
		},
		readyFiles() {
			return this.files.filter((f) => f.status === "ready" || f.status === "processing");
		},
		canSend() {
			return !this.busy && !this.uploading && !!((this.input || "").trim() || this.readyFiles.length);
		},
		acceptTypes() {
			return chat_ai.logic.acceptAttr({ vision: this.features.vision });
		},
		currentModelLabel() {
			if (!this.selectedModel) return this.routing ? this.ui.modelAuto : this.ui.modelDefault;
			return this.selectedModel;
		},
		showModelPicker() {
			return this.models.length > 1 || this.routing;
		},
		shortcuts() {
			return [
				[this.ui.kbSend, "Enter"],
				[this.ui.kbNewline, "Shift+Enter"],
				[this.ui.kbToggle, "Ctrl/Cmd+Shift+J"],
				[this.ui.kbSearch, "Ctrl/Cmd+K"],
				[this.ui.kbNew, "Ctrl/Cmd+Shift+O"],
				[this.ui.kbStop, "Esc"],
				[this.ui.kbFocus, "/"],
				[this.ui.kbHelp, "?"],
			];
		},
	},
	watch: {
		input() {
			this.paletteOpen = this.paletteItems.length > 0;
			this.paletteIndex = 0;
		},
		language() {
			this.mdVersion += 1;
			if (this.listening) {
				this.stopListening();
				this.$nextTick(() => this.startListening());
			}
		},
		selectedModel(v) {
			try {
				localStorage.setItem("chat_ai_model", v || "");
			} catch (e) {
				/* storage unavailable */
			}
		},
		webOn(v) {
			try {
				localStorage.setItem("chat_ai_web", v ? "1" : "0");
			} catch (e) {
				/* storage unavailable */
			}
		},
		sessionQuery() {
			clearTimeout(this._searchTimer);
			this._searchTimer = setTimeout(() => this.refreshSessions(), 250);
		},
	},
	async mounted() {
		chat_ai.sidebar._vm = this;
		this._htmlCache = new Map();
		this._turn = null;
		this._onKey = (e) => this.onGlobalKey(e);
		document.addEventListener("keydown", this._onKey);
		this.bindRealtime();
		this.bindLayout();
		this.bindViewport();
		this.warmVoices();
		this.updateLayoutOffset();
		this.setupMarkdown();
		await this.loadLocale();
		this.loadCommands();
		this.loadModels();
		await this.refreshSessions();
		if (this.open && !this.session) {
			if (this.sessions.length) await this.openSession(this.sessions[0].name);
			else await this.newSession();
		}
	},
	beforeUnmount() {
		document.removeEventListener("keydown", this._onKey);
		this.unbindLayout();
		this.unbindViewport();
		this.stopListening();
		this.stopSpeaking();
		this.files.forEach((f) => f.thumb && URL.revokeObjectURL(f.thumb));
		clearTimeout(this._searchTimer);
		this._flushPending = false;
		if (this._raf) cancelAnimationFrame(this._raf);
		clearTimeout(this._flushTimer);
	},
	methods: {
		/* ------------------------------------------------------------ helpers */
		t(key, vars) {
			return chat_ai.i18n.fmt(this.ui[key] != null ? this.ui[key] : key, vars);
		},
		L() {
			return chat_ai.logic;
		},
		copyText(text) {
			const t = String(text || "");
			if (!t) return;
			const done = () => frappe.show_alert({ message: this.ui.copied, indicator: "green" });
			if (navigator.clipboard && navigator.clipboard.writeText) {
				navigator.clipboard.writeText(t).then(done).catch(() => {
					frappe.utils.copy_to_clipboard(t);
					done();
				});
			} else {
				frappe.utils.copy_to_clipboard(t);
				done();
			}
		},
		download(filename, text, mime) {
			const url = URL.createObjectURL(new Blob([text], { type: mime || "text/plain;charset=utf-8" }));
			const a = document.createElement("a");
			a.href = url;
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
			setTimeout(() => URL.revokeObjectURL(url), 2000);
		},
		focusInput() {
			this.$nextTick(() => {
				const el = this.$refs.input;
				if (el) el.focus();
			});
		},
		msgById(id) {
			return this.messages.find((m) => m.id === id);
		},
		panelEl() {
			return this.$refs.panel || null;
		},

		/* ----------------------------------------------------------- markdown */
		setupMarkdown() {
			this._md = chat_ai.createMarkdown({ libs: {}, window });
			chat_ai.libs.ensure().then((ok) => {
				if (!ok) return;
				this._md = chat_ai.createMarkdown({
					libs: { marked: window.marked, DOMPurify: window.DOMPurify, hljs: window.hljs, katex: window.katex },
					window,
				});
				this._htmlCache.clear();
				this.mdReady = this._md.ready;
				this.mdVersion += 1;
			});
		},
		ensureKatex() {
			if (this._katexStarted) return;
			this._katexStarted = true;
			chat_ai.libs.ensureKatex().then((ok) => {
				if (!ok) return;
				this.setupMarkdown();
			});
		},
		/** Sanitised HTML for an assistant message (cached per message and text). */
		msgHtml(msg) {
			void this.mdVersion;
			const key = [msg.text.length, (msg.sources || []).length, this.mdVersion, this.language].join(":");
			const hit = this._htmlCache.get(msg.id);
			if (hit && hit.key === key && hit.text === msg.text) return hit.html;
			const r = this._md.render(msg.text, {
				sources: msg.sources || [],
				labels: {
					copy: this.ui.copyCode,
					download: this.ui.downloadCode,
					code: this.ui.code,
					source: this.ui.source,
				},
			});
			if (r.needsMath) this.ensureKatex();
			this._htmlCache.set(msg.id, { key, text: msg.text, html: r.html });
			if (this._htmlCache.size > 400) this._htmlCache.delete(this._htmlCache.keys().next().value);
			return r.html;
		},
		/** Clicks inside rendered answers: code-block buttons and citation markers. */
		onMessageClick(e, msg) {
			const target = e.target;
			if (!target || !target.closest) return;
			const cite = target.closest("a[data-cite]");
			if (cite) {
				e.preventDefault(); // never let #cai-src-n reach Frappe's hash router...
				e.stopPropagation(); // ...nor its document-level link handler (it would still rewrite the URL)
				const n = parseInt(cite.getAttribute("data-cite"), 10);
				msg.srcOpen = n;
				this.$nextTick(() => {
					const el = document.getElementById(`cai-src-${msg.id}-${n}`);
					if (el) {
						el.scrollIntoView({ block: "nearest" });
						el.classList.add("cai-source--flash");
						setTimeout(() => el.classList.remove("cai-source--flash"), 1400);
					}
				});
				return;
			}
			const btn = target.closest("button[data-act]");
			if (!btn) return;
			const block = btn.closest(".cai-md-codeblock");
			const code = block && block.querySelector("pre code");
			if (!code) return;
			const text = code.textContent || "";
			if (btn.getAttribute("data-act") === "copy") this.copyText(text);
			else this.download(this.L().codeFilename(block.getAttribute("data-lang")), text);
		},

		/* -------------------------------------------------------------- panel */
		toggle(force) {
			this.open = typeof force === "boolean" ? force : !this.open;
			try {
				localStorage.setItem("chat_ai_open", this.open ? "1" : "0");
			} catch (e) {
				/* storage unavailable */
			}
			this.$nextTick(() => this.updateLayoutOffset());
			if (this.open && !this.session) {
				if (this.sessions.length) this.openSession(this.sessions[0].name);
				else this.newSession();
			}
			if (this.open) {
				this._returnFocus = document.activeElement;
				this.focusInput();
			} else {
				this.stopListening();
				this.closeOverlays();
				if (this._returnFocus && this._returnFocus.focus) this._returnFocus.focus();
			}
		},
		toggleWide() {
			this.expanded = !this.expanded;
			localStorage.setItem("chat_ai_wide", this.expanded ? "1" : "0");
		},
		openScheduledTasks() {
			this.menuOpen = false;
			frappe.set_route("List", "AI Scheduled Task");
		},
		closeOverlays() {
			this.menuOpen = false;
			this.helpOpen = false;
			this.modelMenuOpen = false;
			this.showArtifacts = false;
			this.showSessions = false;
			if (this.dlg) this.closeDialog();
		},
		hasOverlay() {
			return !!(this.dlg || this.menuOpen || this.helpOpen || this.modelMenuOpen || this.showSessions || this.showArtifacts);
		},
		bindViewport() {
			/* Mobile keyboards shrink the visual viewport, not the layout viewport. */
			if (!window.visualViewport) return;
			this._onVV = () => {
				const vv = window.visualViewport;
				const shell = this.$el;
				if (shell && shell.style) shell.style.setProperty("--cai-vvh", `${Math.round(vv.height)}px`);
			};
			window.visualViewport.addEventListener("resize", this._onVV);
			window.visualViewport.addEventListener("scroll", this._onVV);
			this._onVV();
		},
		unbindViewport() {
			if (window.visualViewport && this._onVV) {
				window.visualViewport.removeEventListener("resize", this._onVV);
				window.visualViewport.removeEventListener("scroll", this._onVV);
			}
		},
		onGlobalKey(e) {
			const panel = this.panelEl();
			const active = document.activeElement;
			const inPanel = !!(panel && active && panel.contains(active));
			const typing = !!(
				active && (/^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName) || active.isContentEditable)
			);
			const action = this.L().matchShortcut(e, {
				open: this.open,
				inPanel,
				typing,
				overlay: this.hasOverlay(),
				busy: this.busy,
				frappeModal: !!document.querySelector(".modal.show"),
			});
			if (!action) return;
			e.preventDefault();
			switch (action) {
				case "toggle":
					this.toggle();
					break;
				case "close-overlay":
					this.closeOverlays();
					break;
				case "stop":
					this.stopGeneration();
					break;
				case "close":
					this.toggle(false);
					break;
				case "focus-search":
					this.showSessions = true;
					this.$nextTick(() => this.$refs.search && this.$refs.search.focus());
					break;
				case "new-chat":
					this.newSession();
					break;
				case "help":
					this.helpOpen = true;
					break;
				case "focus-input":
					this.focusInput();
					break;
			}
		},

		/* ------------------------------------------------------------ dialogs */
		openDialog(dlg) {
			this._dlgReturn = document.activeElement;
			this.dlg = Object.assign({ value: "", danger: false, input: false, textarea: false, note: "" }, dlg);
			this.$nextTick(() => {
				const root = this.$refs.dialog;
				const field = root && root.querySelector("input, textarea");
				const first = field || (root && root.querySelector("button"));
				if (first) first.focus();
			});
		},
		closeDialog() {
			this.dlg = null;
			const back = this._dlgReturn;
			this._dlgReturn = null;
			if (back && back.focus && document.contains(back)) back.focus();
		},
		async dialogOk() {
			const d = this.dlg;
			if (!d) return;
			const value = d.value;
			this.closeDialog();
			if (d.onOk) await d.onOk(value);
		},
		dialogKeydown(e) {
			if (e.key === "Escape") {
				e.stopPropagation();
				this.closeDialog();
				return;
			}
			if (e.key === "Enter" && e.target.tagName === "INPUT") {
				e.preventDefault();
				this.dialogOk();
				return;
			}
			if (e.key !== "Tab") return;
			const nodes = this.$refs.dialog.querySelectorAll("button, input, textarea");
			if (!nodes.length) return;
			const first = nodes[0];
			const last = nodes[nodes.length - 1];
			if (e.shiftKey && document.activeElement === first) {
				e.preventDefault();
				last.focus();
			} else if (!e.shiftKey && document.activeElement === last) {
				e.preventDefault();
				first.focus();
			}
		},

		/* ------------------------------------------------------------- models */
		async loadModels() {
			try {
				const r = await chat_ai.api("list_models", {});
				if (!(r && r.ok)) return;
				const d = r.data || {};
				this.models = d.models || [];
				this.routing = !!d.routing;
				this.features = Object.assign(this.features, d.features || {});
				this.maxUploadMb = d.max_upload_mb || this.maxUploadMb;
				if (this.selectedModel && !this.models.some((m) => m.name === this.selectedModel)) {
					this.selectedModel = "";
				}
			} catch (e) {
				/* feature probing is best effort; the composer works without it */
			}
		},
		slotLabel(slot) {
			const map = {
				balanced: "slotBalanced", fast: "slotFast", reasoning: "slotReasoning",
				vision: "slotVision", coding: "slotCoding", fallback: "slotFallback",
			};
			return this.ui[map[slot]] || slot;
		},
		pickModel(name) {
			this.selectedModel = name;
			this.modelMenuOpen = false;
			this.focusInput();
		},

		/* ----------------------------------------------------------- sessions */
		async newSession() {
			try {
				const r = await chat_ai.api("new_session", { language: this.language });
				if (r && r.ok) {
					this.resetConversation(r.data.name);
					this.showSessions = false;
					await this.refreshSessions();
					this.focusInput();
				}
			} catch (e) {
				this.toastError(e);
			}
		},
		resetConversation(session) {
			this._turn = null;
			this.session = session;
			this.messages = [];
			this.hasMore = false;
			this.progress = "";
			this.pending = null;
			this.sessionPinned = false;
			this.busy = false;
			this.stopping = false;
			this.historyError = false;
			this.editing = null;
			this._htmlCache.clear();
			this.clearFiles();
			this.stopSpeaking();
		},
		async refreshSessions() {
			const q = (this.sessionQuery || "").trim();
			this.searching = !!q;
			try {
				const r = q
					? await chat_ai.api("search_sessions", { query: q })
					: await chat_ai.api("list_sessions", { status: "Active" });
				if (r && r.ok && (this.sessionQuery || "").trim() === q) this.sessions = r.data || [];
			} catch (e) {
				if (!q) this.sessions = [];
			} finally {
				if ((this.sessionQuery || "").trim() === q) this.searching = false;
			}
		},
		async openSession(name) {
			if (!name) return;
			if (name === this.session && this.messages.length) {
				this.showSessions = false;
				return;
			}
			const meta = (this.sessions || []).find((s) => s.name === name);
			this.resetConversation(name);
			this.showSessions = false;
			if (meta) {
				this.mode = meta.assistant_mode || this.mode;
				this.sessionPinned = !!meta.is_pinned;
			}
			await this.loadHistory();
			this.loadArtifacts();
		},
		async loadHistory() {
			this.loadingSession = true;
			this.historyError = false;
			const session = this.session;
			try {
				const r = await chat_ai.api("history", { session, limit: 50 });
				if (session !== this.session) return;
				if (!(r && r.ok)) throw new Error("history");
				const rows = (r.data || []).map((row) => this.L().rowToMessage(row));
				this.messages = this.L().mergeHistory(this.messages, rows, "replace");
				this.hasMore = !!r.has_more;
				this.$nextTick(() => this.scrollToBottom(true));
			} catch (e) {
				this.historyError = true;
			} finally {
				this.loadingSession = false;
			}
		},
		async loadOlder() {
			if (this.loadingOlder || !this.hasMore || !this.session) return;
			const cursor = this.L().oldestCursor(this.messages);
			if (!cursor) return;
			this.loadingOlder = true;
			const box = this.$refs.messages;
			const before = box ? box.scrollHeight - box.scrollTop : 0;
			try {
				const r = await chat_ai.api("history", { session: this.session, limit: 50, before: cursor });
				if (!(r && r.ok)) return;
				const rows = (r.data || []).map((row) => this.L().rowToMessage(row));
				this.messages = this.L().mergeHistory(this.messages, rows, "prepend");
				this.hasMore = !!r.has_more;
				this.$nextTick(() => {
					if (box) box.scrollTop = box.scrollHeight - before; // keep the reader where they were
				});
			} catch (e) {
				this.toastError(e);
			} finally {
				this.loadingOlder = false;
			}
		},
		/** After a turn, learn the server ids of the exchange (needed for edit / delete). */
		async adoptIds() {
			if (!this.session) return;
			const session = this.session;
			try {
				const r = await chat_ai.api("history", { session, limit: 4 });
				if (!(r && r.ok) || session !== this.session) return;
				const rows = (r.data || []).slice().reverse();
				const mine = this.messages.filter((m) => !m.serverId);
				rows.forEach((row) => {
					const role = row.role === "user" ? "user" : "assistant";
					const idx = mine.map((m) => m.role).lastIndexOf(role);
					if (idx >= 0 && !this.messages.some((m) => m.serverId === row.name)) {
						const m = mine.splice(idx, 1)[0];
						const live = this.msgById(m.id);
						if (live) {
							live.serverId = row.name;
							live.creation = row.creation || "";
							live.persisted = true;
						}
					}
				});
			} catch (e) {
				/* ids are only needed for edit/delete; the next history load restores them */
			}
		},
		renameSession() {
			if (!this.session) return;
			this.menuOpen = false;
			this.openDialog({
				title: this.ui.renameTitle,
				label: this.ui.renameLabel,
				input: true,
				value: this.sessionTitle,
				okText: this.ui.save,
				onOk: async (title) => {
					if (!(title || "").trim()) return;
					await chat_ai.api("rename", { session: this.session, title: title.trim() });
					this.refreshSessions();
				},
			});
		},
		async togglePin() {
			if (!this.session) return;
			this.menuOpen = false;
			const next = this.sessionPinned ? 0 : 1;
			await chat_ai.api("pin", { session: this.session, pinned: next });
			this.sessionPinned = !!next;
			this.refreshSessions();
		},
		archiveSession() {
			this.menuOpen = false;
			this.openDialog({
				title: this.ui.archiveTitle,
				body: this.ui.archiveBody,
				okText: this.ui.archive,
				onOk: async () => {
					await chat_ai.api("archive", { session: this.session });
					await this.afterSessionGone();
				},
			});
		},
		deleteSession() {
			this.menuOpen = false;
			this.openDialog({
				title: this.ui.deleteChatTitle,
				body: this.ui.deleteChatBody,
				okText: this.ui.delete,
				danger: true,
				onOk: async () => {
					await chat_ai.api("delete_session", { session: this.session });
					await this.afterSessionGone();
				},
			});
		},
		clearSession() {
			this.menuOpen = false;
			this.openDialog({
				title: this.ui.clearTitle,
				body: this.ui.clearBody,
				okText: this.ui.clear,
				danger: true,
				onOk: async () => {
					await chat_ai.api("clear", { session: this.session });
					this.messages = [];
					this.hasMore = false;
					this.pending = null;
				},
			});
		},
		async afterSessionGone() {
			const gone = this.session;
			this.resetConversation(null);
			await this.refreshSessions();
			const next = this.sessions.find((s) => s.name !== gone);
			if (next) await this.openSession(next.name);
			else await this.newSession();
		},
		async exportMarkdown(mode) {
			this.menuOpen = false;
			try {
				const r = await chat_ai.api("export_session", { session: this.session });
				if (!(r && r.ok)) throw new Error("export");
				const d = r.data || {};
				if (mode === "copy") this.copyText(d.markdown);
				else this.download(this.L().exportFilename(d.title), d.markdown, "text/markdown;charset=utf-8");
			} catch (e) {
				this.toastError(e);
			}
		},
		async setLanguage(code) {
			this.language = code;
			try {
				localStorage.setItem("chat_ai_lang", code);
			} catch (e) {
				/* storage unavailable */
			}
			if (!this.session) return;
			try {
				await chat_ai.api("set_language", { session: this.session, language: code });
			} catch (e) {
				/* the choice still applies to the UI */
			}
		},

		/* ---------------------------------------------------------- artifacts */
		async loadArtifacts() {
			if (!this.session) {
				this.artifacts = [];
				return;
			}
			try {
				const r = await chat_ai.api("zatgo_core.chat_ai.api.platform.chat_artifacts", { session: this.session, limit: 40 });
				const list = (r && r.ok && r.data) || (r && r.data) || [];
				this.artifacts = Array.isArray(list) ? list : [];
			} catch (e) {
				this.artifacts = [];
			}
		},
		async openArtifact(name) {
			try {
				const r = await chat_ai.api("zatgo_core.chat_ai.api.platform.get_artifact", { name });
				const doc = (r && r.ok && r.data) || (r && r.data) || {};
				const body = typeof doc.content === "string" ? doc.content : JSON.stringify(doc.content || "", null, 2);
				this.showArtifacts = false;
				this.openDialog({
					title: doc.title || name,
					pre: String(body).slice(0, 20000),
					okText: this.ui.close,
					cancelText: this.ui.copy,
					onCancel: () => this.copyText(body),
					onOk: () => {},
				});
			} catch (e) {
				this.toastError(e);
			}
		},

		/* ----------------------------------------------------------- composer */
		clearFiles() {
			this.files.forEach((f) => f.thumb && URL.revokeObjectURL(f.thumb));
			this.files = [];
		},
		onPickFiles(e) {
			this.addFiles(Array.from(e.target.files || []));
			e.target.value = "";
		},
		onPaste(e) {
			const items = Array.from((e.clipboardData && e.clipboardData.files) || []);
			if (items.length) {
				e.preventDefault();
				this.addFiles(items);
			}
		},
		onDrop(e) {
			this.dragging = false;
			const items = Array.from((e.dataTransfer && e.dataTransfer.files) || []);
			if (items.length) this.addFiles(items);
		},
		onDragOver(e) {
			if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files")) {
				e.preventDefault();
				this.dragging = true;
			}
		},
		fileProblem(file) {
			const chk = this.L().clientFileCheck(file, {
				fileUpload: this.features.file_upload,
				vision: this.features.vision,
				maxMb: this.maxUploadMb,
			});
			if (chk.ok) return "";
			const map = {
				disabled: ["errFileDisabled", {}],
				type: ["errFileType", { name: file.name }],
				size: ["errFileSize", { name: file.name, mb: this.maxUploadMb }],
				empty: ["errFileEmpty", { name: file.name }],
				vision: ["errFileVision", { name: file.name }],
			};
			const m = map[chk.reason] || ["errGeneric", {}];
			return this.t(m[0], m[1]);
		},
		async addFiles(list) {
			for (const file of list) {
				if (this.files.length >= 5) {
					frappe.show_alert({ message: this.t("errFileLimit", { n: 5 }), indicator: "orange" });
					break;
				}
				const problem = this.fileProblem(file);
				if (problem) {
					frappe.show_alert({ message: problem, indicator: "orange" });
					continue;
				}
				const entry = {
					id: this.L().localId("f"),
					name: file.name,
					size: file.size,
					kind: this.L().FILE_TYPES[this.L().extOf(file.name)] || "",
					status: "uploading",
					progress: 0,
					server: "",
					error: "",
					thumb: file.type && file.type.startsWith("image/") ? URL.createObjectURL(file) : "",
				};
				this.files.push(entry);
				this.uploadFile(entry.id, file);
			}
		},
		async uploadFile(id, file) {
			const entry = () => this.files.find((f) => f.id === id);
			try {
				if (!this.session) await this.newSession();
				const fd = new FormData();
				fd.append("session", this.session);
				fd.append("file", file, file.name);
				const result = await new Promise((resolve, reject) => {
					const xhr = new XMLHttpRequest();
					xhr.open("POST", "/api/method/" + CAI_API + "upload");
					xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
					xhr.setRequestHeader("Accept", "application/json");
					xhr.upload.onprogress = (ev) => {
						const e = entry();
						if (e && ev.lengthComputable) e.progress = Math.round((ev.loaded / ev.total) * 100);
					};
					xhr.onerror = () => reject(new Error(this.ui.errNetwork));
					xhr.onload = () => {
						let json = null;
						try {
							json = JSON.parse(xhr.responseText);
						} catch (e) {
							json = null;
						}
						if (xhr.status >= 200 && xhr.status < 300 && json && json.message) resolve(json.message);
						else reject(new Error(chat_ai.api.serverMessage(json) || this.ui.errGeneric));
					};
					xhr.send(fd);
				});
				const e = entry();
				if (!e) return; // removed while uploading
				if (!result.ok) {
					e.status = "failed";
					e.error = result.error || this.ui.errGeneric;
					return;
				}
				e.server = result.data.name;
				e.status = result.data.status === "Failed" ? "failed" : result.data.status === "Ready" ? "ready" : "processing";
				e.error = result.data.error || "";
				e.progress = 100;
			} catch (err) {
				const e = entry();
				if (e) {
					e.status = "failed";
					e.error = err.message || this.ui.errGeneric;
				}
			}
		},
		async removeFile(f) {
			this.files = this.files.filter((x) => x.id !== f.id);
			if (f.thumb) URL.revokeObjectURL(f.thumb);
			if (f.server) {
				try {
					await chat_ai.api("delete_attachment", { attachment: f.server });
				} catch (e) {
					/* an orphaned file is removed with its conversation */
				}
			}
		},
		onKeydown(e) {
			if (this.paletteOpen && this.paletteItems.length) {
				if (e.key === "ArrowDown") {
					e.preventDefault();
					this.paletteIndex = (this.paletteIndex + 1) % this.paletteItems.length;
					return;
				}
				if (e.key === "ArrowUp") {
					e.preventDefault();
					this.paletteIndex = (this.paletteIndex - 1 + this.paletteItems.length) % this.paletteItems.length;
					return;
				}
				if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
					e.preventDefault();
					this.pickCommand(this.paletteItems[this.paletteIndex]);
					return;
				}
			}
			if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
				e.preventDefault();
				this.send();
			}
		},
		autoGrow() {
			const el = this.$refs.input;
			if (!el) return;
			el.style.height = "auto";
			el.style.height = Math.min(el.scrollHeight, 180) + "px";
		},
		pickCommand(cmd) {
			this.input = `/${cmd.name} `;
			this.paletteOpen = false;
			if (cmd.name === "help") this.showHelp();
			this.focusInput();
		},
		showHelp() {
			const lines = this.commands.map((c) => `/${c.name} — ${c.description || c.label || ""}`);
			const msg = this.L().emptyMessage("assistant", lines.join("\n") || "No commands available.");
			this.messages.push(msg);
			this.scrollToBottom(true);
		},
		isPlanApprovalText(text) {
			const t = (text || "").trim().toLowerCase();
			return ["ok", "yes", "confirm", "proceed", "continue", "go ahead", "y"].includes(t);
		},

		/* --------------------------------------------------------------- turns */
		async send() {
			if (!this.canSend) {
				if (this.uploading) frappe.show_alert({ message: this.ui.uploadWait, indicator: "orange" });
				return;
			}
			let text = (this.input || "").trim();
			this.stopListening();
			if (this.pending && this.pending.kind === "plan" && this.isPlanApprovalText(text)) {
				this.input = "";
				const m = this.L().emptyMessage("user", text);
				this.messages.push(m);
				await this.confirmPlan(true);
				return;
			}
			let command = null;
			if (text.startsWith("/")) {
				const parts = text.slice(1).split(/\s+/);
				command = parts.shift();
				text = parts.join(" ");
				if (command === "help") {
					this.showHelp();
					this.input = "";
					this.paletteOpen = false;
					return;
				}
			}
			const attachments = this.readyFiles.map((f) => ({ name: f.server, file_name: f.name, kind: f.kind }));
			const user = this.L().emptyMessage("user", command ? `/${command} ${text}`.trim() : text);
			user.attachments = attachments;
			this.messages.push(user);
			this.input = "";
			this.paletteOpen = false;
			this.$nextTick(() => this.autoGrow());
			const args = {
				message: text,
				command,
				attachments: attachments.map((a) => a.name),
				model: this.selectedModel || null,
				web: this.features.web_search ? (this.webOn ? 1 : 0) : null,
			};
			this.files.forEach((f) => f.thumb && URL.revokeObjectURL(f.thumb));
			this.files = [];
			await this.runTurn("send", args);
		},
		/**
		 * One request/response turn. kind: send | regenerate | edit | confirm.
		 * Streaming text arrives over realtime meanwhile; the response is authoritative.
		 */
		async runTurn(kind, args) {
			if (!this.session) await this.newSession();
			const L = this.L();
			const assistant = L.emptyMessage("assistant", "");
			assistant.status = "pending";
			assistant._retry = { kind, args };
			this.messages.push(assistant);
			const turn = {
				session: this.session,
				msgId: assistant.id,
				buffer: new L.StreamBuffer(),
				finalized: false,
				dirty: false,
			};
			this._turn = turn;
			this.busy = true;
			this.stopping = false;
			this.progress = this.ui.working;
			this.announce = this.ui.working;
			this.scrollToBottom(true);
			const common = { session: this.session, client_context: this.clientContext() };
			let payload = null;
			let failure = null;
			try {
				if (kind === "regenerate") {
					payload = await chat_ai.api("regenerate", { session: this.session, model: args.model, web: args.web });
				} else if (kind === "edit") {
					payload = await chat_ai.api("edit_message", {
						session: this.session, message: args.message_id, content: args.message, model: args.model, web: args.web,
					});
				} else {
					payload = await chat_ai.api("send", Object.assign({}, common, args));
				}
			} catch (e) {
				failure = e;
			}
			turn.finalized = true;
			this._flushPending = false;
			if (this._raf) {
				cancelAnimationFrame(this._raf);
				this._raf = 0;
			}
			clearTimeout(this._flushTimer);
			if (this._turn === turn) this._turn = null;
			const live = this.msgById(turn.msgId);
			if (turn.session !== this.session || !live) {
				this.busy = false; // the user moved to another conversation; nothing to render here
				return;
			}
			if (failure) await this.finishWithFailure(live, turn, failure);
			else if (!payload || !payload.ok) this.finishWithError(live, turn, this.L().errorFromPayload(payload));
			else this.finishWithAnswer(live, payload.data || {});
			this.busy = false;
			this.stopping = false;
			this.progress = "";
			this.scrollToBottom();
			this.refreshSessions();
			this.loadArtifacts();
			this.adoptIds();
		},
		finishWithAnswer(msg, data) {
			const L = this.L();
			msg.steps.forEach((st) => {
				if (st.status === "running") st.status = "done"; // the turn is over: nothing is still running
			});
			const cj = data.content_json || {};
			if (data.assistant_mode) this.mode = data.assistant_mode;
			msg.text = data.content || msg.text || "";
			msg.blocks = Array.isArray(cj.blocks) ? cj.blocks : [];
			msg.sources = L.normalizeSources(data.sources || cj.sources);
			msg.meta = data.meta || cj.meta || null;
			const interrupted = !!(msg.meta && msg.meta.interrupted);
			msg.status = interrupted ? "error" : "done";
			msg.error = interrupted ? { message: "", code: "interrupted", retryable: true } : null;
			msg.serverId = data.message || msg.serverId;
			msg.persisted = !!data.message;
			msg.needs_confirmation = !!(cj.needs_confirmation || data.needs_confirmation);
			msg.needs_plan_approval = !!(cj.needs_plan_approval || data.needs_plan_approval);
			msg.pending_plan = cj.pending_plan || data.pending_plan || [];
			msg.pending_assumptions = cj.pending_assumptions || data.pending_assumptions || [];
			msg.confirmation_token = cj.confirmation_token || data.confirmation_token || "";
			if (data.queued) {
				msg.status = "queued";
				msg.text = msg.text || this.ui.bgNotice;
			}
			if (msg.needs_confirmation) {
				this.pending = { kind: "tool", tool: cj.pending_tool, args: cj.pending_args, token: msg.confirmation_token };
			} else if (msg.needs_plan_approval) {
				this.pending = { kind: "plan", plan: msg.pending_plan, assumptions: msg.pending_assumptions, token: msg.confirmation_token };
			}
			this.announce = this.ui.replyReady;
			if (this.autoSpeak && this.enableVoiceOut && msg.text && msg.status === "done") this.speak(msg);
		},
		finishWithError(msg, turn, error) {
			msg.steps.forEach((st) => {
				if (st.status === "running") st.status = "failed";
			});
			msg.status = "error";
			msg.text = turn.buffer.flushAll() || msg.text; // what the user already saw stays visible
			msg.error = error;
			msg.error.partial = !!msg.text;
			this.announce = error.message || this.ui.errGeneric;
			if (error.code === "forbidden") this.loadHistory();
		},
		async finishWithFailure(msg, turn, err) {
			const network = this.L().isNetworkError(err) || err.network;
			if (!network) {
				this.finishWithError(msg, turn, {
					message: err.message || "",
					code: err.code || "internal",
					retryable: false,
				});
				return;
			}
			// The connection broke while the server may have finished: look before assuming failure.
			msg.status = "pending";
			msg.text = turn.buffer.flushAll() || msg.text;
			this.progress = this.ui.errNetwork;
			await new Promise((r) => setTimeout(r, 1500));
			const before = this.messages.filter((m) => m.serverId).length;
			await this.loadHistory();
			const after = this.messages.filter((m) => m.serverId).length;
			if (after > before) return; // the answer had arrived: history now shows it
			const live = this.msgById(msg.id) || this.messages[this.messages.length - 1];
			if (live && !live.serverId) {
				live.status = "error";
				live.error = { message: this.ui.errNetworkFinal, code: "network", retryable: true, reload: true };
			}
		},
		stopGeneration() {
			if (!this.busy || this.stopping) return;
			this.stopping = true;
			this.progress = this.ui.stopping;
			if (this.session) chat_ai.api("cancel", { session: this.session }).catch(() => {});
			// The server finishes the turn with what was generated and the response replaces this state.
		},
		retryMessage(msg) {
			const retry = msg._retry;
			const idx = this.messages.findIndex((m) => m.id === msg.id);
			if (idx < 0) return;
			const prev = this.messages[idx - 1];
			const persisted = !!(prev && prev.serverId);
			if (msg.error && msg.error.reload) {
				this.loadHistory();
				return;
			}
			this.messages.splice(idx, 1);
			if (persisted) {
				this.runTurn("regenerate", { model: this.selectedModel || null, web: this.features.web_search ? (this.webOn ? 1 : 0) : null });
			} else if (retry) {
				this.runTurn(retry.kind === "send" ? "send" : "regenerate", retry.args);
			}
		},
		regenerate(msg) {
			if (this.busy || !this.L().canRegenerate(this.messages, msg)) return;
			this.messages = this.messages.filter((m) => m.id !== msg.id);
			this.runTurn("regenerate", { model: this.selectedModel || null, web: this.features.web_search ? (this.webOn ? 1 : 0) : null });
		},
		startEdit(msg) {
			if (this.busy || !msg.serverId) return;
			this.editing = { id: msg.id, text: msg.text };
			this.$nextTick(() => {
				const el = this.$refs.editBox && (Array.isArray(this.$refs.editBox) ? this.$refs.editBox[0] : this.$refs.editBox);
				if (el) {
					el.focus();
					el.setSelectionRange(el.value.length, el.value.length);
				}
			});
		},
		cancelEdit() {
			this.editing = null;
		},
		async saveEdit(msg) {
			const text = (this.editing && this.editing.text || "").trim();
			if (!text || this.busy) return;
			const idx = this.messages.findIndex((m) => m.id === msg.id);
			const serverId = msg.serverId;
			const attachments = msg.attachments;
			this.editing = null;
			this.messages = this.L().truncateAfter(this.messages, idx - 1);
			const user = this.L().emptyMessage("user", text);
			user.attachments = attachments;
			this.messages.push(user);
			await this.runTurn("edit", {
				message_id: serverId, message: text, model: this.selectedModel || null,
				web: this.features.web_search ? (this.webOn ? 1 : 0) : null,
			});
		},
		deleteMessage(msg) {
			if (this.busy) return;
			if (!msg.serverId) {
				this.messages = this.messages.filter((m) => m.id !== msg.id);
				return;
			}
			this.openDialog({
				title: this.ui.deleteMsgTitle,
				body: this.ui.deleteMsgBody,
				okText: this.ui.delete,
				danger: true,
				onOk: async () => {
					try {
						await chat_ai.api("delete_message", { session: this.session, message: msg.serverId });
						this.messages = this.messages.filter((m) => m.id !== msg.id);
					} catch (e) {
						this.toastError(e);
					}
				},
			});
		},
		async confirmPending(yes, msg) {
			if (msg) msg.confirmState = yes ? "approved" : "declined";
			if (!yes) {
				this.pending = null;
				this.messages.push(this.L().emptyMessage("assistant", this.ui.cancelled));
				return;
			}
			if (!this.pending || this.pending.kind !== "tool") return;
			const p = this.pending;
			this.pending = null;
			await this.runTurn("send", {
				message: "", confirmed: 1, pending_tool: p.tool, pending_args: p.args, confirmation_token: p.token,
			});
		},
		async confirmPlan(yes, msg) {
			if (msg) msg.confirmState = yes ? "approved" : "declined";
			if (!yes) {
				this.pending = null;
				this.messages.push(this.L().emptyMessage("assistant", this.ui.cancelled));
				return;
			}
			if (!this.pending || this.pending.kind !== "plan") return;
			const p = this.pending;
			this.pending = null;
			await this.runTurn("send", { message: "OK", plan_confirmed: 1, confirmation_token: p.token });
		},
		openLink(dt, nm) {
			frappe.set_route("Form", dt, nm);
		},
		toastError(e) {
			frappe.show_alert({ message: (e && e.message) || this.ui.errGeneric, indicator: "red" });
		},

		/* ------------------------------------------------------------ scrolling */
		onScroll() {
			const box = this.$refs.messages;
			if (!box) return;
			this.atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
			if (box.scrollTop < 60 && this.hasMore && !this.loadingOlder) this.loadOlder();
		},
		scrollToBottom(force) {
			this.$nextTick(() => {
				const box = this.$refs.messages;
				if (!box) return;
				if (force || this.atBottom) {
					box.scrollTop = box.scrollHeight;
					this.atBottom = true;
				}
			});
		},

		/* ------------------------------------------------------------- realtime */
		scheduleFlush() {
			if (this._flushPending) return;
			this._flushPending = true;
			// One render per frame for smoothness, but a hidden tab pauses requestAnimationFrame, so a
			// short timer races it: whichever fires first flushes, the other is cancelled.
			const run = () => {
				if (!this._flushPending) return;
				this._flushPending = false;
				if (this._raf) cancelAnimationFrame(this._raf);
				clearTimeout(this._flushTimer);
				this._raf = 0;
				this.flushStream();
			};
			this._raf = requestAnimationFrame(run);
			this._flushTimer = setTimeout(run, 80);
		},
		flushStream() {
			const t = this._turn;
			if (!t || t.finalized) return;
			const changed = t.buffer.take();
			if (changed || t.dirty) {
				const m = this.msgById(t.msgId);
				if (m) {
					m.text = t.buffer.text;
					m.status = "streaming";
				}
				t.dirty = false;
				this.scrollToBottom();
			}
		},
		addStep(msg, label, tool) {
			if (!msg || !label) return;
			const last = msg.steps[msg.steps.length - 1];
			if (last && last.label === label) return;
			if (last) last.status = last.status === "failed" ? "failed" : "done";
			msg.steps.push({ label, tool: tool || "", status: "running" });
			if (msg.steps.length > 40) msg.steps.shift();
		},
		bindRealtime() {
			if (!frappe.realtime || !frappe.realtime.on) return;
			frappe.realtime.on("chat_ai:progress", (data) => {
				const t = this._turn;
				if (!data || !this.L().eventBelongsToTurn(data, t)) return;
				const label = this.ui["stage_" + data.stage] || data.label || data.stage || "";
				this.progress = label;
				this.addStep(this.msgById(t.msgId), data.tool ? this.t("toolRunning", { tool: data.tool }) : label, data.tool);
			});
			frappe.realtime.on("chat_ai:stream", (data) => {
				const t = this._turn;
				if (!data || !this.L().eventBelongsToTurn(data, t)) return;
				t.buffer.push(data);
				if (data.reset) t.dirty = true;
				this.scheduleFlush();
			});
			frappe.realtime.on("chat_ai:event", (evt) => {
				const t = this._turn;
				if (!evt || !this.L().eventBelongsToTurn(evt, t)) return;
				const type = evt.type || "";
				const d = evt.data || {};
				// Text deltas come from chat_ai:stream only (this event mirrors them).
				if (type === "planning" || type === "thinking") this.progress = d.detail || this.ui.thinking;
				else if (type === "tool_started" || type === "tool_progress") {
					this.progress = d.detail || d.tool || type;
					this.addStep(this.msgById(t.msgId), this.t("toolRunning", { tool: d.tool || "" }), d.tool);
				} else if (type === "artifact_created") this.loadArtifacts();
				else if (type === "error") this.progress = d.message || this.ui.errGeneric;
			});
			frappe.realtime.on("chat_ai:notify", (data) => {
				if (data && data.message) frappe.show_alert({ message: data.message, indicator: "green" });
				if (this.session) this.loadHistory();
			});
		},


		/* --------------------------------------------------------- template helpers */
		grouped(msg) {
			return this.L().groupSources(msg.sources);
		},
		sourceTotal(msg) {
			return this.L().sourceCount(msg.sources);
		},
		stepsSummary(msg) {
			if (msg.status === "pending" || msg.status === "streaming") return this.ui.stepsRunning;
			return this.t("stepsCount", { n: msg.steps.length });
		},
		badge(msg) {
			return this.L().metaBadge(msg.meta);
		},
		badgeText(msg) {
			const b = this.badge(msg);
			if (!b) return "";
			return b.fallbackFrom
				? this.t("answeredFallback", { model: b.model, from: b.fallbackFrom })
				: this.t("answeredBy", { model: b.model });
		},
		routeLabel(route) {
			const map = {
				fast: "routeFast", reasoning: "routeReasoning", vision: "routeVision",
				coding: "routeCoding", balanced: "routeBalanced", manual: "routeManual",
			};
			return map[route] ? this.ui[map[route]] : "";
		},
		errorText(msg) {
			const e = msg.error || {};
			if (e.message) return e.message;
			return e.code === "interrupted" ? this.ui.interrupted : this.ui.errGeneric;
		},
		canRetryMsg(msg) {
			return !!(msg.error && (this.L().canRetry(msg.error) || msg.error.reload));
		},
		canConfigure(msg) {
			const code = msg.error && msg.error.code;
			const admin = frappe.user && (frappe.user.has_role("System Manager") || frappe.user.has_role("Chat AI Manager"));
			return !!admin && ["auth", "model_unavailable", "not_configured"].includes(code);
		},
		openSettings() {
			frappe.set_route("Form", "Chat AI Settings");
		},
		fileState(f) {
			if (f.status === "uploading") return `${this.ui.uploading} ${f.progress}%`;
			if (f.status === "processing") return this.ui.processing;
			if (f.status === "failed") return f.error || this.ui.failed;
			return this.L().humanSize(f.size);
		},
		attachmentLabel(a) {
			return a.file_name || a.name;
		},
		dialogCancel() {
			const d = this.dlg;
			if (d && d.onCancel) d.onCancel();
			else this.closeDialog();
		},
		tableCsv(data) {
			this.download("table.csv", "﻿" + this.L().tableToCsv(data), "text/csv;charset=utf-8");
		},
		parts(text) {
			return this.L().highlightParts(text, this.sessionQuery);
		},
		groupLabel(key) {
			const map = { pinned: "groupPinned", today: "groupToday", yesterday: "groupYesterday", week: "groupWeek", older: "groupOlder" };
			return this.ui[map[key]] || key;
		},
		lastAssistantId() {
			const list = this.messages;
			for (let i = list.length - 1; i >= 0; i--) if (list[i].role === "assistant") return list[i].id;
			return "";
		},

		/* ---- voice, layout and locale: carried over unchanged from the previous version ---- */
		warmVoices() {
			if (!window.speechSynthesis) return;
			const mark = () => {
				this.voicesReady = true;
			};
			window.speechSynthesis.getVoices();
			window.speechSynthesis.onvoiceschanged = mark;
			mark();
		},
		joinVoiceParts(...parts) {
			return parts
				.map((p) => (p || "").trim())
				.filter(Boolean)
				.join(" ")
				.replace(/\s+/g, " ")
				.trim();
		},
		pickBestAlternative(result) {
			let best = result[0];
			let bestScore = typeof best.confidence === "number" ? best.confidence : 0;
			for (let i = 1; i < result.length; i++) {
				const c = typeof result[i].confidence === "number" ? result[i].confidence : 0;
				if (c > bestScore) {
					best = result[i];
					bestScore = c;
				}
			}
			return { transcript: (best.transcript || "").trim(), confidence: bestScore };
		},
		/** Keep panel below navbar + form page-head so Save/Submit stay clickable. */
		updateLayoutOffset() {
			const shell = this.$el;
			if (!shell) return;
			let top = 0;
			const nav = document.querySelector(".navbar");
			if (nav) {
				const r = nav.getBoundingClientRect();
				top = Math.max(top, r.bottom);
			}
			const head = document.querySelector(".page-head");
			if (head) {
				const r = head.getBoundingClientRect();
				/* sticky page-head while near the top of the viewport */
				if (r.height > 0 && r.top < 160 && r.bottom > top) {
					top = Math.max(top, r.bottom);
				}
			}
			if (!top) {
				top = 48 + 52;
			}
			shell.style.setProperty("--cai-top", `${Math.ceil(top + 4)}px`);
		},
		bindLayout() {
			this._onLayout = () => this.updateLayoutOffset();
			window.addEventListener("resize", this._onLayout);
			window.addEventListener("scroll", this._onLayout, true);
			if (frappe.router && frappe.router.on) {
				frappe.router.on("change", this._onLayout);
			} else if (frappe.after_ajax) {
				/* fallback: remeasure after route paints */
			}
			$(document).on("page-change.chat_ai_layout form-load.chat_ai_layout", this._onLayout);
			this._layoutTimer = setInterval(() => this.updateLayoutOffset(), 1500);
		},
		unbindLayout() {
			if (this._onLayout) {
				window.removeEventListener("resize", this._onLayout);
				window.removeEventListener("scroll", this._onLayout, true);
				$(document).off(".chat_ai_layout");
			}
			if (this._layoutTimer) clearInterval(this._layoutTimer);
		},
		async loadLocale() {
			try {
				const r = await frappe.call({
					method: "zatgo_core.chat_ai.api.chat.get_ui_locale",
					freeze: false,
					error: () => {
						/* keep defaults if method not yet loaded on worker */
					},
				});
				if (!(r && r.message && r.message.ok)) return;
				const d = r.message.data || {};
				if (d.languages && d.languages.length) this.languages = d.languages;
				if (d.language) this.language = d.language;
				this.enableVoiceIn = !!d.enable_voice_input;
				this.enableVoiceOut = !!d.enable_voice_output;
				this.ttsEngine = d.tts_engine || "Voicebox";
				this.voiceboxUrl = (d.voicebox_url || "http://127.0.0.1:17493").replace(/\/$/, "");
				this.voiceboxProfile = d.voicebox_profile || "";
				this.voiceboxEngine = d.voicebox_engine || "";
				this.voiceboxViaServer = !!d.voicebox_via_server;
				/* Speak setting on → automatic speech; local toggle can override */
				const stored = localStorage.getItem("chat_ai_auto_speak");
				if (stored === "1" || stored === "0") {
					this.autoSpeak = stored === "1" && this.enableVoiceOut;
				} else {
					this.autoSpeak =
						this.enableVoiceOut &&
						(d.auto_speak_replies == null ? true : !!d.auto_speak_replies);
				}
				localStorage.setItem("chat_ai_lang", this.language);
			} catch (e) {
				/* keep defaults */
			}
		},
		clientContext() {
			const route = frappe.get_route ? frappe.get_route() : [];
			const ctx = {
				route: { path: route },
				recent: [],
				workspace: {},
				language: this.language,
			};
			if (route[0] === "Workspaces" && route[1]) {
				ctx.workspace = { name: route[1] };
			} else if (route[0] === "List" && route[1]) {
				ctx.workspace = { doctype: route[1] };
			}
			if (route[0] === "Form" && route[1] && route[2]) {
				ctx.form = { doctype: route[1], name: route[2] };
				const frm = window.cur_frm;
				if (frm && frm.doc && frm.doc.doctype === route[1] && frm.doc.name === route[2]) {
					ctx.form.docstatus = frm.doc.docstatus;
					if (frm.doc.company) ctx.form.company = frm.doc.company;
					if (frm.doc.customer) ctx.form.customer = frm.doc.customer;
					if (frm.doc.project) ctx.form.project = frm.doc.project;
					if (frm.doc.warehouse) ctx.form.warehouse = frm.doc.warehouse;
				}
			}
			if (frappe.boot && frappe.boot.user && frappe.boot.user.recent) {
				ctx.recent = frappe.boot.user.recent.slice(0, 10);
			}
			return ctx;
		},
		async loadCommands() {
			try {
				const r = await frappe.call("zatgo_core.chat_ai.api.chat.list_commands");
				if (r.message && r.message.ok) this.commands = r.message.data || [];
			} catch (e) {
				this.commands = [];
			}
		},

		toggleMic() {
			if (!this.enableVoiceIn) {
				frappe.show_alert({ message: this.ui.micOff, indicator: "orange" });
				return;
			}
			if (this.listening) this.stopListening();
			else this.startListening();
		},
		startListening() {
			if (!this.enableVoiceIn) return;
			const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
			if (!SR) {
				frappe.show_alert({ message: this.ui.voiceUnsupported, indicator: "orange" });
				return;
			}
			this.stopSpeaking();
			this._keepListening = true;
			this._voiceBase = (this.input || "").trim();
			this._voiceFinal = "";
			this.liveTranscript = "";
			this.listening = true;
			this.progress = this.ui.listening;
			this._bindRecognition(SR);
		},
		_bindRecognition(SR) {
			if (!this._keepListening) return;
			try {
				if (this.recognition) {
					this.recognition.onend = null;
					this.recognition.onerror = null;
					this.recognition.onresult = null;
					this.recognition.stop();
				}
			} catch (e) {
				/* ignore */
			}
			const rec = new SR();
			rec.lang = this.sttLang;
			rec.continuous = true;
			rec.interimResults = true;
			rec.maxAlternatives = 3;
			rec.onresult = (ev) => {
				let interim = "";
				for (let i = ev.resultIndex; i < ev.results.length; i++) {
					const picked = this.pickBestAlternative(ev.results[i]);
					if (!picked.transcript) continue;
					if (ev.results[i].isFinal) {
						if (picked.confidence > 0 && picked.confidence < 0.35) continue;
						this._voiceFinal = this.joinVoiceParts(this._voiceFinal, picked.transcript);
					} else {
						interim = this.joinVoiceParts(interim, picked.transcript);
					}
				}
				this.input = this.joinVoiceParts(this._voiceBase, this._voiceFinal, interim);
				this.liveTranscript = interim;
				this.progress = interim
					? `${this.ui.livePrefix}: ${interim}`
					: this.ui.listening;
			};
			rec.onerror = (ev) => {
				const err = (ev && ev.error) || "";
				if (err === "not-allowed" || err === "service-not-allowed") {
					this._keepListening = false;
					frappe.show_alert({ message: this.ui.voiceDenied, indicator: "red" });
					this.listening = false;
					this.progress = "";
					this.liveTranscript = "";
					return;
				}
				if (err === "no-speech" || err === "aborted") {
					return;
				}
				if (err === "audio-capture" || err === "network") {
					this._keepListening = false;
					frappe.show_alert({ message: this.ui.voiceError, indicator: "orange" });
					this.listening = false;
					this.progress = "";
					this.liveTranscript = "";
				}
			};
			rec.onend = () => {
				this.recognition = null;
				if (!this._keepListening) {
					this.listening = false;
					this.liveTranscript = "";
					if (
						this.progress === this.ui.listening ||
						(this.progress || "").startsWith(this.ui.livePrefix)
					) {
						this.progress = "";
					}
					return;
				}
				clearTimeout(this._restartTimer);
				this._restartTimer = setTimeout(() => {
					if (this._keepListening) this._bindRecognition(SR);
				}, 180);
			};
			this.recognition = rec;
			try {
				rec.start();
			} catch (e) {
				clearTimeout(this._restartTimer);
				this._restartTimer = setTimeout(() => {
					if (this._keepListening) this._bindRecognition(SR);
				}, 250);
			}
		},
		stopListening() {
			this._keepListening = false;
			clearTimeout(this._restartTimer);
			try {
				if (this.recognition) {
					this.recognition.onend = null;
					this.recognition.stop();
				}
			} catch (e) {
				/* ignore */
			}
			this.recognition = null;
			this.listening = false;
			this.liveTranscript = "";
			this.input = this.joinVoiceParts(this._voiceBase, this._voiceFinal);
			this._voiceBase = this.input;
			this._voiceFinal = "";
			if (
				this.progress === this.ui.listening ||
				(this.progress || "").startsWith(this.ui.livePrefix)
			) {
				this.progress = "";
			}
		},
		pickTtsVoice(lang) {
			const voices = window.speechSynthesis.getVoices() || [];
			if (!voices.length) return null;
			const code = (lang || "en-US").toLowerCase();
			const prefix = code.split("-")[0];
			const score = (v) => {
				const vl = (v.lang || "").toLowerCase();
				let s = 0;
				if (vl === code) s += 40;
				else if (vl.startsWith(prefix + "-") || vl === prefix) s += 25;
				else if (vl.startsWith(prefix)) s += 10;
				else return -1;
				if (v.localService) s += 8;
				if (/neural|premium|enhanced|natural/i.test(v.name || "")) s += 5;
				return s;
			};
			let best = null;
			let bestScore = -1;
			for (const v of voices) {
				const s = score(v);
				if (s > bestScore) {
					best = v;
					bestScore = s;
				}
			}
			return best;
		},
		cleanForSpeech(text) {
			return String(text || "")
				.replace(/```[\s\S]*?```/g, " ")
				.replace(/`[^`]+`/g, " ")
				.replace(/[#*_>~]/g, " ")
				.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
				.replace(/https?:\/\/\S+/g, " ")
				.replace(/\s+/g, " ")
				.trim();
		},
		voiceboxLang() {
			const c = (this.language || "en").split("-")[0];
			const ok = {
				zh: 1,
				en: 1,
				ja: 1,
				ko: 1,
				de: 1,
				fr: 1,
				ru: 1,
				pt: 1,
				es: 1,
				it: 1,
				he: 1,
				ar: 1,
				da: 1,
				el: 1,
				fi: 1,
				hi: 1,
				ms: 1,
				nl: 1,
				no: 1,
				pl: 1,
				sv: 1,
				sw: 1,
				tr: 1,
			};
			return ok[c] ? c : "en";
		},
		async speak(msg) {
			if (!this.enableVoiceOut || !this.ttsAvailable || !msg || !msg.text) return;
			this.stopSpeaking();
			const plain = this.cleanForSpeech(msg.text);
			if (!plain) return;
			this.speakingId = msg.id;
			if (this.ttsEngine === "Voicebox") {
				try {
					await this.speakVoicebox(plain, msg.id);
					return;
				} catch (e) {
					console.warn("Voicebox speak failed, falling back to browser TTS", e);
					if (this.speakingId !== msg.id) return;
				}
			}
			this.speakBrowser(plain, msg.id);
		},
		speakBrowser(plain, msgId) {
			if (!(window.speechSynthesis && window.SpeechSynthesisUtterance)) {
				this.speakingId = null;
				return;
			}
			const u = new SpeechSynthesisUtterance(plain);
			u.lang = this.bcp47;
			const match = this.pickTtsVoice(this.bcp47);
			if (match) {
				u.voice = match;
				u.lang = match.lang || this.bcp47;
			}
			u.rate = this.language === "ar" || this.language === "ml" ? 0.9 : 1;
			u.pitch = 1;
			u.onend = () => {
				if (this.speakingId === msgId) this.speakingId = null;
			};
			u.onerror = () => {
				if (this.speakingId === msgId) this.speakingId = null;
			};
			this.speakingId = msgId;
			window.speechSynthesis.speak(u);
		},
		async speakVoicebox(plain, msgId) {
			let audioB64 = null;
			let contentType = "audio/wav";
			let audioUrl = null;

			if (this.voiceboxViaServer) {
				const r = await frappe.call({
					method: "zatgo_core.chat_ai.api.voice.speak",
					args: { text: plain, language: this.voiceboxLang() },
					freeze: false,
				});
				const payload = (r && r.message) || {};
				if (!payload.ok) throw new Error(payload.error || "Voicebox proxy failed");
				const data = payload.data || {};
				audioB64 = data.audio_b64;
				contentType = data.content_type || contentType;
				audioUrl = data.audio_url || null;
			} else {
				const base = this.voiceboxUrl || "http://127.0.0.1:17493";
				const body = {
					text: plain.slice(0, 10000),
					language: this.voiceboxLang(),
				};
				if (this.voiceboxProfile) body.profile = this.voiceboxProfile;
				if (this.voiceboxEngine) body.engine = this.voiceboxEngine;
				const speakRes = await fetch(`${base}/speak`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"X-Voicebox-Client-Id": "chat-ai",
					},
					body: JSON.stringify(body),
				});
				if (!speakRes.ok) {
					const errText = await speakRes.text();
					throw new Error(errText || `Voicebox HTTP ${speakRes.status}`);
				}
				const gen = await speakRes.json();
				const genId = gen && gen.id;
				if (!genId) throw new Error("Voicebox returned no generation id");
				const deadline = Date.now() + 120000;
				let status = gen.status || "generating";
				while (Date.now() < deadline) {
					if (this.speakingId !== msgId) return;
					const histRes = await fetch(`${base}/history/${genId}`, {
						headers: { "X-Voicebox-Client-Id": "chat-ai" },
					});
					if (histRes.ok) {
						const hist = await histRes.json();
						status = hist.status || status;
						if (status === "completed") break;
						if (status === "failed") throw new Error(hist.error || "Voicebox failed");
					}
					await new Promise((resolve) => setTimeout(resolve, 600));
				}
				if (status !== "completed") throw new Error("Voicebox timed out");
				audioUrl = `${base}/audio/${genId}`;
			}

			if (this.speakingId !== msgId) return;

			const audio = new Audio();
			this._voiceboxAudio = audio;
			if (audioB64) {
				audio.src = `data:${contentType};base64,${audioB64}`;
			} else if (audioUrl) {
				audio.src = audioUrl;
			} else {
				throw new Error("No Voicebox audio");
			}
			audio.onended = () => {
				if (this.speakingId === msgId) this.speakingId = null;
				if (this._voiceboxAudio === audio) this._voiceboxAudio = null;
			};
			audio.onerror = () => {
				if (this.speakingId === msgId) this.speakingId = null;
				if (this._voiceboxAudio === audio) this._voiceboxAudio = null;
			};
			await audio.play();
		},
		stopSpeaking() {
			try {
				if (window.speechSynthesis) window.speechSynthesis.cancel();
			} catch (e) {
				/* ignore */
			}
			try {
				if (this._voiceboxAudio) {
					this._voiceboxAudio.pause();
					this._voiceboxAudio.src = "";
					this._voiceboxAudio = null;
				}
			} catch (e) {
				/* ignore */
			}
			this.speakingId = null;
		},

	},
	template: `
<div class="cai-shell" :class="{ 'cai-shell--wide': expanded }">
  <button
    type="button"
    class="cai-launcher"
    :class="{ 'cai-launcher--hidden': open }"
    :title="ui.open + ' (Ctrl+Shift+J)'"
    :aria-label="ui.open"
    @click="toggle()"
  >
    <span class="cai-launcher-mark" aria-hidden="true">ZAI</span>
  </button>

  <div v-if="open" class="cai-scrim" @click="toggle(false)" aria-hidden="true"></div>

  <aside
    ref="panel"
    class="cai-panel"
    :class="{ 'cai-panel--open': open, 'cai-panel--rtl': dir === 'rtl', 'cai-panel--drop': dragging }"
    :dir="dir"
    :aria-hidden="open ? 'false' : 'true'"
    :inert="open ? null : ''"
    role="complementary"
    :aria-label="ui.brand"
    @dragover="onDragOver"
    @dragleave.self="dragging = false"
    @drop.prevent="onDrop"
  >
    <header class="cai-header">
      <button type="button" class="cai-icon-btn cai-btn-chats" :aria-label="showSessions ? ui.hideChats : ui.showChats" :aria-expanded="showSessions ? 'true' : 'false'" @click="showSessions = !showSessions; showSessions && refreshSessions()">
        <span aria-hidden="true">☰</span>
      </button>
      <div class="cai-brand">
        <strong class="cai-brand-title" :title="sessionTitle">{{ sessionTitle }}</strong>
        <span class="cai-brand-sub">{{ ui.brand }} · {{ mode || ui.modeAuto }}</span>
      </div>
      <button type="button" class="cai-icon-btn" :aria-label="ui.newChatFull" :title="ui.newChatFull + ' (Ctrl+Shift+O)'" @click="newSession"><span aria-hidden="true">＋</span></button>
      <div class="cai-menu-wrap">
        <button type="button" class="cai-icon-btn" :aria-label="ui.menu" aria-haspopup="menu" :aria-expanded="menuOpen ? 'true' : 'false'" @click="menuOpen = !menuOpen"><span aria-hidden="true">⋯</span></button>
        <div v-if="menuOpen" class="cai-menu" role="menu" @click.stop>
          <button type="button" role="menuitem" class="cai-menu-item" @click="renameSession">{{ ui.rename }}</button>
          <button type="button" role="menuitem" class="cai-menu-item" @click="togglePin">{{ sessionPinned ? ui.unpin : ui.pin }}</button>
          <button type="button" role="menuitem" class="cai-menu-item" @click="exportMarkdown('copy')">{{ ui.copyMarkdown }}</button>
          <button type="button" role="menuitem" class="cai-menu-item" @click="exportMarkdown('download')">{{ ui.downloadMarkdown }}</button>
          <button type="button" role="menuitem" class="cai-menu-item" @click="showArtifacts = true; menuOpen = false; loadArtifacts()">{{ ui.artifacts }}</button>
          <button type="button" role="menuitem" class="cai-menu-item" @click="openScheduledTasks">{{ ui.scheduledTasks }}</button>
          <button type="button" role="menuitem" class="cai-menu-item" @click="helpOpen = true; menuOpen = false">{{ ui.help }}</button>
          <div class="cai-menu-sep" role="separator"></div>
          <label class="cai-menu-field">
            <span>{{ ui.language }}</span>
            <select :value="language" @change="setLanguage($event.target.value)">
              <option v-for="l in languages" :key="l.code" :value="l.code">{{ l.native }}</option>
            </select>
          </label>
          <div class="cai-menu-sep" role="separator"></div>
          <button type="button" role="menuitem" class="cai-menu-item" @click="clearSession">{{ ui.clear }}</button>
          <button type="button" role="menuitem" class="cai-menu-item" @click="archiveSession">{{ ui.archive }}</button>
          <button type="button" role="menuitem" class="cai-menu-item cai-menu-item--danger" @click="deleteSession">{{ ui.delete }}</button>
        </div>
      </div>
      <button type="button" class="cai-icon-btn cai-btn-wide" :aria-label="expanded ? ui.collapse : ui.expand" :aria-pressed="expanded ? 'true' : 'false'" @click="toggleWide"><span aria-hidden="true">{{ expanded ? '⇥' : '⇤' }}</span></button>
      <button type="button" class="cai-icon-btn" :aria-label="ui.close" @click="toggle(false)"><span aria-hidden="true">×</span></button>
    </header>

    <div class="cai-sr-only" role="status" aria-live="polite">{{ announce }}</div>
    <div v-if="menuOpen || modelMenuOpen" class="cai-overlay-catch" @click="menuOpen = false; modelMenuOpen = false"></div>

    <nav v-if="showSessions" class="cai-rail" :aria-label="ui.sessions">
      <div class="cai-search">
        <input ref="search" type="search" v-model="sessionQuery" :placeholder="ui.searchSessions" :aria-label="ui.searchSessions" />
      </div>
      <div class="cai-rail-list">
        <p v-if="searching && !sessions.length" class="cai-muted">{{ ui.searching }}</p>
        <p v-else-if="!sessions.length" class="cai-muted">{{ sessionQuery ? ui.noResults : ui.noChats }}</p>
        <template v-for="g in groupedSessions" :key="g.key">
          <h3 class="cai-rail-group">{{ groupLabel(g.key) }}</h3>
          <button
            v-for="s in g.items"
            :key="s.name"
            type="button"
            class="cai-session"
            :class="{ 'cai-session--active': s.name === session }"
            :aria-current="s.name === session ? 'true' : null"
            @click="openSession(s.name)"
          >
            <span class="cai-session-title">{{ s.title || ui.untitled }}</span>
            <small v-if="s.match === 'message' && s.snippet" class="cai-session-snippet"><span class="cai-muted">{{ ui.inMessages }}:</span>
              <template v-for="(p, pi) in parts(s.snippet)" :key="pi"><mark v-if="p.hit">{{ p.text }}</mark><template v-else>{{ p.text }}</template></template>
            </small>
          </button>
        </template>
      </div>
    </nav>

    <div v-if="showArtifacts" class="cai-rail cai-rail--artifacts" role="region" :aria-label="ui.artifacts">
      <div class="cai-rail-head">
        <strong>{{ ui.artifacts }}</strong>
        <span>
          <button type="button" class="cai-icon-btn" :aria-label="ui.refresh" @click="loadArtifacts"><span aria-hidden="true">↻</span></button>
          <button type="button" class="cai-icon-btn" :aria-label="ui.close" @click="showArtifacts = false"><span aria-hidden="true">×</span></button>
        </span>
      </div>
      <div class="cai-rail-list">
        <button v-for="a in artifacts" :key="a.name" type="button" class="cai-session" @click="openArtifact(a.name)">
          <span class="cai-session-title">{{ a.title || a.artifact_type }}</span>
          <small class="cai-muted">{{ a.artifact_type }}</small>
        </button>
        <p v-if="!artifacts.length" class="cai-muted">{{ ui.noArtifacts }}</p>
      </div>
    </div>

    <div class="cai-messages" ref="messages" role="log" :aria-label="ui.conversation" aria-live="off" aria-relevant="additions" tabindex="0" @scroll.passive="onScroll">
      <div v-if="hasMore" class="cai-older">
        <button type="button" class="cai-btn cai-btn--ghost" :disabled="loadingOlder" @click="loadOlder">{{ loadingOlder ? ui.loadingOlder : ui.loadOlder }}</button>
      </div>

      <div v-if="loadingSession" class="cai-skeleton" aria-hidden="true">
        <span></span><span></span><span></span>
      </div>
      <div v-else-if="historyError" class="cai-alert" role="alert">
        <span>{{ ui.historyError }}</span>
        <button type="button" class="cai-btn" @click="loadHistory">{{ ui.retry }}</button>
      </div>

      <div v-if="!messages.length && !loadingSession && !historyError" class="cai-empty">
        <p class="cai-empty-title">{{ ui.emptyTitle }}</p>
        <p class="cai-empty-hint">{{ ui.emptyHint }}</p>
        <div class="cai-suggest">
          <button v-for="k in ['suggest1','suggest2','suggest3','suggest4']" :key="k" type="button" class="cai-chip" @click="input = ui[k]; focusInput()">{{ ui[k] }}</button>
        </div>
      </div>

      <article
        v-for="msg in messages"
        :key="msg.id"
        class="cai-msg"
        :class="['cai-msg--' + msg.role, 'cai-msg--' + msg.status]"
        :aria-label="msg.role === 'user' ? ui.you : ui.assistant"
      >
        <div class="cai-bubble">
          <!-- user message -->
          <template v-if="msg.role === 'user'">
            <div v-if="editing && editing.id === msg.id" class="cai-edit">
              <label class="cai-sr-only" :for="'cai-edit-' + msg.id">{{ ui.editMessage }}</label>
              <textarea :id="'cai-edit-' + msg.id" ref="editBox" v-model="editing.text" rows="3" @keydown.esc.stop="cancelEdit"></textarea>
              <p class="cai-muted">{{ ui.editWarn }}</p>
              <div class="cai-row">
                <button type="button" class="cai-btn cai-btn--primary" :disabled="!(editing.text || '').trim()" @click="saveEdit(msg)">{{ ui.editSend }}</button>
                <button type="button" class="cai-btn" @click="cancelEdit">{{ ui.cancel }}</button>
              </div>
            </div>
            <div v-else class="cai-user-text">{{ msg.text }}</div>
            <ul v-if="msg.attachments && msg.attachments.length" class="cai-attached">
              <li v-for="(a, ai) in msg.attachments" :key="ai"><span aria-hidden="true">📎</span> {{ attachmentLabel(a) }}</li>
            </ul>
          </template>

          <!-- assistant message -->
          <template v-else>
            <details v-if="msg.steps.length" class="cai-steps">
              <summary>{{ stepsSummary(msg) }}</summary>
              <ul>
                <li v-for="(s, si) in msg.steps" :key="si" :class="'cai-step--' + s.status">{{ s.label }}</li>
              </ul>
            </details>

            <div v-if="(msg.status === 'pending' || msg.status === 'queued') && !msg.text" class="cai-typing" role="img" :aria-label="ui.working"><i></i><i></i><i></i></div>

            <div
              v-if="msg.text"
              class="cai-md"
              :class="{ 'cai-md--streaming': msg.status === 'streaming' }"
              v-html="msgHtml(msg)"
              @click="onMessageClick($event, msg)"
            ></div>

            <template v-for="(b, bi) in msg.blocks" :key="bi">
              <div v-if="b.type === 'table' && b.data" class="cai-tablewrap" role="region" tabindex="0" :aria-label="ui.artifact">
                <table class="cai-table">
                  <thead><tr><th v-for="(h, hi) in (b.data.headers || [])" :key="hi" scope="col">{{ h }}</th></tr></thead>
                  <tbody><tr v-for="(row, ri) in (b.data.rows || [])" :key="ri"><td v-for="(cell, ci) in row" :key="ci">{{ L().fmtCell(cell) }}</td></tr></tbody>
                </table>
              </div>
              <div v-if="b.type === 'table'" class="cai-row">
                <button type="button" class="cai-btn cai-btn--ghost" @click="tableCsv(b.data)">{{ ui.downloadCsv }}</button>
                <button type="button" class="cai-btn cai-btn--ghost" @click="copyText(JSON.stringify(b.data || {}))">{{ ui.copyJson }}</button>
              </div>
              <div v-if="b.type === 'links' && Array.isArray(b.data)" class="cai-links">
                <button v-for="(l, li) in b.data" :key="li" type="button" class="cai-chip" @click="openLink(l.doctype, l.name)">{{ l.doctype }}: {{ l.name }}</button>
              </div>
              <div v-if="b.type === 'plan' && b.data" class="cai-plan">
                <template v-if="(b.data.assumptions || []).length">
                  <strong>{{ ui.assumptions }}</strong>
                  <ul><li v-for="(a, ai) in b.data.assumptions" :key="'a' + ai">{{ a }}</li></ul>
                </template>
                <ol v-if="(b.data.steps || []).length"><li v-for="(s, si) in b.data.steps" :key="'s' + si">{{ s }}</li></ol>
              </div>
              <span v-if="b.type === 'badge' || b.type === 'status'" class="cai-badge">{{ b.data && (b.data.label || b.data.text || b.data) }}</span>
              <details v-if="b.type === 'chart' || b.type === 'json' || b.type === 'artifact'" class="cai-artifact">
                <summary>{{ ui.artifact }}</summary>
                <pre><code>{{ typeof b.data === 'string' ? b.data : JSON.stringify(b.data, null, 2) }}</code></pre>
                <button type="button" class="cai-btn cai-btn--ghost" @click="copyText(typeof b.data === 'string' ? b.data : JSON.stringify(b.data, null, 2))">{{ ui.copy }}</button>
              </details>
            </template>

            <div v-if="msg.status === 'error'" class="cai-alert" role="alert">
              <span>{{ errorText(msg) }}<template v-if="msg.error && msg.error.partial"> {{ ui.partialNotSaved }}</template></span>
              <span class="cai-row">
                <button v-if="canRetryMsg(msg)" type="button" class="cai-btn" @click="retryMessage(msg)">{{ msg.error && msg.error.reload ? ui.reloadChat : ui.retry }}</button>
                <button v-if="canConfigure(msg)" type="button" class="cai-btn cai-btn--ghost" @click="openSettings">{{ ui.openSettings }}</button>
              </span>
            </div>

            <div v-if="msg.needs_plan_approval" class="cai-confirm">
              <template v-if="!msg.confirmState">
                <button type="button" class="cai-btn cai-btn--primary" @click="confirmPlan(true, msg)">{{ ui.planOk }}</button>
                <button type="button" class="cai-btn" @click="confirmPlan(false, msg)">{{ ui.cancel }}</button>
              </template>
              <span v-else class="cai-badge">{{ msg.confirmState === 'approved' ? ui.approved : ui.declined }}</span>
            </div>
            <div v-if="msg.needs_confirmation" class="cai-confirm">
              <template v-if="!msg.confirmState">
                <button type="button" class="cai-btn cai-btn--primary" @click="confirmPending(true, msg)">{{ ui.confirm }}</button>
                <button type="button" class="cai-btn" @click="confirmPending(false, msg)">{{ ui.cancel }}</button>
              </template>
              <span v-else class="cai-badge">{{ msg.confirmState === 'approved' ? ui.approved : ui.declined }}</span>
            </div>

            <details v-if="sourceTotal(msg)" class="cai-sources" :open="msg.srcOpen != null">
              <summary>{{ ui.sources }} ({{ sourceTotal(msg) }})</summary>
              <template v-for="kind in ['web', 'file']" :key="kind">
                <template v-if="grouped(msg)[kind].length">
                  <h4>{{ kind === 'web' ? ui.sourcesWeb : ui.sourcesFiles }}</h4>
                  <ol class="cai-source-list">
                    <li v-for="s in grouped(msg)[kind]" :key="s.n" :id="'cai-src-' + msg.id + '-' + s.n" class="cai-source" :value="s.n">
                      <span class="cai-source-n">{{ s.n }}</span>
                      <span class="cai-source-body">
                        <a v-if="s.type === 'web' && s.url" :href="s.url" target="_blank" rel="noopener noreferrer nofollow" :aria-label="ui.openSource + ': ' + s.title">{{ s.title }}</a>
                        <span v-else class="cai-source-title">{{ s.title }}<template v-if="s.chunk != null && s.chunk >= 0"> · {{ t('part', { n: s.chunk + 1 }) }}</template><template v-else-if="s.chunk === -1"> · {{ ui.computedFromFile }}</template></span>
                        <small v-if="s.type === 'web' && s.domain" class="cai-muted">{{ s.domain }}</small>
                        <small v-if="s.snippet" class="cai-source-snippet">{{ s.snippet }}</small>
                      </span>
                    </li>
                  </ol>
                </template>
              </template>
            </details>

            <div v-if="badge(msg) && msg.status !== 'pending'" class="cai-meta" :class="{ 'cai-meta--fallback': badge(msg).fallbackFrom }">
              <span>{{ badgeText(msg) }}</span>
              <span v-if="routeLabel(badge(msg).route) && !badge(msg).fallbackFrom" class="cai-badge">{{ routeLabel(badge(msg).route) }}</span>
            </div>
          </template>
        </div>

        <div v-if="!busy && msg.status !== 'pending' && msg.status !== 'streaming' && !(editing && editing.id === msg.id)" class="cai-actions" role="group" :aria-label="msg.role === 'user' ? ui.you : ui.assistant">
          <button type="button" class="cai-act" :aria-label="ui.copyMessage" :title="ui.copyMessage" @click="copyText(msg.text)"><span aria-hidden="true">⧉</span></button>
          <button v-if="msg.role === 'assistant' && L().canRegenerate(messages, msg)" type="button" class="cai-act" :aria-label="ui.regenerate" :title="ui.regenerate" @click="regenerate(msg)"><span aria-hidden="true">↻</span></button>
          <button v-if="msg.role === 'user' && msg.serverId" type="button" class="cai-act" :aria-label="ui.editMessage" :title="ui.editMessage" @click="startEdit(msg)"><span aria-hidden="true">✎</span></button>
          <button v-if="msg.role === 'assistant' && enableVoiceOut && ttsAvailable && msg.text" type="button" class="cai-act" :aria-label="speakingId === msg.id ? ui.stop : ui.speak" :title="speakingId === msg.id ? ui.stop : ui.speak" @click="speakingId === msg.id ? stopSpeaking() : speak(msg)"><span aria-hidden="true">{{ speakingId === msg.id ? '■' : '🔊' }}</span></button>
          <button v-if="msg.serverId" type="button" class="cai-act cai-act--danger" :aria-label="ui.deleteMessage" :title="ui.deleteMessage" @click="deleteMessage(msg)"><span aria-hidden="true">🗑</span></button>
        </div>
      </article>
    </div>

    <button v-if="!atBottom && messages.length" type="button" class="cai-jump" @click="scrollToBottom(true)">{{ ui.jumpLatest }} <span aria-hidden="true">↓</span></button>

    <div class="cai-progress" :class="{ 'cai-progress--active': progress || busy || listening }" aria-hidden="true">
      <span v-if="progress || busy || listening" class="cai-progress-dot"></span>
      <span class="cai-progress-text">{{ progress || (busy ? ui.working : '') }}</span>
    </div>

    <footer class="cai-composer" :class="{ 'cai-composer--listening': listening }">
      <div v-if="dragging" class="cai-drop" aria-hidden="true">{{ ui.dropFiles }}</div>

      <ul v-if="files.length" class="cai-files" :aria-label="ui.attach">
        <li v-for="f in files" :key="f.id" class="cai-file" :class="'cai-file--' + f.status">
          <img v-if="f.thumb" :src="f.thumb" alt="" class="cai-file-thumb" />
          <span v-else class="cai-file-icon" aria-hidden="true">📄</span>
          <span class="cai-file-body">
            <span class="cai-file-name">{{ f.name }}</span>
            <small class="cai-file-state" :role="f.status === 'failed' ? 'alert' : null">{{ fileState(f) }}</small>
          </span>
          <button type="button" class="cai-act" :aria-label="ui.removeFile + ': ' + f.name" @click="removeFile(f)"><span aria-hidden="true">×</span></button>
        </li>
      </ul>

      <div v-show="paletteOpen" class="cai-palette" role="listbox" :aria-label="ui.commands">
        <button v-for="(c, ci) in paletteItems" :key="c.name" type="button" role="option" :aria-selected="ci === paletteIndex ? 'true' : 'false'" class="cai-palette-item" :class="{ 'cai-palette-item--on': ci === paletteIndex }" @click="pickCommand(c)">
          <strong>/{{ c.name }}</strong><span>{{ c.description || c.label || '' }}</span>
        </button>
      </div>

      <label class="cai-sr-only" for="cai-input">{{ ui.composerLabel }}</label>
      <textarea
        id="cai-input"
        ref="input"
        class="cai-input"
        v-model="input"
        rows="1"
        :placeholder="ui.placeholder"
        enterkeyhint="send"
        @keydown="onKeydown"
        @input="autoGrow"
        @paste="onPaste"
      ></textarea>

      <div class="cai-toolbar">
        <input v-if="features.file_upload" ref="filePicker" type="file" multiple class="cai-sr-only" tabindex="-1" :accept="acceptTypes" @change="onPickFiles" />
        <button v-if="features.file_upload" type="button" class="cai-tool" :aria-label="ui.attach" :title="ui.attach" @click="$refs.filePicker.click()"><span aria-hidden="true">📎</span></button>
        <button v-if="features.web_search" type="button" class="cai-tool" :class="{ 'cai-tool--on': webOn }" :aria-pressed="webOn ? 'true' : 'false'" :aria-label="ui.webSearch" :title="webOn ? ui.webSearchOn : ui.webSearchOff" @click="webOn = !webOn"><span aria-hidden="true">🌐</span><span class="cai-tool-label">{{ ui.webSearch }}</span></button>

        <div v-if="showModelPicker" class="cai-menu-wrap">
          <button type="button" class="cai-tool cai-tool--model" aria-haspopup="menu" :aria-expanded="modelMenuOpen ? 'true' : 'false'" :aria-label="ui.model + ': ' + currentModelLabel" @click="modelMenuOpen = !modelMenuOpen"><span class="cai-tool-label cai-tool-label--always">{{ currentModelLabel }}</span><span aria-hidden="true">▾</span></button>
          <div v-if="modelMenuOpen" class="cai-menu cai-menu--up" role="menu" @click.stop>
            <button type="button" role="menuitemradio" :aria-checked="!selectedModel ? 'true' : 'false'" class="cai-menu-item" @click="pickModel('')">
              {{ routing ? ui.modelAuto : ui.modelDefault }}<small v-if="routing" class="cai-muted"> — {{ ui.modelAutoHint }}</small>
            </button>
            <button v-for="m in models" :key="m.name" type="button" role="menuitemradio" :aria-checked="selectedModel === m.name ? 'true' : 'false'" class="cai-menu-item" @click="pickModel(m.name)">
              {{ m.name }} <small class="cai-muted">{{ slotLabel(m.slot) }}</small>
            </button>
          </div>
        </div>

        <span class="cai-spacer"></span>

        <button v-if="enableVoiceOut && ttsAvailable" type="button" class="cai-tool" :class="{ 'cai-tool--on': autoSpeak }" :aria-pressed="autoSpeak ? 'true' : 'false'" :aria-label="autoSpeak ? ui.speakOn : ui.speakOff" :title="autoSpeak ? ui.speakOn : ui.speakOff" @click="toggleAutoSpeak"><span aria-hidden="true">{{ autoSpeak ? '🔊' : '🔇' }}</span></button>
        <button v-if="voiceAvailable" type="button" class="cai-tool" :class="{ 'cai-tool--on': listening }" :disabled="!enableVoiceIn || busy" :aria-pressed="listening ? 'true' : 'false'" :aria-label="enableVoiceIn ? ui.mic : ui.micOff" :title="enableVoiceIn ? ui.mic : ui.micOff" @click="toggleMic"><span aria-hidden="true">{{ listening ? '■' : '🎤' }}</span></button>
        <button v-if="busy" type="button" class="cai-btn cai-btn--stop" :disabled="stopping" @click="stopGeneration">{{ stopping ? ui.stopping : ui.stopGen }}</button>
        <button v-else type="button" class="cai-btn cai-btn--primary cai-send" :disabled="!canSend" @click="send">{{ ui.send }}</button>
      </div>
      <p class="cai-hint">{{ ui.composerHint }}</p>
    </footer>

    <div v-if="helpOpen" class="cai-dialog-wrap" @click.self="helpOpen = false">
      <div class="cai-dialog" role="dialog" aria-modal="true" :aria-label="ui.help" @keydown.esc.stop="helpOpen = false">
        <h2>{{ ui.help }}</h2>
        <dl class="cai-keys"><template v-for="(k, ki) in shortcuts" :key="ki"><dt>{{ k[0] }}</dt><dd><kbd>{{ k[1] }}</kbd></dd></template></dl>
        <div class="cai-row cai-row--end"><button type="button" class="cai-btn cai-btn--primary" autofocus @click="helpOpen = false">{{ ui.ok }}</button></div>
      </div>
    </div>

    <div v-if="dlg" class="cai-dialog-wrap" @click.self="closeDialog">
      <div ref="dialog" class="cai-dialog" role="dialog" aria-modal="true" :aria-label="dlg.title" @keydown="dialogKeydown">
        <h2>{{ dlg.title }}</h2>
        <p v-if="dlg.body">{{ dlg.body }}</p>
        <pre v-if="dlg.pre" class="cai-dialog-pre">{{ dlg.pre }}</pre>
        <label v-if="dlg.input" class="cai-field"><span>{{ dlg.label }}</span><input type="text" v-model="dlg.value" maxlength="140" /></label>
        <div class="cai-row cai-row--end">
          <button type="button" class="cai-btn" @click="dialogCancel">{{ dlg.cancelText || ui.cancel }}</button>
          <button type="button" class="cai-btn" :class="dlg.danger ? 'cai-btn--danger' : 'cai-btn--primary'" @click="dialogOk">{{ dlg.okText || ui.ok }}</button>
        </div>
      </div>
    </div>
  </aside>
</div>
`,
};

$(document).ready(function () {
	if (frappe.session && frappe.session.user && frappe.session.user !== "Guest") {
		chat_ai.sidebar.init();
	}
});
