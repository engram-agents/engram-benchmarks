#!/usr/bin/env bash
# P2 step 1: vanilla Claude Code on the local model, fully isolated from the host's real Claude Code config, plugins and ENGRAM graph.
: "${BEAM_HELLO_DIR:?set BEAM_HELLO_DIR (scratch directory that already contains work/, cc-home/ and eh/; outputs are written into it)}"
BEAM_OLLAMA_URL="${BEAM_OLLAMA_URL:-http://localhost:11434}"  # privacy-scan: allow (Ollama's documented default endpoint)
S=$BEAM_HELLO_DIR
cd "$S/work" || exit 9
env -i MODEL="$MODEL" TAG="$TAG" PATH="$PATH" TERM=dumb HOME="$S/cc-home" CLAUDE_CONFIG_DIR="$S/cc-home/.claude" ENGRAM_HOME="$S/eh" \
  ANTHROPIC_BASE_URL="$BEAM_OLLAMA_URL" ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY= \
  CLAUDE_CODE_AUTO_COMPACT_WINDOW=120000 DISABLE_TELEMETRY=1 DISABLE_AUTOUPDATER=1 \
  timeout 600 claude -p "Reply with the single word READY, then on a new line list the names of the tools you can call, comma-separated." \
  --model "${MODEL:-qwen3.8:27b}" --output-format json > "$S/vanilla-hello${TAG}.json" 2> "$S/vanilla-hello${TAG}.err"
echo "claude exit=$?"
