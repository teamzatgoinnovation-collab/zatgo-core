/**
 * Chat AI — Vue 3 Desk slide-out (languages + voice)
 */
frappe.provide("chat_ai.sidebar");

const CAI_UI = {
	en: {
		sub: "ERP assistant",
		emptyTitle: "Ask anything about your ERP",
		emptyHint: "Click 🎤, speak in the selected language, click mic again to stop, then Send.",
		placeholder: "Message or /command…",
		send: "Send",
		newChat: "New",
		working: "Working…",
		speak: "Speak",
		speakOn: "Auto-speak on",
		speakOff: "Auto-speak off",
		stop: "Stop",
		mic: "Voice input — click to talk, click again to stop",
		micOff: "Enable Voice Input in Chat AI Settings",
		listening: "Listening… speak clearly, then click mic to stop",
		livePrefix: "Hearing",
		confirm: "Confirm",
		cancel: "Cancel",
		planOk: "OK — proceed",
		voiceUnsupported: "Voice input is not supported in this browser. Use Chrome or Edge.",
		voiceError: "Could not hear clearly — try again closer to the mic.",
		voiceDenied: "Microphone permission denied. Allow mic access for this site.",
		sessions: "Chats",
		rename: "Rename",
		pin: "Pin",
		unpin: "Unpin",
		archive: "Archive",
		delete: "Delete",
		clear: "Clear",
		stopGen: "Stop",
		searchSessions: "Search chats…",
		copy: "Copy",
		copied: "Copied",
		artifact: "Result",
		modeAuto: "Auto",
	},
	ar: {
		sub: "مساعد تخطيط الموارد",
		emptyTitle: "اسأل عن أي شيء في النظام",
		emptyHint: "اكتب سؤالاً أو / للأوامر أو استخدم الميكروفون.",
		placeholder: "رسالة أو /أمر…",
		send: "إرسال",
		newChat: "جديد",
		listening: "جاري الاستماع… تحدث بوضوح ثم اضغط الميكروفون للإيقاف",
		working: "جاري العمل…",
		speak: "تشغيل",
		speakOn: "التحدث التلقائي مفعّل",
		speakOff: "التحدث التلقائي متوقف",
		stop: "إيقاف",
		mic: "إدخال صوتي — اضغط للتحدث ثم مجدداً للإيقاف",
		micOff: "فعّل الإدخال الصوتي من إعدادات Chat AI",
		livePrefix: "يُسمع",
		confirm: "تأكيد",
		cancel: "إلغاء",
		planOk: "موافق — متابعة",
		voiceUnsupported: "الإدخال الصوتي غير مدعوم. استخدم Chrome أو Edge.",
		voiceError: "لم يُسمع بوضوح — حاول مجدداً أقرب للميكروفون.",
		voiceDenied: "تم رفض إذن الميكروفون. اسمح بالوصول لهذا الموقع.",
		sessions: "المحادثات",
		rename: "إعادة تسمية",
		pin: "تثبيت",
		unpin: "إلغاء التثبيت",
		archive: "أرشفة",
		delete: "حذف",
		clear: "مسح",
		stopGen: "إيقاف",
		searchSessions: "بحث…",
		copy: "نسخ",
		copied: "تم النسخ",
		artifact: "نتيجة",
		modeAuto: "تلقائي",
	},
	ml: {
		sub: "ERP സഹായി",
		emptyTitle: "ERP-യെക്കുറിച്ച് എന്തും ചോദിക്കൂ",
		emptyHint: "ചോദ്യം ടൈപ്പ് ചെയ്യുക, / കമാൻഡ്, അല്ലെങ്കിൽ മൈക്ക് ഉപയോഗിക്കുക.",
		placeholder: "സന്ദേശം അല്ലെങ്കിൽ /കമാൻഡ്…",
		send: "അയയ്ക്കുക",
		newChat: "പുതിയത്",
		listening: "കേൾക്കുന്നു… വ്യക്തമായി സംസാരിച്ച് മൈക്ക് അമർത്തി നിർത്തുക",
		working: "പ്രവർത്തിക്കുന്നു…",
		speak: "കേൾക്കുക",
		speakOn: "യാന്ത്രിക സംസാരം ഓൺ",
		speakOff: "യാന്ത്രിക സംസാരം ഓഫ്",
		stop: "നിർത്തുക",
		mic: "വോയ്സ് — ക്ലിക്ക് ചെയ്ത് സംസാരിക്കുക, വീണ്ടും അമർത്തി നിർത്തുക",
		micOff: "Chat AI Settings-ൽ Voice Input ഓണാക്കുക",
		livePrefix: "കേൾക്കുന്നു",
		confirm: "സ്ഥിരീകരിക്കുക",
		cancel: "റദ്ദാക്കുക",
		planOk: "ശരി — തുടരുക",
		voiceUnsupported: "വോയ്സ് ലഭ്യമല്ല. Chrome അല്ലെങ്കിൽ Edge ഉപയോഗിക്കുക.",
		voiceError: "വ്യക്തമായി കേട്ടില്ല — മൈക്കിനോട് അടുത്ത് വീണ്ടും ശ്രമിക്കുക.",
		voiceDenied: "മൈക്ക് അനുമതി നിഷേധിച്ചു. ഈ സൈറ്റിന് അനുവദിക്കുക.",
		sessions: "ചാറ്റുകൾ",
		rename: "പേര് മാറ്റുക",
		pin: "പിൻ",
		unpin: "അൺപിൻ",
		archive: "ആർക്കൈവ്",
		delete: "ഇല്ലാതാക്കുക",
		clear: "മായ്ക്കുക",
		stopGen: "നിർത്തുക",
		searchSessions: "തിരയുക…",
		copy: "പകർത്തുക",
		copied: "പകർത്തി",
		artifact: "ഫലം",
		modeAuto: "ഓട്ടോ",
	},
};

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

		document.addEventListener("keydown", (e) => {
			if (e.key === "Escape" && this._vm && this._vm.open) {
				this._vm.toggle(false);
			}
			if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "j") {
				e.preventDefault();
				if (this._vm) this._vm.toggle();
			}
		});
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
			input: "",
			progress: "",
			busy: false,
			listening: false,
			speakingId: null,
			commands: [],
			paletteOpen: false,
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
			sessions: [],
			sessionQuery: "",
			showSessions: false,
			streamMsgId: null,
			streamStopped: false,
			sessionPinned: false,
			artifacts: [],
			showArtifacts: false,
			_typeQueue: "",
			_typeTimer: null,
			_typeMsgId: null,
			_typePendingMeta: null,
		};
	},
	computed: {
		ui() {
			return CAI_UI[this.language] || CAI_UI.en;
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
			if (!this.input.startsWith("/")) return [];
			const q = this.input.slice(1).toLowerCase();
			return (this.commands || []).filter(
				(c) =>
					!q ||
					(c.name || "").toLowerCase().startsWith(q) ||
					(c.label || "").toLowerCase().includes(q)
			);
		},
		voiceAvailable() {
			return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
		},
		ttsAvailable() {
			if (this.ttsEngine === "Voicebox") return true;
			return !!(window.speechSynthesis && window.SpeechSynthesisUtterance);
		},
	},
	watch: {
		input() {
			this.paletteOpen = this.input.startsWith("/") && this.paletteItems.length > 0;
		},
		language() {
			if (this.listening) {
				this.stopListening();
				this.$nextTick(() => this.startListening());
			}
		},
	},
	async mounted() {
		chat_ai.sidebar._vm = this;
		this.bindRealtime();
		this.bindLayout();
		this.warmVoices();
		this.updateLayoutOffset();
		await this.loadLocale();
		this.loadCommands();
		await this.refreshSessions();
		if (this.open && !this.session) {
			if (this.sessions.length) await this.openSession(this.sessions[0].name);
			else await this.newSession();
		}
	},
	beforeUnmount() {
		this.unbindLayout();
		this.stopListening();
		this.stopSpeaking();
	},
	methods: {
		esc(s) {
			return frappe.utils.escape_html(String(s ?? ""));
		},
		formatText(s) {
			let t = this.esc(s);
			const codes = [];
			t = t.replace(/```([\s\S]*?)```/g, (_, code) => {
				const i = codes.length;
				codes.push(`<pre class="cai-code"><code>${code.trim()}</code></pre>`);
				return `@@CODE${i}@@`;
			});
			t = t.replace(/`([^`]+)`/g, "<code class=\"cai-inline-code\">$1</code>");
			t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
			t = t.replace(/(^|\n)[\-*] (.+)/g, "$1• $2");
			t = t.replace(/\n/g, "<br>");
			codes.forEach((html, i) => {
				t = t.replace(`@@CODE${i}@@`, html);
			});
			return t;
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
		toggle(force) {
			this.open = typeof force === "boolean" ? force : !this.open;
			localStorage.setItem("chat_ai_open", this.open ? "1" : "0");
			this.$nextTick(() => this.updateLayoutOffset());
			if (this.open && !this.session) this.newSession();
			if (this.open) {
				this.$nextTick(() => {
					const el = this.$refs.input;
					if (el) el.focus();
				});
			} else {
				this.stopListening();
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
		async newSession() {
			const r = await frappe.call("zatgo_core.chat_ai.api.chat.new_session", {
				language: this.language,
			});
			if (r.message && r.message.ok) {
				this.session = r.message.data.name;
				this.messages = [];
				this.progress = "";
				this.pending = null;
				this.sessionPinned = false;
				this.streamMsgId = null;
				this.streamStopped = false;
				this.stopSpeaking();
				await this.refreshSessions();
			}
		},
		async refreshSessions() {
			try {
				const method = this.sessionQuery
					? "zatgo_core.chat_ai.api.chat.search_sessions"
					: "zatgo_core.chat_ai.api.chat.list_sessions";
				const args = this.sessionQuery ? { query: this.sessionQuery } : { status: "Active" };
				const r = await frappe.call(method, args);
				if (r.message && r.message.ok) this.sessions = r.message.data || [];
			} catch (e) {
				this.sessions = [];
			}
		},
		async openSession(name) {
			if (!name || name === this.session) {
				this.showSessions = false;
				return;
			}
			this.session = name;
			this.messages = [];
			this.pending = null;
			this.streamMsgId = null;
			this.progress = "";
			this.showSessions = false;
			const meta = (this.sessions || []).find((s) => s.name === name);
			if (meta) {
				this.mode = meta.assistant_mode || this.mode;
				this.sessionPinned = !!meta.is_pinned;
			}
			try {
				const r = await frappe.call("zatgo_core.chat_ai.api.chat.history", { session: name, limit: 80 });
				if (!(r.message && r.message.ok)) return;
				const rows = r.message.data || [];
				for (const row of rows) {
					let cj = {};
					try {
						cj = typeof row.content_json === "string"
							? JSON.parse(row.content_json || "{}")
							: row.content_json || {};
					} catch (e) {
						cj = {};
					}
					this.pushMessage(row.role || "assistant", {
						text: row.content || "",
						content_json: cj,
					}, { history: true });
				}
			} catch (e) {
				/* ignore */
			}
			await this.loadArtifacts();
		},
		async renameSession() {
			if (!this.session) return;
			const title = prompt(this.ui.rename, (this.sessions.find((s) => s.name === this.session) || {}).title || "");
			if (title == null) return;
			await frappe.call("zatgo_core.chat_ai.api.chat.rename", { session: this.session, title });
			await this.refreshSessions();
		},
		async togglePin() {
			if (!this.session) return;
			const next = this.sessionPinned ? 0 : 1;
			await frappe.call("zatgo_core.chat_ai.api.chat.pin", { session: this.session, pinned: next });
			this.sessionPinned = !!next;
			await this.refreshSessions();
		},
		async archiveSession() {
			if (!this.session) return;
			await frappe.call("zatgo_core.chat_ai.api.chat.archive", { session: this.session });
			this.session = null;
			this.messages = [];
			await this.refreshSessions();
			if (this.sessions.length) await this.openSession(this.sessions[0].name);
			else await this.newSession();
		},
		async deleteSession() {
			if (!this.session) return;
			if (!confirm(this.ui.delete + "?")) return;
			await frappe.call("zatgo_core.chat_ai.api.chat.delete_session", { session: this.session });
			this.session = null;
			this.messages = [];
			await this.refreshSessions();
			if (this.sessions.length) await this.openSession(this.sessions[0].name);
			else await this.newSession();
		},
		async clearSession() {
			if (!this.session) return;
			await frappe.call("zatgo_core.chat_ai.api.chat.clear", { session: this.session });
			this.messages = [];
			this.pending = null;
		},
		stopGeneration() {
			this.streamStopped = true;
			this.busy = false;
			this.progress = "";
			this.clearTypewriter(true);
			this.streamMsgId = null;
			if (this.session) {
				frappe.call({
					method: "zatgo_core.chat_ai.api.chat.cancel",
					args: { session: this.session },
				}).catch(() => {});
			}
		},
		clearTypewriter(flush) {
			if (this._typeTimer) {
				clearTimeout(this._typeTimer);
				this._typeTimer = null;
			}
			const msg = this.messages.find((m) => m.id === this._typeMsgId);
			if (msg) {
				if (flush && this._typeQueue) {
					msg.text = (msg.text || "") + this._typeQueue;
				}
				msg.typing = false;
			}
			this._typeQueue = "";
			this._typeMsgId = null;
			const meta = this._typePendingMeta;
			this._typePendingMeta = null;
			if (meta && msg) this.applyMessageMeta(msg, meta);
		},
		applyMessageMeta(msg, meta) {
			if (!msg || !meta) return;
			if (meta.blocks) msg.blocks = meta.blocks;
			if (meta.needs_confirmation != null) msg.needs_confirmation = !!meta.needs_confirmation;
			if (meta.needs_plan_approval != null) msg.needs_plan_approval = !!meta.needs_plan_approval;
			if (meta.pending_plan) msg.pending_plan = meta.pending_plan;
			if (meta.pending_assumptions) msg.pending_assumptions = meta.pending_assumptions;
			if (meta.confirmation_token) msg.confirmation_token = meta.confirmation_token;
			if (msg.needs_confirmation && meta.pending) this.pending = meta.pending;
			else if (msg.needs_plan_approval && meta.pending) this.pending = meta.pending;
			if (meta.speak && this.autoSpeak && this.enableVoiceOut && msg.text) this.speak(msg);
		},
		enqueueType(msgId, chunk) {
			if (!chunk || this.streamStopped) return;
			this._typeMsgId = msgId;
			this._typeQueue += chunk;
			const msg = this.messages.find((m) => m.id === msgId);
			if (msg) msg.typing = true;
			if (!this._typeTimer) this.drainTypewriter();
		},
		drainTypewriter() {
			if (this.streamStopped) {
				this.clearTypewriter(false);
				return;
			}
			if (!this._typeQueue) {
				this._typeTimer = null;
				const msg = this.messages.find((m) => m.id === this._typeMsgId);
				if (msg) msg.typing = false;
				const meta = this._typePendingMeta;
				if (meta && msg) {
					this._typePendingMeta = null;
					this.applyMessageMeta(msg, meta);
				}
				return;
			}
			/* ChatGPT-style: reveal one word at a time */
			const wordMatch = this._typeQueue.match(/^(\s+|[^\s]+(?:\s+)?)/);
			const take = wordMatch ? wordMatch[0] : this._typeQueue.slice(0, 1);
			this._typeQueue = this._typeQueue.slice(take.length);
			const msg = this.messages.find((m) => m.id === this._typeMsgId);
			if (msg) {
				msg.text = (msg.text || "") + take;
				msg.typing = true;
			}
			this.$nextTick(() => {
				const box = this.$refs.messages;
				if (box) box.scrollTop = box.scrollHeight;
			});
			let delay = 52;
			if (/[.!?…]/.test(take)) delay = 110;
			else if (/\n/.test(take)) delay = 80;
			else if (/[,;:]/.test(take)) delay = 70;
			else if (take.length > 12) delay = 64;
			this._typeTimer = setTimeout(() => this.drainTypewriter(), delay);
		},
		typeToFull(msgId, fullText, meta) {
			const msg = this.messages.find((m) => m.id === msgId);
			if (!msg) return Promise.resolve();
			const target = fullText || "";
			this._typePendingMeta = meta || null;
			if (!target) {
				this.applyMessageMeta(msg, meta);
				msg.typing = false;
				return Promise.resolve();
			}
			/* Sync queue to remaining text only — avoid duplicating streamed chunks */
			const current = msg.text || "";
			if (this._typeTimer) {
				clearTimeout(this._typeTimer);
				this._typeTimer = null;
			}
			this._typeQueue = "";
			if (target === current) {
				this.applyMessageMeta(msg, meta);
				msg.typing = false;
				return Promise.resolve();
			}
			if (target.startsWith(current)) {
				const rest = target.slice(current.length);
				if (!rest) {
					this.applyMessageMeta(msg, meta);
					msg.typing = false;
					return Promise.resolve();
				}
				this.enqueueType(msgId, rest);
			} else {
				msg.text = "";
				this.enqueueType(msgId, target);
			}
			return new Promise((resolve) => {
				const wait = () => {
					if (!this._typeQueue && !this._typeTimer) {
						resolve();
						return;
					}
					setTimeout(wait, 40);
				};
				wait();
			});
		},
		toggleAutoSpeak() {
			if (!this.enableVoiceOut || !this.ttsAvailable) return;
			this.autoSpeak = !this.autoSpeak;
			localStorage.setItem("chat_ai_auto_speak", this.autoSpeak ? "1" : "0");
			if (!this.autoSpeak) this.stopSpeaking();
		},
		async loadArtifacts() {
			if (!this.session) {
				this.artifacts = [];
				return;
			}
			try {
				const r = await frappe.call({
					method: "zatgo_core.chat_ai.api.platform.chat_artifacts",
					args: { session: this.session, limit: 40 },
				});
				const payload = r.message || {};
				this.artifacts = (payload.ok && payload.data) || payload.data || [];
				if (!Array.isArray(this.artifacts)) this.artifacts = [];
			} catch (e) {
				this.artifacts = [];
			}
		},
		async openArtifact(name) {
			try {
				const r = await frappe.call({
					method: "zatgo_core.chat_ai.api.platform.get_artifact",
					args: { name },
				});
				const payload = r.message || {};
				const doc = (payload.ok && payload.data) || payload.data || {};
				const body = doc.content || "";
				frappe.msgprint({
					title: doc.title || name,
					message: `<pre class="cai-code">${frappe.utils.escape_html(String(body).slice(0, 8000))}</pre>`,
				});
			} catch (e) {
				frappe.show_alert({ message: e.message || "Failed", indicator: "red" });
			}
		},
		async setLanguage(code) {
			this.language = code;
			localStorage.setItem("chat_ai_lang", code);
			if (!this.session) return;
			await frappe.call("zatgo_core.chat_ai.api.chat.set_language", {
				session: this.session,
				language: code,
			});
		},
		pickCommand(cmd) {
			this.input = `/${cmd.name} `;
			this.paletteOpen = false;
			if (cmd.name === "help") this.showHelp();
			this.$nextTick(() => {
				if (this.$refs.input) this.$refs.input.focus();
			});
		},
		showHelp() {
			const lines = this.commands.map(
				(c) => `/${c.name} — ${c.description || c.label || ""}`
			);
			this.pushMessage("assistant", {
				text: lines.join("\n") || "No commands available.",
			});
		},
		pushMessage(role, payload, opts = {}) {
			const cj = payload.content_json || {};
			const msg = {
				id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
				role,
				text: payload.text || "",
				blocks: cj.blocks || [],
				needs_confirmation: !!cj.needs_confirmation && !opts.history,
				needs_plan_approval: !!cj.needs_plan_approval && !opts.history,
				pending_plan: cj.pending_plan || [],
				pending_assumptions: cj.pending_assumptions || [],
				confirmation_token: cj.confirmation_token || payload.confirmation_token || "",
			};
			this.messages.push(msg);
			if (role === "assistant" && !opts.history) {
				if (msg.needs_confirmation) {
					this.pending = {
						kind: "tool",
						tool: cj.pending_tool,
						args: cj.pending_args,
						token: msg.confirmation_token,
					};
				} else if (msg.needs_plan_approval) {
					this.pending = {
						kind: "plan",
						plan: msg.pending_plan,
						assumptions: msg.pending_assumptions,
						token: msg.confirmation_token,
					};
				}
			}
			this.$nextTick(() => {
				const box = this.$refs.messages;
				if (box) box.scrollTop = box.scrollHeight;
			});
			/* Auto-speak is handled after typewriter finishes (applyMessageMeta / typeToFull) */
			return msg;
		},
		openLink(dt, nm) {
			frappe.set_route("Form", dt, nm);
		},
		async confirmPending(yes) {
			if (!yes) {
				this.pending = null;
				this.pushMessage("assistant", { text: "Cancelled." });
				return;
			}
			if (!this.pending || this.pending.kind !== "tool") return;
			await this.sendRaw("", {
				confirmed: 1,
				pending_tool: this.pending.tool,
				pending_args: this.pending.args,
				confirmation_token: this.pending.token,
			});
			this.pending = null;
		},
		async confirmPlan(yes) {
			if (!yes) {
				this.pending = null;
				this.pushMessage("assistant", { text: "Cancelled." });
				return;
			}
			if (!this.pending || this.pending.kind !== "plan") return;
			await this.sendRaw("OK", {
				plan_confirmed: 1,
				confirmation_token: this.pending.token,
			});
			this.pending = null;
		},
		isPlanApprovalText(text) {
			const t = (text || "").trim().toLowerCase();
			return ["ok", "yes", "confirm", "proceed", "continue", "go ahead", "y"].includes(t);
		},
		onKeydown(e) {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send();
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
		async send() {
			let text = (this.input || "").trim();
			if (!text || this.busy) return;
			this.stopListening();
			// Typed OK for pending plan
			if (this.pending && this.pending.kind === "plan" && this.isPlanApprovalText(text)) {
				this.input = "";
				this.pushMessage("user", { text });
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
			const display = command ? `/${command} ${text}`.trim() : text;
			this.input = "";
			this.paletteOpen = false;
			this.pushMessage("user", { text: display });
			await this.sendRaw(text, { command });
		},
		async sendRaw(message, extra = {}) {
			if (!this.session) await this.newSession();
			this.busy = true;
			this.streamStopped = false;
			this.progress = this.ui.working;
			const streamMsg = this.pushMessage("assistant", { text: "", content_json: { blocks: [], streaming: true } });
			this.streamMsgId = streamMsg.id;
			try {
				const r = await frappe.call({
					method: "zatgo_core.chat_ai.api.chat.send",
					args: {
						session: this.session,
						message,
						client_context: JSON.stringify(this.clientContext()),
						command: extra.command || null,
						confirmed: extra.confirmed || 0,
						plan_confirmed: extra.plan_confirmed || 0,
						confirmation_token: extra.confirmation_token || null,
						pending_tool: extra.pending_tool || null,
						pending_args: extra.pending_args
							? JSON.stringify(extra.pending_args)
							: null,
					},
				});
				if (this.streamStopped) return;
				const payload = r.message || {};
				const idx = this.messages.findIndex((m) => m.id === this.streamMsgId);
				if (!payload.ok) {
					if (idx >= 0) this.messages[idx].text = payload.error || "Error";
					else this.pushMessage("assistant", { text: payload.error || "Error" });
					return;
				}
				const data = payload.data || {};
				if (data.assistant_mode) this.mode = data.assistant_mode;
				const cj = data.content_json || {
					blocks: [],
					needs_confirmation: data.needs_confirmation,
					needs_plan_approval: data.needs_plan_approval,
					pending_plan: data.pending_plan,
					pending_assumptions: data.pending_assumptions,
					pending_tool: data.pending_tool,
					pending_args: data.pending_args,
					confirmation_token: data.confirmation_token,
				};
				if (idx >= 0) {
					const msg = this.messages[idx];
					const pending =
						cj.needs_confirmation
							? {
									kind: "tool",
									tool: cj.pending_tool,
									args: cj.pending_args,
									token: cj.confirmation_token || data.confirmation_token || "",
							  }
							: cj.needs_plan_approval
								? {
										kind: "plan",
										plan: cj.pending_plan || [],
										assumptions: cj.pending_assumptions || [],
										token: cj.confirmation_token || data.confirmation_token || "",
								  }
								: null;
					await this.typeToFull(msg.id, data.content || msg.text || "", {
						blocks: cj.blocks || [],
						needs_confirmation: !!cj.needs_confirmation,
						needs_plan_approval: !!cj.needs_plan_approval,
						pending_plan: cj.pending_plan || [],
						pending_assumptions: cj.pending_assumptions || [],
						confirmation_token: cj.confirmation_token || data.confirmation_token || "",
						pending,
						speak: true,
					});
				} else {
					const m = this.pushMessage("assistant", {
						text: "",
						content_json: cj,
						confirmation_token: data.confirmation_token,
					});
					await this.typeToFull(m.id, data.content || "", {
						blocks: cj.blocks || [],
						speak: true,
					});
				}
				await this.refreshSessions();
				await this.loadArtifacts();
			} catch (e) {
				const idx = this.messages.findIndex((m) => m.id === this.streamMsgId);
				if (idx >= 0) this.messages[idx].text = e.message || "Request failed";
				else this.pushMessage("assistant", { text: e.message || "Request failed" });
			} finally {
				this.busy = false;
				this.progress = "";
				/* keep streamMsgId until typing finishes if still queued */
				if (!this._typeQueue && !this._typeTimer) this.streamMsgId = null;
			}
		},
		bindRealtime() {
			if (!frappe.realtime || !frappe.realtime.on) return;
			frappe.realtime.on("chat_ai:progress", (data) => {
				if (!data) return;
				if (data.session && this.session && data.session !== this.session) return;
				this.progress = data.label || data.stage || "";
				if (data.stage === "done") {
					setTimeout(() => {
						if (this.progress === (data.label || data.stage)) this.progress = "";
					}, 800);
				}
			});
			frappe.realtime.on("chat_ai:stream", (data) => {
				if (!data) return;
				if (data.session && this.session && data.session !== this.session) return;
				if (this.streamStopped) return;
				if (data.done) {
					this.progress = "";
					return;
				}
				const chunk = data.chunk || "";
				if (!chunk) return;
				let msg = this.messages.find((m) => m.id === this.streamMsgId);
				if (!msg) {
					msg = this.pushMessage("assistant", { text: "", content_json: { blocks: [] } });
					this.streamMsgId = msg.id;
				}
				msg._fromLegacyStream = true;
				this.enqueueType(msg.id, chunk);
			});
			frappe.realtime.on("chat_ai:event", (evt) => {
				if (!evt) return;
				if (evt.session && this.session && evt.session !== this.session) return;
				const t = evt.type || "";
				const d = evt.data || {};
				if (t === "planning" || t === "thinking") {
					this.progress = d.detail || t;
				} else if (t === "tool_started" || t === "tool_progress") {
					this.progress = d.detail || d.tool || t;
				} else if (t === "assistant_message") {
					if (this.streamStopped) return;
					if (d.done) {
						this.progress = "";
						return;
					}
					const chunk = d.chunk || "";
					if (!chunk) return;
					let msg = this.messages.find((m) => m.id === this.streamMsgId);
					if (!msg) {
						msg = this.pushMessage("assistant", { text: "", content_json: { blocks: [] } });
						this.streamMsgId = msg.id;
					}
					/* Prefer legacy stream when both fire */
					if (msg._fromLegacyStream) return;
					this.enqueueType(msg.id, chunk);
				} else if (t === "artifact_created") {
					this.loadArtifacts();
				} else if (t === "done") {
					this.progress = "";
					this.loadArtifacts();
				} else if (t === "error") {
					this.progress = d.message || "Error";
				}
			});
		},
	},
	template: `
<div class="cai-shell">
  <button
    type="button"
    class="cai-launcher"
    :class="{ 'cai-launcher--hidden': open }"
    title="Chat AI (Ctrl+Shift+J)"
    aria-label="Open Chat AI"
    @click="toggle()"
  >
    <span class="cai-launcher-mark">AI</span>
  </button>

  <aside
    class="cai-panel"
    :class="{ 'cai-panel--open': open, 'cai-panel--rtl': dir === 'rtl' }"
    :dir="dir"
    :aria-hidden="open ? 'false' : 'true'"
  >
    <header class="cai-header">
      <div class="cai-brand">
        <span class="cai-brand-mark">AI</span>
        <div class="cai-brand-text">
          <strong>Chat AI</strong>
          <span class="cai-brand-sub">{{ ui.sub }} · {{ mode || ui.modeAuto }}</span>
        </div>
      </div>
      <select class="cai-mode" :value="language" @change="setLanguage($event.target.value)" title="Language">
        <option v-for="l in languages" :key="l.code" :value="l.code">{{ l.native }}</option>
      </select>
      <button type="button" class="cai-icon-btn" :title="ui.sessions" @click="showSessions = !showSessions; refreshSessions()">☰</button>
      <button type="button" class="cai-icon-btn" title="Artifacts" @click="showArtifacts = !showArtifacts; loadArtifacts()">▣</button>
      <button type="button" class="cai-icon-btn" :title="ui.newChat" @click="newSession">{{ ui.newChat }}</button>
      <button type="button" class="cai-icon-btn" title="Close" @click="toggle(false)">×</button>
    </header>

    <div v-if="showArtifacts" class="cai-session-rail cai-artifact-rail">
      <div class="cai-session-actions">
        <strong>Artifacts</strong>
        <button type="button" class="cai-icon-btn" @click="loadArtifacts">↻</button>
      </div>
      <button
        v-for="a in artifacts"
        :key="a.name"
        type="button"
        class="cai-session-item"
        @click="openArtifact(a.name)"
      >
        <span>{{ a.title || a.artifact_type }}</span>
        <small>{{ a.artifact_type }}</small>
      </button>
      <p v-if="!artifacts.length" class="cai-brand-sub">No artifacts yet</p>
    </div>

    <div v-if="showSessions" class="cai-session-rail">
      <input class="cai-session-search" v-model="sessionQuery" :placeholder="ui.searchSessions" @input="refreshSessions" />
      <div class="cai-session-actions">
        <button type="button" class="cai-icon-btn" @click="renameSession">{{ ui.rename }}</button>
        <button type="button" class="cai-icon-btn" @click="togglePin">{{ sessionPinned ? ui.unpin : ui.pin }}</button>
        <button type="button" class="cai-icon-btn" @click="clearSession">{{ ui.clear }}</button>
        <button type="button" class="cai-icon-btn" @click="archiveSession">{{ ui.archive }}</button>
        <button type="button" class="cai-icon-btn" @click="deleteSession">{{ ui.delete }}</button>
      </div>
      <button
        v-for="s in sessions"
        :key="s.name"
        type="button"
        class="cai-session-item"
        :class="{ 'cai-session-item--active': s.name === session }"
        @click="openSession(s.name)"
      >
        <span class="cai-session-title">{{ s.is_pinned ? '📌 ' : '' }}{{ s.title || s.name }}</span>
      </button>
    </div>

    <div class="cai-messages" ref="messages">
      <div v-if="!messages.length" class="cai-empty">
        <p class="cai-empty-title">{{ ui.emptyTitle }}</p>
        <p class="cai-empty-hint">{{ ui.emptyHint }}</p>
      </div>

      <div
        v-for="msg in messages"
        :key="msg.id"
        class="cai-msg"
        :class="'cai-msg--' + msg.role"
      >
        <div class="cai-bubble">
          <div
            class="cai-bubble-text"
            :class="{ 'cai-bubble-text--typing': msg.typing }"
            v-html="formatText(msg.text)"
          ></div>

          <template v-for="(b, bi) in msg.blocks" :key="bi">
            <table v-if="b.type === 'table' && b.data" class="cai-table">
              <thead>
                <tr>
                  <th v-for="(h, hi) in (b.data.headers || [])" :key="hi">{{ h }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in (b.data.rows || [])" :key="ri">
                  <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                </tr>
              </tbody>
            </table>
            <div v-if="b.type === 'table'" class="cai-artifact-actions">
              <button type="button" class="cai-icon-btn" @click="copyText(JSON.stringify(b.data || {}))">{{ ui.copy }}</button>
            </div>
            <div v-if="b.type === 'links' && Array.isArray(b.data)" class="cai-links">
              <button
                v-for="(l, li) in b.data"
                :key="li"
                type="button"
                class="cai-link"
                @click="openLink(l.doctype, l.name)"
              >{{ l.doctype }}: {{ l.name }}</button>
            </div>
            <div v-if="b.type === 'plan' && b.data" class="cai-plan">
              <p v-if="(b.data.assumptions || []).length" class="cai-plan-assumptions">
                <strong>Assumptions</strong>
              </p>
              <ul v-if="(b.data.assumptions || []).length" class="cai-plan-list">
                <li v-for="(a, ai) in b.data.assumptions" :key="'a'+ai">{{ a }}</li>
              </ul>
              <ol v-if="(b.data.steps || []).length" class="cai-plan-steps">
                <li v-for="(s, si) in b.data.steps" :key="'s'+si">{{ s }}</li>
              </ol>
            </div>
            <span v-if="b.type === 'badge' || b.type === 'status'" class="cai-badge">{{ b.data && (b.data.label || b.data.text || b.data) }}</span>
            <details v-if="b.type === 'chart' || b.type === 'json' || b.type === 'artifact'" class="cai-artifact">
              <summary>{{ ui.artifact }}</summary>
              <pre class="cai-code"><code>{{ typeof b.data === 'string' ? b.data : JSON.stringify(b.data, null, 2) }}</code></pre>
              <button type="button" class="cai-icon-btn" @click="copyText(typeof b.data === 'string' ? b.data : JSON.stringify(b.data, null, 2))">{{ ui.copy }}</button>
            </details>
          </template>

          <div v-if="msg.needs_plan_approval" class="cai-confirm cai-confirm--plan">
            <button type="button" class="cai-btn cai-btn--primary" @click="confirmPlan(true)">{{ ui.planOk }}</button>
            <button type="button" class="cai-btn" @click="confirmPlan(false)">{{ ui.cancel }}</button>
          </div>

          <div v-if="msg.needs_confirmation" class="cai-confirm">
            <button type="button" class="cai-btn cai-btn--primary" @click="confirmPending(true)">{{ ui.confirm }}</button>
            <button type="button" class="cai-btn" @click="confirmPending(false)">{{ ui.cancel }}</button>
          </div>

          <div v-if="msg.role === 'assistant' && enableVoiceOut && ttsAvailable && msg.text" class="cai-voice-actions">
            <button
              type="button"
              class="cai-icon-btn"
              @click="speakingId === msg.id ? stopSpeaking() : speak(msg)"
            >{{ speakingId === msg.id ? ui.stop : ui.speak }}</button>
          </div>
        </div>
      </div>
    </div>

    <div
      class="cai-progress"
      :class="{ 'cai-progress--active': progress || busy || listening, 'cai-progress--listening': listening }"
    >
      <span v-if="progress || busy || listening" class="cai-progress-dot"></span>
      <span class="cai-progress-text">{{ progress || (busy ? ui.working : '') }}</span>
    </div>

    <footer class="cai-composer" :class="{ 'cai-composer--listening': listening }">
      <div v-show="paletteOpen" class="cai-palette">
        <button
          v-for="c in paletteItems"
          :key="c.name"
          type="button"
          class="cai-palette-item"
          @click="pickCommand(c)"
        >
          <strong>/{{ c.name }}</strong>
          <span>{{ c.description || c.label || '' }}</span>
        </button>
      </div>
      <textarea
        ref="input"
        class="cai-input"
        v-model="input"
        rows="2"
        :placeholder="ui.placeholder"
        @keydown="onKeydown"
      ></textarea>
      <div class="cai-composer-actions">
        <button
          v-if="enableVoiceOut && ttsAvailable"
          type="button"
          class="cai-icon-btn cai-speak-toggle"
          :class="{ 'cai-speak-toggle--on': autoSpeak }"
          :title="autoSpeak ? ui.speakOn : ui.speakOff"
          @click="toggleAutoSpeak"
        >{{ autoSpeak ? '🔊' : '🔇' }}</button>
        <button
          v-if="voiceAvailable"
          type="button"
          class="cai-icon-btn cai-mic"
          :class="{ 'cai-mic--on': listening, 'cai-mic--off': !enableVoiceIn }"
          :disabled="!enableVoiceIn || busy"
          :title="enableVoiceIn ? ui.mic : ui.micOff"
          @click="toggleMic"
        >{{ listening ? '■' : '🎤' }}</button>
        <button
          v-if="busy"
          type="button"
          class="cai-btn"
          @click="stopGeneration"
        >{{ ui.stopGen }}</button>
        <button
          v-else
          type="button"
          class="cai-btn cai-btn--primary cai-send"
          :disabled="!(input || '').trim()"
          @click="send"
        >{{ ui.send }}</button>
      </div>
    </footer>
  </aside>
</div>
`,
};

$(document).ready(function () {
	if (frappe.session && frappe.session.user && frappe.session.user !== "Guest") {
		chat_ai.sidebar.init();
	}
});
