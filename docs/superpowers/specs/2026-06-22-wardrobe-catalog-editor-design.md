# Wardrobe Catalog Editor Design

Date: 2026-06-22

## Goal

Add a first-class catalog editor to the existing Wardrobe Stylist app so Varun can browse wardrobe items, filter them by type, and edit the metadata associated with an individual clothing item.

The editor persists changes to the app SQLite database only. `working/wardrobe_catalog.csv` remains import history and is no longer treated as the live source of truth.

## Approved Direction

Use a route-based extension of the existing local app:

- `/chat` keeps the existing stylist chat experience.
- `/catalog` becomes the wardrobe item management page.
- `/` should default or redirect to `/chat`.
- The backend exposes item read/update APIs backed by SQLite.
- The frontend uses the existing React/Vite app and adds lightweight client-side routing.

## Data Ownership

SQLite is the live catalog source of truth for this feature.

In scope:

- Read catalog items from the `items` and `item_images` tables.
- Update item metadata in the `items` table.
- Keep `item_id` stable so conversations, saved outfits, and image mappings continue to reference the same garment.

Out of scope:

- Writing changes back to `working/wardrobe_catalog.csv`.
- Editing image mappings.
- Uploading new images.
- Creating or deleting items.
- Editing conversations or saved outfit snapshots.
- Adding filters beyond item type.

## Backend API

Add the following endpoints:

- `GET /api/items?type=all|top|bottom|shoe`
- `GET /api/items/{item_id}`
- `PATCH /api/items/{item_id}`

`GET /api/items` returns a list suitable for the catalog page. Each item includes its editable metadata plus representative image data. The type filter is derived from the canonical prefixes `TOP-`, `BOT-`, and `SHOE-`, with the existing category fallback logic used as a backup.

`GET /api/items/{item_id}` returns the full item row and all mapped images for the edit view.

`PATCH /api/items/{item_id}` accepts only editable `items` fields. It rejects unknown fields and does not allow changes to:

- `item_id`
- `raw_json`
- `created_at`
- `updated_at`
- image records

On save, the backend updates `updated_at` and returns the refreshed item with images.

## Editable Fields

Expose all catalog metadata fields currently stored in SQLite, grouped by the catalog schema:

- Identity: category, sub-category, brand, colors, pattern.
- Shape & Fit: fit, rise, length, silhouette, neckline, drape notes, fit source.
- Material & Feel: fabric, weight, stretch, breathability, surface texture.
- Style & Occasion: formality, vibe tags, occasion tags, layering position.
- Seasonality: season, max comfortable temp.
- Condition & Usage: condition, wear frequency estimate.
- Color Science: color temperature, skin tone interaction, skin tone caution flag, contrast level.
- Pairing Utility: versatility score, role in outfit, volume/visual weight.
- Shoes Only: shoe type, sole profile, aesthetic range, top compatibility note.
- Client Notes: client notes.

`item_id`, images, timestamps, and internal raw JSON remain read-only or hidden.

Numeric fields:

- `formality`
- `versatility_score`

These should be stored as integers when present and nullable when blank.

## Catalog Page

The `/catalog` page is a dense, app-like management surface rather than a marketing page.

It shows:

- Representative image.
- Item ID.
- Type.
- Category and sub-category.
- Brand.
- Primary color.
- Fit.
- Condition.
- Versatility score.
- Client notes preview.
- Edit action.

The page supports a segmented type filter:

- All
- Tops
- Bottoms
- Shoes

No search, sorting, multi-select, or advanced filtering is required for this pass.

## Edit Experience

Selecting edit opens a large modal or focused edit view over the catalog page.

The editor shows:

- Item ID and representative image for orientation.
- All mapped images as read-only visual references.
- Field groups matching the catalog sections.
- Text inputs or textareas for free-form values.
- Number inputs for numeric scores.
- Save and cancel actions.
- A clear save status or error message.

The modal should be wide enough for long metadata fields like drape notes, skin tone interaction, and client notes. On small screens, it should collapse into a single-column full-height panel.

## Frontend Data Flow

On `/catalog` load:

1. Fetch `GET /api/items?type=all`.
2. Render the item list.
3. When the filter changes, fetch `GET /api/items?type=<selected>`.
4. When editing an item, fetch `GET /api/items/{item_id}` or use the list item if it already contains the full data.
5. Submit changes through `PATCH /api/items/{item_id}`.
6. Replace the updated item in the local list.

The chat route should continue to use the existing recommendation, conversation, citation, and saved-outfit APIs.

## Navigation

Add app navigation for:

- Chat
- Catalog

The current sidebar can host both links. The active route should be visibly selected. Existing chat controls remain available on the chat route.

## Error Handling

Backend:

- Return `404` when the item does not exist.
- Return `400` for invalid JSON, unknown fields, or non-editable fields.
- Return `400` when integer fields receive non-integer values.

Frontend:

- Show load failures in the catalog page.
- Keep the editor open if save fails.
- Show a saved confirmation after a successful update.

## Testing And Verification

Use automated tests for the new item update behavior where practical:

- Backend tests should cover field validation, read endpoints, SQLite persistence, and numeric field handling.
- Frontend verification should cover build success and manual interaction in the browser.

Manual verification:

- Import or use an existing SQLite catalog.
- Start the backend.
- Start the frontend.
- Open `/catalog`.
- Filter by Tops, Bottoms, and Shoes.
- Edit an item field, save, refresh, and confirm the value persists.
- Confirm `/chat` still loads and item citations still render.
