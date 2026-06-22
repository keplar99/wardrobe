# Wardrobe Catalog Import And Review Design

Date: 2026-06-22

## Goal

Add a first-class import workflow to the Wardrobe Stylist app so Varun can upload 1 to 100 item images, save those images into the local canonical image store, generate catalog metadata in batches, review the generated drafts, and publish approved items into the live catalog viewer.

Uploaded images must not become live catalog items immediately. They enter a draft queue first. Generated metadata becomes reviewable draft data, and only approved drafts are copied into the live `items` and `item_images` tables used by `/catalog` and stylist recommendations.

## Approved Direction

Use a backend-backed draft queue:

- `/chat` remains the stylist chat route.
- `/catalog` remains the live catalog viewer/editor for published items.
- `/catalog/import` becomes the import, processing, and draft review route.
- Uploaded files are copied into `data/Raw Images/` as the canonical local assets before any metadata generation happens.
- The backend stores upload batches, uploaded images, generated drafts, and draft observations in SQLite.
- Processing runs in batches, defaulting to 10 images per run, following the wardrobe cataloging skill rules.
- Publishing a draft creates stable live catalog records and makes the item visible in the catalog viewer.

## Data Ownership

SQLite remains the live app source of truth.

In scope:

- Canonicalize uploaded image files into `data/Raw Images/`.
- Track upload batches and per-image processing status in SQLite.
- Store generated item drafts in SQLite before publication.
- Let the user review, edit, publish, reject, or leave generated drafts pending.
- Show only published items in `/catalog` and recommendation prompts.

Out of scope:

- Writing new rows back to `working/wardrobe_catalog.csv`.
- Updating the legacy `image_reference_map.csv` or `observations_open_questions.csv`.
- Real-time multi-user collaboration.
- Background processing that continues after the local backend process exits.
- Automatic deletion of canonical image files when a draft is rejected.

## Database Model

Add draft-oriented tables alongside the existing live tables.

`import_batches`:

- `id`
- `status`: `uploaded`, `processing`, `needs_review`, `partially_published`, `published`, `failed`
- `original_file_count`
- `uploaded_file_count`
- `processed_file_count`
- `published_item_count`
- `error_message`
- `created_at`
- `updated_at`

`import_images`:

- `id`
- `batch_id`
- `original_filename`
- `canonical_filename`
- `canonical_path`
- `content_hash`
- `status`: `uploaded`, `processing`, `processed`, `failed`, `rejected`, `published`
- `draft_item_id`
- `error_message`
- `created_at`

`draft_items`:

- `id`
- `batch_id`
- `status`: `generated`, `needs_review`, `published`, `rejected`
- `proposed_item_id`
- all editable catalog metadata fields from `items`
- `image_reference`
- `generation_notes`
- `validation_warnings_json`
- `raw_model_json`
- `published_item_id`
- `created_at`
- `updated_at`

`draft_item_images`:

- `id`
- `draft_item_id`
- `import_image_id`
- `image_reference`
- `is_representative`

`draft_observations`:

- `id`
- `batch_id`
- `draft_item_id`
- `category`
- `observation_type`
- `detail`
- `action_needed`

The draft schema intentionally mirrors the live catalog fields so the existing editor field groups can be reused for review.

## Canonical Image Handling

The upload endpoint accepts multiple image files in one request.

For each file, the backend:

1. Validates that the file is an allowed image type.
2. Computes a content hash.
3. Copies the file into `data/Raw Images/`.
4. Uses a collision-safe canonical filename such as `upload_YYYYMMDD_HHMMSS_<short-hash>_<sanitized-original-name>.<ext>`.
5. Creates an `import_images` row linked to the upload batch.

The canonical file path is the only image path used by later draft and live catalog records. The user's source location on the computer is never referenced after upload.

## Batch Processing

The import route supports processing a batch in chunks, defaulting to 10 uploaded images per call. This keeps long uploads manageable and matches the existing wardrobe cataloging workflow.

Processing flow:

1. Select the next `uploaded` or retryable `failed` images for the batch.
2. Send those images plus the wardrobe cataloging rules to the configured LLM provider.
3. Ask for strict JSON matching the draft catalog schema.
4. Deduplicate within the current chunk and against published catalog items.
5. Store generated draft items, draft-image mappings, and draft observations.
6. Mark processed images as `processed` or `failed`.
7. Update the import batch status and counters.

