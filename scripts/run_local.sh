#!/bin/bash
# Start the full Helpyy Hand local stack.
# Usage: ./scripts/run_local.sh
set -e

MODEL="${OLLAMA_MODEL:-gemma4:e4b}"

# ── 1. Check Ollama installed ──
if ! command -v ollama &>/dev/null; then
  echo "Ollama not found. Installing via Homebrew..."
  brew install ollama
fi

# ── 2. Start Ollama if not running ──
if curl -sf http://localhost:11434/api/tags &>/dev/null; then
  echo "Ollama already running."
else
  echo "Starting Ollama..."
  ollama serve &
  # Wait until ready
  for i in {1..30}; do
    curl -sf http://localhost:11434/api/tags &>/dev/null && break
    sleep 1
  done
  echo "Ollama ready."
fi

# ── 3. Pull model if not present ──
if ollama list | grep -q "$MODEL"; then
  echo "Model $MODEL already downloaded."
else
  echo "Downloading $MODEL (first time only, may take a few minutes)..."
  ollama pull "$MODEL"
fi

# ── 4. Start Docker services ──
echo "Starting Docker services..."
docker compose up --build -d

echo ""
echo "Helpyy Hand is running:"
echo "  App mobile:  http://localhost:5173"
echo "  Web widget:  http://localhost:3000"
echo "  API docs:    http://localhost:8000/docs"
echo "  ML Mock:     http://localhost:8001/docs"
echo "  Ollama:      http://localhost:11434"
echo ""
echo "To stop: docker compose down"
echo "To view logs: docker compose logs -f"
