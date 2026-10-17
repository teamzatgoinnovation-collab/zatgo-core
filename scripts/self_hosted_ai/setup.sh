#!/usr/bin/env bash
# Downloads the models (resumable) and starts the self-hosted AI stack.
# Usage: ./setup.sh [--no-start]      Env: BENCH_NETWORK (default devcontainer_default)
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p models

LLM_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
LLM_FILE="qwen2.5-3b-instruct-q4_k_m.gguf";            LLM_BYTES=2104932768
EMB_URL="https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q4_K_M.gguf"
EMB_FILE="nomic-embed-text-v1.5.Q4_K_M.gguf";          EMB_BYTES=84106624

fetch() {  # url file expected_bytes  -- retries and resumes; verifies the final size
  local url=$1 file=models/$2 want=$3 tries=0
  while [ "$(stat -c %s "$file" 2>/dev/null || echo 0)" -ne "$want" ]; do
    tries=$((tries + 1)); [ "$tries" -le 50 ] || { echo "giving up on $2 after 50 attempts" >&2; exit 1; }
    echo "downloading $2 (attempt $tries, $(( $(stat -c %s "$file" 2>/dev/null || echo 0) / 1048576 )) MiB so far)"
    curl -fL -C - --retry 3 --retry-delay 5 --connect-timeout 20 -o "$file" "$url" || sleep 5
  done
  echo "$2 complete ($want bytes)"
}

fetch "$LLM_URL" "$LLM_FILE" "$LLM_BYTES"
fetch "$EMB_URL" "$EMB_FILE" "$EMB_BYTES"

[ -f .env ] || { echo "SEARXNG_SECRET=$(openssl rand -hex 32)" > .env; chmod 600 .env; }

if [ "${1:-}" = "--no-start" ]; then echo "models ready; start with: docker compose up -d"; exit 0; fi
docker compose up -d
echo "waiting for the model server (loading a 3B model takes a minute on CPU)..."
for _ in $(seq 1 60); do
  docker exec zatgo-llm curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1 && break; sleep 5
done
cat <<MSG

Stack is up on network ${BENCH_NETWORK:-devcontainer_default}. Point Chat AI at it:

  bench --site <site> execute zatgo_core.chat_ai.setup_self_hosted.configure \\
    --kwargs '{"llm_url": "http://zatgo-llm:8080", "embed_url": "http://zatgo-embed:8080", "searxng_url": "http://zatgo-searxng:8080"}'
  bench --site <site> execute zatgo_core.chat_ai.setup_self_hosted.check
MSG
