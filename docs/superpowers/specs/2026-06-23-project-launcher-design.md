# Project Launcher Design

## Goal

Create a root-level `script.sh` that starts the wardrobe app backend and frontend for local development.

## Design

The launcher uses loopback-only ports that avoid common prime/default choices: backend `8765` and frontend `8766`. Before starting either service, it checks each configured port and terminates any process currently listening there so this project can claim the ports deterministically.

The backend runs with `BACKEND_HOST=127.0.0.1` and `BACKEND_PORT=8765` via `python3 app/backend/server.py`. The frontend runs from `app/frontend` with `VITE_API_BASE_URL=http://127.0.0.1:8765` and `npm run dev -- --port 8766 --strictPort`.

The script tracks the PIDs it starts and traps `INT`/`TERM`/`EXIT` to stop its own child processes cleanly.

## Testing

Add a unittest that verifies the script exists, is executable, passes `bash -n`, uses the approved non-default ports, invokes the expected backend and frontend commands, and includes port cleanup plus signal traps.
