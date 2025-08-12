#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Booting Unzip bot for Koyeb (Web Service mode)"

# ---------------------------------------------------------
# Optional: load .env locally; on Koyeb you set env in the UI
# ---------------------------------------------------------
if [[ -f .env ]]; then
  # shellcheck disable=SC2046
  export $(grep -vE '^\s*#' .env | xargs -0 -I{} bash -c 'echo {}' 2>/dev/null || true)
fi

# Sensible defaults
: "${RPC_SECRET:=changeme}"
: "${PORT:=8080}"

# ---------------------------------------------------------
# Start aria2c RPC (used by the bot for fast downloads)
# ---------------------------------------------------------
echo "▶️  Starting aria2c (RPC on, secret set)"
aria2c \
  --enable-rpc \
  --rpc-listen-all=true \
  --rpc-allow-origin-all \
  --rpc-secret="${RPC_SECRET}" \
  --max-connection-per-server=16 \
  --split=16 \
  --min-split-size=1M \
  --file-allocation=none \
  --continue=true \
  --follow-torrent=true \
  --max-overall-download-limit=0 \
  --summary-interval=0 \
  --daemon=true

# ---------------------------------------------------------
# Tiny HTTP server for Koyeb health checks (Web Service)
# ---------------------------------------------------------
if [ -n "${PORT:-}" ]; then
  python3 -m http.server "$PORT" >/dev/null 2>&1 &
  echo "Healthcheck server on :$PORT"
fi
# ---------------------------------------------------------
# Run the bot
# ---------------------------------------------------------
echo "🤖 Starting the bot..."
exec python3 -m unzipbot
