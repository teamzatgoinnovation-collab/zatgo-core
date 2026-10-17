# Self-hosted AI for Chat AI (no external API)

Chat AI talks to any OpenAI-compatible server, so it can run entirely on your own hardware:

| Capability | Self-hosted service | Needs |
|---|---|---|
| Chat, tool calling, streaming | `llama.cpp` server (`zatgo-llm`) running Qwen2.5-3B-Instruct (Q4_K_M, ~2.1 GB) | ~4 GB RAM |
| File search embeddings | `llama.cpp` server (`zatgo-embed`) running nomic-embed-text-v1.5 (~84 MB) | ~0.5 GB RAM |
| Web search | SearXNG (`zatgo-searxng`), no key, no account | ~0.3 GB RAM |

Everything lives in `scripts/self_hosted_ai/` and joins the bench's Docker network (`BENCH_NETWORK`,
default `devcontainer_default`); nothing is published to the host. Models are not committed (`models/` is gitignored).

## Set up

```bash
cd scripts/self_hosted_ai
./setup.sh                       # downloads the models (resumable), starts the three containers
bench --site <site> execute zatgo_core.chat_ai.setup_self_hosted.configure \
  --kwargs '{"llm_url": "http://zatgo-llm:8080", "embed_url": "http://zatgo-embed:8080", "searxng_url": "http://zatgo-searxng:8080"}'
bench --site <site> execute zatgo_core.chat_ai.setup_self_hosted.check     # reachability of each service
```

`configure` sets Chat AI Settings: provider *Custom OpenAI-compatible*, the chat endpoint and model,
the embedding provider/endpoint/model, SearXNG as the web search provider, a context window that
suits a small model (8192) and a 300 s request timeout (CPU inference is slow). It never touches API
keys. Then switch the module on for the site (ZG System Settings → Enable Chat AI).

Other servers work the same way (Ollama, vLLM, LM Studio): pass their URL as `llm_url` and the model
name as `model`. Another model: set `LLM_FILE` / `LLM_ALIAS` in `.env` and place the GGUF in `models/`.

## What to expect

- **Speed.** CPU-only inference of a 3B model is slow (single-digit tokens per second on 4 cores). Each
  turn makes a short planning call before the answer, so replies take a while; Stop works at any time.
  A GPU host or a smaller/faster model changes this far more than any setting.
- **Quality.** A 3B model is noticeably weaker than hosted frontier models at multi-step tool use,
  long documents and Arabic. File search and the calculator/table tools help because the numbers are
  computed, not generated.
- **No vision.** The text model cannot read images; image uploads are refused with a clear message.
  Use a vision-capable GGUF + its multimodal projector, or a hosted vision model, if you need that.
- **SearXNG** has no API key but still asks public search engines on your behalf; results depend on them.

## Security notes

- The three services are reachable only inside the bench network. Do not publish their ports.
- `fetch_url` keeps its public-address-only rule; the SearXNG URL is an administrator setting and is
  deliberately allowed to be internal.
- The SearXNG secret is generated into `scripts/self_hosted_ai/.env` (gitignored, mode 600).

## Verification status


### Run on 2026-10-17 (4 CPU cores, 7 GB RAM, no GPU; Qwen2.5-3B Q4_K_M, nomic-embed-text v1.5, SearXNG)

Real calls through `chat.send`, no mocks; the stack was reached from the Frappe container by service name.

| Turn | Result | Time |
|---|---|---|
| "In one sentence, what is VAT?" | correct one-line answer | 63 s |
| "calculate 1250000 x 0.15 with the calculator" | model called `calculator`; answered 187500.0 | 90 s |
| Upload `policy.txt` (6 chunks, all embedded), "compressor warranty?" | answered "36 month" from the file | 117 s (upload itself 2 s) |
| "Search the web: what is ZATCA e-invoicing phase 2?" | SearXNG returned 5 real results, shown as sources; answer cited the guideline PDF | 139 s |

Direct model probe: first token 1.7 s, about 8.5 tokens/s, correct streamed tool call, usage reported.

**Conclusion:** functionally everything works with no external API. It is *slow* on this hardware
(1-2 minutes per turn), because each turn is a planning call plus the answer with a long system
prompt, both evaluated on 4 CPU cores. It is practical for light use or demos here; for real use run the same
stack on a GPU host or a faster CPU. Not verified here: Arabic quality, long documents, a GPU run, the
chat panel UI against this model (the panel was verified against a scripted provider).
