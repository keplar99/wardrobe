# Saved Outfits Page And Soft Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class saved outfits page, two-step saved outfit removal, and catalog soft deletion that preserves saved outfit history.

**Architecture:** Keep the existing Python API and React/Vite app. Add `deleted_at` to catalog items, filter active items for recommendations, expose saved outfit deletion, and reuse the existing `OutfitCard` component on a new `/saved` route.

**Tech Stack:** Python `unittest`, SQLite, stdlib HTTP server, React 19, Vite, lucide-react.

---

### File Structure

- Modify `app/backend/schema.sql`: add nullable `deleted_at` to new `items` tables.
- Modify `app/backend/db.py`: migrate existing DBs, soft-delete catalog items, filter active recommendation data, preserve deleted items in saved outfits, delete saved outfit snapshots.
- Modify `app/backend/server.py`: add `DELETE /api/saved-outfits/{id}` and route catalog deletes to soft delete.
- Modify `tests/test_catalog_items.py`: add backend tests for soft deletion and saved outfit deletion.
- Modify `app/frontend/src/api.js`: add `deleteSavedOutfit`.
- Modify `app/frontend/src/App.jsx`: add `/saved` route/nav/page, remove drawer, reuse `OutfitCard` with save/remove variants, mark removed citations.
- Modify `app/frontend/src/styles.css`: add saved page styles and removed citation styling.

### Task 1: Backend Tests

**Files:**
- Modify: `tests/test_catalog_items.py`

- [ ] **Step 1: Write failing tests**

Add tests that prove catalog delete is soft, prompt data excludes deleted items, saved outfits still include deleted item records, and saved outfit deletion removes only the saved snapshot.

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run python -m unittest tests/test_catalog_items.py`

Expected: failures because `deleted_at`, `list_items_for_prompt` filtering, `delete_saved_outfit`, and saved outfit preservation are not implemented.

### Task 2: Backend Implementation

**Files:**
- Modify: `app/backend/schema.sql`
- Modify: `app/backend/db.py`
- Modify: `app/backend/server.py`

- [ ] **Step 1: Add schema/migration support**

Add `deleted_at TEXT` to `items` and an idempotent migration in `apply_schema` for existing SQLite files.

- [ ] **Step 2: Implement active item filtering and soft delete**

Make catalog list/prompt/category functions use active items. Change `delete_catalog_item` to set `deleted_at`.

- [ ] **Step 3: Implement saved outfit deletion**

Add `delete_saved_outfit(conn, saved_outfit_id)` and `DELETE /api/saved-outfits/{id}`.

- [ ] **Step 4: Run backend tests**

Run: `uv run python -m unittest tests/test_catalog_items.py`

Expected: all tests pass.

### Task 3: Frontend Saved Page

**Files:**
- Modify: `app/frontend/src/api.js`
- Modify: `app/frontend/src/App.jsx`
- Modify: `app/frontend/src/styles.css`

- [ ] **Step 1: Add API client and route**

Add `/saved` to the route list and navigation. Add `api.deleteSavedOutfit(id)`.

- [ ] **Step 2: Replace drawer with saved page**

Remove drawer state/rendering. Make chat's Saved button navigate to `/saved`.

- [ ] **Step 3: Reuse `OutfitCard`**

Add optional `action` props to `OutfitCard` so chat uses save and saved page uses a two-step remove action.

- [ ] **Step 4: Mark removed item citations**

In `CitationItem`, show a removed label and subdued styling when `item.deleted_at` is present.

### Task 4: Verification

**Files:**
- Existing app files only.

- [ ] **Step 1: Run backend tests**

Run: `uv run python -m unittest tests/test_catalog_items.py`

Expected: all tests pass.

- [ ] **Step 2: Build frontend**

Run: `npm run build` in `app/frontend`

Expected: Vite build succeeds.

- [ ] **Step 3: Start local servers if needed**

Start backend and frontend, then open `/saved`, `/chat`, and `/catalog` to verify routing and rendering.