The processor must flag uncertain duplicates rather than silently merging them. If a group of images appears to show the same item, it can generate one draft item mapped to multiple images. If the model is uncertain, it should generate separate drafts with warnings.

## AI Contract

The generation prompt uses the wardrobe cataloging skill as the operational source:

- Worn photos override flat lays for fit, silhouette, and drape.
- Brands are not guessed.
- Color names must be precise.
- Skin-tone caution rules are applied.
- Versatility is not inflated.
- Possible duplicates are flagged, not silently merged.
- Non-applicable fields are blank, while deliberate solid-color secondary fields use `—`.

The JSON schema requires:

- Draft item metadata for the full catalog field set.
- Per-image references.
- Representative image choice.
- Duplicate or merge confidence.
- Observations and warnings.

The model can propose an item prefix, category, and metadata, but final live `item_id` assignment happens on publish.

## Publish Flow

Publishing a draft:

1. Validates editable catalog fields with the same normalization rules used by the current catalog editor.
2. Assigns the next stable live item ID for the appropriate prefix: `TOP-XX`, `BOT-XX`, `SHOE-XX`, or `ACC-XX`.
3. Inserts one row into `items`.
4. Inserts linked rows into `item_images` using the canonical image paths.
5. Marks the draft item and linked import images as `published`.
6. Returns the published live item so the UI can refresh the catalog list.

Published items appear in `/catalog` and become eligible for stylist recommendations immediately.

## Backend API

Add these endpoints:

- `POST /api/import-batches`
- `GET /api/import-batches`
- `GET /api/import-batches/{batch_id}`
- `POST /api/import-batches/{batch_id}/process`
- `PATCH /api/draft-items/{draft_item_id}`
- `POST /api/draft-items/{draft_item_id}/publish`
- `POST /api/draft-items/{draft_item_id}/reject`

`POST /api/import-batches` accepts multipart image uploads and returns the created batch with import image records.

`POST /api/import-batches/{batch_id}/process` accepts an optional `limit` and processes the next chunk. The initial default is 10.

`PATCH /api/draft-items/{draft_item_id}` accepts the same editable metadata fields as the live item editor plus these draft-only fields: `status`, `generation_notes`, and `validation_warnings_json`.

`POST /api/draft-items/{draft_item_id}/publish` publishes one reviewed draft into the live catalog.

`POST /api/draft-items/{draft_item_id}/reject` marks a draft as rejected while leaving the canonical image file and audit rows intact.

## Frontend Experience

Add an Import action to the catalog management surface and a route at `/catalog/import`.

The import page includes:

- A file picker that accepts multiple images.
- Upload progress and the created batch summary.
- A batch list with status, counts, and last error.
- A process-next-batch action.
- A draft review list filtered by `Pending`, `Processing`, `Needs Review`, `Published`, and `Rejected`.
- Draft item cards or rows with representative image, proposed category, proposed type, brand, color, warnings, and actions.

Draft review uses the existing catalog editor field groups:

- The user can edit generated metadata before publishing.
- The user can preview all linked images.
- Validation warnings and duplicate cautions stay visible while editing.
- Publishing updates the draft row state and removes it from the pending review queue.

The main `/catalog` route continues to show only published live catalog items.

## Error Handling

Backend:

- Reject unsupported file types with `400`.
- Return `404` for missing batches or drafts.
- Return `400` for invalid draft updates.
- Store per-image and per-batch processing failures instead of losing the upload batch.
- Keep already processed drafts if a later chunk fails.

Frontend:

- Show upload failures without clearing selected files.
- Show processing failures at the batch and image level.
- Keep draft review forms open when save or publish fails.
- Show clear published, rejected, and failed states.

## Testing And Verification

Automated backend tests should cover:

- Multipart upload creates an import batch and canonical files.
- Duplicate filenames produce unique canonical names.
- Draft batch status and counters update correctly.
- Draft item updates reuse catalog field validation.
- Publishing inserts live `items` and `item_images` rows.
- Published items appear in `list_catalog_items`.
- Rejected drafts do not appear in the live catalog.

Frontend verification should cover:

- Build success.
- Import route renders.
- Multiple image selection and upload.
- Batch processing action states.
- Draft edit, publish, reject, and catalog refresh.

Manual verification:

- Start the backend and frontend.
- Upload a small mixed set of images.
- Confirm canonical files exist under `data/Raw Images/`.
- Process one chunk.
- Review and edit generated metadata.
- Publish one item.
- Confirm the item appears in `/catalog` and can be edited.
- Confirm rejected drafts stay out of `/catalog`.
