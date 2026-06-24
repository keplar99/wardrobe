#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8765}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-8766}"
VITE_API_BASE_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"

BACKEND_PID=""
FRONTEND_PID=""

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

kill_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti tcp:"${port}" -sTCP:LISTEN 2>/dev/null || true)"

  if [[ -z "${pids}" ]]; then
    return 0
  fi

  echo "Port ${port} is occupied by PID(s): ${pids//$'\n'/ }. Stopping them..."
  for pid in ${pids}; do
    kill "${pid}" 2>/dev/null || true
  done

  sleep 1

  for pid in ${pids}; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" 2>/dev/null || true
    fi
  done
}

cleanup() {
  local exit_code=$?
  trap - INT TERM EXIT

  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi

  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi

  exit "${exit_code}"
}

main() {
  require_command lsof
  require_command python3
  require_command npm

  kill_port "${BACKEND_PORT}"
  kill_port "${FRONTEND_PORT}"

  echo "Starting backend on http://${BACKEND_HOST}:${BACKEND_PORT}"
  (
    cd "${ROOT_DIR}"
    BACKEND_HOST="${BACKEND_HOST}" BACKEND_PORT="${BACKEND_PORT}" python3 app/backend/server.py
  ) &
  BACKEND_PID=$!

  echo "Starting frontend on http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  (
    cd "${ROOT_DIR}/app/frontend"
    VITE_API_BASE_URL="${VITE_API_BASE_URL}" npm run dev -- --port "${FRONTEND_PORT}" --host "${FRONTEND_HOST}" --strictPort
  ) &
  FRONTEND_PID=$!

  echo
  echo "Wardrobe app is starting:"
  echo "  Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
  echo "  Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  echo
  echo "Press Ctrl+C to stop both servers."

  while kill -0 "${BACKEND_PID}" 2>/dev/null && kill -0 "${FRONTEND_PID}" 2>/dev/null; do
    sleep 1
  done

  wait "${BACKEND_PID}" "${FRONTEND_PID}"
}

trap cleanup INT TERM EXIT
main "$@"
