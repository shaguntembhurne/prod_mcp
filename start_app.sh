#!/usr/bin/env bash
set -Eeuo pipefail

# Run from the project root (prod/) or invoke this file by its path.
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

VLLM_URL="${VLLM_URL:-http://127.0.0.1:8000/v1/models}"
DJANGO_HOST="${DJANGO_HOST:-127.0.0.1}"
DJANGO_PORT="${DJANGO_PORT:-8001}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

VLLM_PID=""
DJANGO_PID=""
FRONTEND_PID=""

cleanup() {
    echo
    echo "Stopping services started by this script..."
    for pid in "$FRONTEND_PID" "$DJANGO_PID" "$VLLM_PID"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo "Stopped."
}
trap cleanup EXIT INT TERM

for command in curl npm; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "Error: '$command' is required but was not found in PATH."
        exit 1
    }
done

# Use an already-active venv, or look in common project locations.
if [[ -n "${VIRTUAL_ENV:-}" && -f "${VIRTUAL_ENV}/bin/activate" ]]; then
    PYTHON_ACTIVATE="${VIRTUAL_ENV}/bin/activate"
elif [[ -f "$ROOT_DIR/venv/bin/activate" ]]; then
    PYTHON_ACTIVATE="$ROOT_DIR/venv/bin/activate"
elif [[ -f "$ROOT_DIR/backend/venv/bin/activate" ]]; then
    PYTHON_ACTIVATE="$ROOT_DIR/backend/venv/bin/activate"
else
    echo "Error: Python virtual environment not found."
    echo "Activate your venv first, or place it at prod/venv or prod/backend/venv."
    exit 1
fi

# 1. Start vLLM. inference/serve.sh defaults to GPU 1.
# To choose another GPU, run: GPU_ID=0 ./start_app.sh or GPU_ID=2 ./start_app.sh
echo "Starting vLLM..."
cd "$ROOT_DIR"
./inference/serve.sh &
VLLM_PID=$!

echo "Waiting for vLLM at $VLLM_URL ..."
until curl -fsS "$VLLM_URL" >/dev/null 2>&1; do
    if ! kill -0 "$VLLM_PID" 2>/dev/null; then
        echo "Error: vLLM exited before becoming ready. Check its logs."
        exit 1
    fi
    sleep 2
done
echo "vLLM is ready."

# 2. Start Django on 8001 because vLLM is using port 8000.
echo "Starting Django..."
(
    cd "$ROOT_DIR/backend"
    source "$PYTHON_ACTIVATE"
    python manage.py runserver "$DJANGO_HOST:$DJANGO_PORT"
) &
DJANGO_PID=$!

# 3. Start Vite frontend.
echo "Starting frontend..."
(
    cd "$ROOT_DIR/frontend"
    npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

echo
echo "Services launched:"
echo "  vLLM API: http://127.0.0.1:8000/v1"
echo "  Django:   http://${DJANGO_HOST}:${DJANGO_PORT}"
echo "  Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo
echo "Press Ctrl+C to stop the services started by this script."

# Keep the launcher alive and stop the stack if a service exits.
while true; do
    for pid in "$VLLM_PID" "$DJANGO_PID" "$FRONTEND_PID"; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "Error: one of the services stopped. Exiting."
            exit 1
        fi
    done
    sleep 2
done
