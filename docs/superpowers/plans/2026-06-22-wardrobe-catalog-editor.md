# Wardrobe Catalog Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a route-based catalog page to browse, filter, and edit wardrobe item metadata persisted to SQLite.

**Architecture:** Extend the existing stdlib Python API with SQLite item read/update helpers and routes. Extend the current React/Vite app with lightweight client-side routing for `/chat` and `/catalog`, keeping chat behavior intact while adding a dense item table and grouped edit modal.

**Tech Stack:** Python 3 stdlib, SQLite, unittest, React, Vite, JavaScript, CSS.

---

## File Structure

- Modify `app/backend/db.py`: editable field constants, item list/detail helpers, type filtering, and update validation.
- Modify `app/backend/server.py`: `GET /api/items`, `GET /api/items/{item_id}`, and `PATCH /api/items/{item_id}` routes plus CORS support for PATCH.
- Create `tests/test_catalog_items.py`: backend regression tests using an isolated temporary SQLite database.
- Modify `app/frontend/src/api.js`: item list/detail/update calls.
- Modify `app/frontend/src/App.jsx`: route-aware app shell, extracted chat page, catalog page, grouped item editor.
- Modify `app/frontend/src/styles.css`: navigation, catalog table/list, segmented filters, and modal/editor styles.

## Task 1: Backend Item Persistence

- [ ] Write failing unittest coverage for listing items by type, fetching item details with images, saving editable fields, rejecting unknown fields, rejecting read-only fields, and normalizing blank numeric fields to null.
- [ ] Run `python3 -m unittest tests.test_catalog_items -v` and confirm failures are caused by missing helpers.
- [ ] Add minimal DB helpers in `app/backend/db.py`.
- [ ] Run `python3 -m unittest tests.test_catalog_items -v` and confirm the tests pass.

## Task 2: Backend HTTP Routes

- [ ] Add `/api/items` and `/api/items/{item_id}` GET routes.
- [ ] Add `/api/items/{item_id}` PATCH route.
- [ ] Allow PATCH in CORS headers.
- [ ] Run `python3 -m compileall app/backend` and `python3 -m unittest tests.test_catalog_items -v`.

## Task 3: Frontend Catalog Route

- [ ] Add API client methods for item list, item detail, and item update.
- [ ] Add lightweight routing for `/chat`, `/catalog`, and `/`.
- [ ] Preserve the existing chat UI and saved-outfits drawer behavior under `/chat`.
- [ ] Build `/catalog` with type filters, a dense item list, representative images, critical columns, and edit action.
- [ ] Build grouped editor modal with all editable catalog fields.
- [ ] Run `npm run build` from `app/frontend`.

## Task 4: End-To-End Verification

- [ ] Run backend syntax checks and backend tests.
- [ ] Run frontend build.
- [ ] Start backend and frontend dev servers.
- [ ] Verify `/catalog` loads, type filters work, an edit persists after refresh, and `/chat` still loads.
