# Wardrobe Stylist App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user explicitly requested no automated tests; use the manual verification commands listed here.

**Goal:** Build the v1 local wardrobe stylist app from the approved design spec.

**Architecture:** A stdlib Python HTTP API owns SQLite, CSV import, validation, OpenAI-compatible Responses API calls, image serving, conversations, and saved outfits. A React/Vite frontend provides the single-stream chat UI, outfit cards with expandable citations, and a saved-outfits drawer.

**Tech Stack:** Python 3.13 stdlib, SQLite, React, Vite, JavaScript, CSS, OpenAI-compatible HTTPS Responses API.

---

## File Structure

- Create `app/backend/schema.sql`: SQLite schema.
- Create `app/backend/db.py`: connection helpers, migrations, catalog/message/outfit persistence.
- Create `app/backend/import_catalog.py`: one-time CSV import from `working/wardrobe_catalog.csv`.
- Create `app/backend/llm.py`: provider interface and OpenAI-compatible implementation using strict JSON schema.
- Create `app/backend/recommender.py`: prompt construction, output validation, retry handling, citation attachment.
- Create `app/backend/server.py`: stdlib HTTP API and image-serving endpoint.
- Create `app/prompts/stylist.md`: default stylist prompt.
- Create `app/frontend/package.json`, `index.html`, `src/*`: React/Vite UI.
- Create `.env.example`: required backend/frontend environment variables.
- Modify `.gitignore`: ignore local app DB, `.env`, dependency folders, and build outputs.

## Task 1: Backend DB And Catalog Import

**Files:**
- Create: `app/backend/schema.sql`
- Create: `app/backend/db.py`
- Create: `app/backend/import_catalog.py`
- Modify: `.gitignore`

- [ ] Create the SQLite schema with canonical `items`, `item_images`, `conversations`, `messages`, `saved_outfits`, and `saved_outfit_items` tables.
- [ ] Implement DB helpers for opening the configured database path, applying schema, loading items, loading images, inserting conversations/messages, and saving outfits.
- [ ] Implement the one-time importer that reads `working/wardrobe_catalog.csv`, maps `Item ID` to `items`, splits pipe-separated `Item Image Name` values into `item_images`, and marks representative images by preferring worn references.
- [ ] Add local generated files to `.gitignore`: `.env`, `app/data/*.sqlite*`, `app/frontend/node_modules`, `app/frontend/dist`.
- [ ] Manually verify import with `python3 app/backend/import_catalog.py --reset`, then inspect counts with `python3 app/backend/import_catalog.py --summary`.

## Task 2: LLM Provider And Recommendation Validation

**Files:**
- Create: `app/backend/llm.py`
- Create: `app/backend/recommender.py`
- Create: `app/prompts/stylist.md`
- Create: `.env.example`

- [ ] Add the approved stylist prompt to `app/prompts/stylist.md`.
- [ ] Add `.env.example` documenting `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `WARDROBE_DB_PATH`, and backend/frontend ports.
- [ ] Implement env loading from `.env` without external dependencies.
- [ ] Implement OpenAI-compatible Responses API calls with strict JSON schema through `https://api.openai.com/v1/responses`.
- [ ] Implement structured output parsing from `output_text` or response message text parts.
- [ ] Implement recommendation validation: valid item IDs only, top + bottom + shoes required, fixed labels only, no exact repeated item set per conversation, and rich stylist notes required.
- [ ] Implement retry-on-invalid-output and client-visible failure after retry limit.

## Task 3: Backend HTTP API

**Files:**
- Create: `app/backend/server.py`
- Modify: `app/backend/db.py`
- Modify: `app/backend/recommender.py`

- [ ] Implement `GET /api/health`.
- [ ] Implement `GET /api/conversations` and `POST /api/conversations`.
- [ ] Implement `GET /api/conversations/{id}/messages`.
- [ ] Implement `POST /api/conversations/{id}/messages` to persist the user message, generate recommendations, persist the assistant payload, and return outfit cards with citations.
- [ ] Implement `GET /api/saved-outfits`.
- [ ] Implement `POST /api/saved-outfits`.
- [ ] Implement `GET /api/item-images/{image_id}` to stream local image files from `data/Raw Images/`.
- [ ] Implement CORS for local Vite development.
- [ ] Manually verify `GET /api/health` after starting the backend.

## Task 4: React/Vite Frontend

**Files:**
- Create: `app/frontend/package.json`
- Create: `app/frontend/index.html`
- Create: `app/frontend/src/main.jsx`
- Create: `app/frontend/src/App.jsx`
- Create: `app/frontend/src/api.js`
- Create: `app/frontend/src/styles.css`

- [ ] Build a single-stream chat UI with conversation selection/new conversation controls.
- [ ] Render assistant recommendation payloads as outfit cards.
- [ ] Show title, fixed labels, rich stylist notes, item list, representative image, expandable additional images, and save button.
- [ ] Add a saved-outfits drawer/list grouped by time of day and occasion.
- [ ] Show backend/model validation errors clearly in the chat stream.
- [ ] Keep the UI dense and app-like, not a marketing page.

## Task 5: Manual Verification And Dev Server

**Files:**
- Modify only files required by failures found during manual verification.

- [ ] Run `python3 app/backend/import_catalog.py --reset`.
- [ ] Run `python3 app/backend/import_catalog.py --summary`.
- [ ] Run Python syntax checks with `python3 -m compileall app/backend`.
- [ ] Install frontend dependencies with `npm install` in `app/frontend` if needed.
- [ ] Build the frontend with `npm run build`.
- [ ] Start the backend.
- [ ] Start the frontend dev server.
- [ ] Confirm the app URL loads.
- [ ] Confirm health/imported catalog state in the UI or backend response.

## Self-Review Checklist

- The plan covers the approved design spec.
- The plan contains no automated test creation.
- The plan keeps catalog editing, CSV export, staging outfits, status filtering, image vision, and pin/avoid controls out of scope.
- The backend can run with Python stdlib only.
- The frontend can be served through Vite and can use backend image citations.
