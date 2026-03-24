#!/bin/bash
# Run the Media Downloader server locally (macOS / Linux)

cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python" ]; then
    echo "ERROR: Virtual environment not found."
    echo "Setting up virtual environment and installing dependencies..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

mkdir -p logs

# Read PORT from .env (default 8000)
PORT=8000
if [ -f ".env" ]; then
    ENV_PORT=$(grep -E "^PORT=" .env | cut -d'=' -f2)
    if [ -n "$ENV_PORT" ]; then
        PORT="$ENV_PORT"
    fi
fi

echo "Starting Media Downloader server on port $PORT..."
echo "Press Ctrl+C to stop."
echo ""

.venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port "$PORT"
