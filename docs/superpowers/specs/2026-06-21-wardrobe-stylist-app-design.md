# Wardrobe Stylist App Design

Date: 2026-06-21

## Goal

Build a local, chat-first wardrobe stylist web app that answers "what should I wear?" using only Varun's cataloged wardrobe items. The app should generate new outfit combinations, cite the local images for each recommended piece, persist chat conversations, and allow saving outfit options by fixed time-of-day and occasion labels.

The app must not hallucinate clothing items. Every recommended piece must resolve to an existing canonical `Item ID`.

## Approved Direction

Use a local full-stack app:

- Python backend API.
- React/Vite frontend.
- SQLite app database in a separate app data folder.
- One-time setup script to import `working/wardrobe_catalog.csv`.
- Provider-agnostic LLM layer, with OpenAI-compatible provider implemented first.
- `.env` configuration for credentials and model settings.
- Strict structured model output with rich stylist notes.
- Manual verification only. No automated tests for v1.

## Existing Inputs

The current source file is `working/wardrobe_catalog.csv`. It has one canonical row per clothing article, identified by `Item ID`. Some catalog rows reference multiple images through the `Item Image Name` column.

For v1:

- `Item ID` is the canonical garment identifier.
- `Item Image Name` is split into one or more citation image filenames.
- `Image References` helps choose a representative image.
- `Client notes` should be passed to the model because it contains user-specific context not always visible from automated cataloging.
- `Status` is ignored for recommendation filtering.
- `data/staging_outfit/` is ignored.

## App Data Ownership

The database becomes the app's source of truth after import. The CSV is a one-time seed for v1.

Out of scope for v1:

- Catalog editing in the app.
- Writing DB changes back to CSV.
- CSV export or backup.
- Catalog sync after import.

This keeps the first app focused on recommendation, citation, chat history, and saved outfits.

## Database Model

Use SQLite under a separate app data folder, for example `app/data/wardrobe.sqlite`.

### `items`

One row per canonical wardrobe item.

Important fields:

- `item_id`
- `category`
- `sub_category`
- `brand`
- `color_primary`
- `color_secondary`
- `pattern`
- `fit`
- `rise`
- `length`
- `silhouette`
- `neckline`
- `drape_notes`
- `fit_source`
- `fabric`
- `weight`
- `stretch`
- `breathability`
- `surface_texture`
- `formality`
- `vibe_tags`
- `occasion_tags`
- `layering_position`
- `season`
- `max_comfortable_temp_c`
- `condition`
- `wear_frequency_estimate`
- `color_temperature`
- `skin_tone_interaction`
- `skin_tone_caution_flag`
- `contrast_level`
- `versatility_score`
- `role_in_outfit`
- `volume_visual_weight`
- `shoe_type`
- `sole_profile`
- `aesthetic_range`
- `top_compatibility_note`
- `client_notes`

The importer should preserve useful metadata even when some fields are blank.

### `item_images`

One row per image mapped to an item.

Important fields:

- `id`
- `item_id`
- `filename`
- `path`
- `image_reference`
- `is_representative`

Representative image rule:

1. Prefer an image whose reference indicates a worn photo.
2. Otherwise use the first filename in `Item Image Name`.

The UI shows the representative image by default and lets the user expand to see all mapped images for the item.

### `conversations`

Persisted chat threads.

Important fields:

- `id`
- `title`
- `created_at`
- `updated_at`

### `messages`

Persisted user and assistant turns.

Important fields:

- `id`
- `conversation_id`
- `role`
- `content`
- `structured_payload_json`
- `created_at`

Assistant messages that contain outfit recommendations should store the validated structured payload.

### `saved_outfits`

Saved recommendation snapshots.

Important fields:

- `id`
- `title`
- `time_of_day`
- `occasion`
- `stylist_notes`
- `source_conversation_id`
- `source_message_id`
- `created_at`

Saved outfits preserve the exact stylist notes generated at recommendation time.

### `saved_outfit_items`

Join table from saved outfits to canonical item IDs.

Important fields:

- `saved_outfit_id`
- `item_id`
- `role`
- `sort_order`

## Fixed Labels

Time of day:

- `morning`
- `afternoon`
- `evening`
- `night`
- `all-day`

Occasion:

- `office`
- `date night`
- `party`
- `restaurant`
- `casual hangout`
- `boys night`
- `travel day`
- `beach/Goa`
- `concert`
- `brunch`

## Prompt Management

The default stylist prompt lives in the repo, for example `app/prompts/stylist.md`.

The current prompt should be incorporated:

> You are an expert in fashion and styling tips for men. I am 6 foot tall, Indian guy with a light brown complexion, athletic, oval face, I workout regularly. I usually dress for office, date nights, parties, restaurants or hanging out with the boys.
>
> Wardrobe catalog contains the unique list of all clothing items. The column Client notes contains notes from the client specifically that might not have been captured by the image categorizer automatically.
>
> DO NOT HALLUCINATE OR COME UP WITH CLOTHING ITEMS OF YOUR OWN

The design should allow a future app-level prompt override, but v1 can start with the repo prompt file and `.env` configuration.

## LLM Provider Layer

Define a provider-agnostic interface for outfit generation. Implement OpenAI-compatible first.

Configuration comes from `.env`. Required variables:

- `LLM_PROVIDER=openai`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

The backend sends catalog metadata to the model. It does not send image files in v1.

## Structured Recommendation Output

The model must return strict structured data, not free-form recommendations.

Each response should include outfit options. Default count is 3 unless the user explicitly asks for a different number.

Each outfit must include:

- `title`
- `time_of_day`
- `occasion`
- `item_ids`
- `stylist_notes`
- Optional short fields such as `why_it_works`, `wearing_notes`, or `cautions` if useful for a richer answer.

The stylist notes are required and should be rich enough to explain the silhouette, colors, formality, comfort, skin-tone interaction, and why the pieces work together.

## Recommendation Flow

For each user message:

1. Load conversation history.
2. Load the full item catalog from SQLite.
3. Build the model request from the default prompt, user message, conversation context, and catalog metadata.
4. Ask the provider for strict structured outfit recommendations.
5. Validate the structured payload.
6. Ensure each outfit contains at least one top, one bottom, and one shoe.
7. Validate every `Item ID` exists in the DB.
8. Enforce no exact repeated item set within the same conversation.
9. Attach item image citations from `item_images`.
10. Persist the user and assistant messages.
11. Return outfit cards to the frontend.

Uniqueness rule:

- Within a conversation, the exact same set of item IDs cannot be recommended again.
- Similar combinations are allowed if the full item set differs.

Invalid output handling:

- If the model references an invalid item, omits required item roles, repeats an exact prior outfit, or returns malformed data, retry with a correction prompt.
- If validation still fails after the configured retry limit, return a clear client-visible error.
- Do not display or save unvalidated recommendations.

## Frontend UX

Use the selected Single Stream layout.

The first screen is a chat-first experience:

- Chronological chat stream.
- User messages as text.
- Assistant recommendations as outfit cards.
- Main input for natural-language wardrobe questions.

Each outfit card shows:

- Title.
- Fixed time-of-day label.
- Fixed occasion label.
- Required top, bottom, and shoes.
- Optional jacket/accessory if recommended.
- Rich stylist notes.
- Representative image citation for each item.
- Expandable additional images for each item.
- Save button.

Saved outfits are reachable from a simple list, tab, or drawer and are grouped/filterable by the fixed labels.

Out of scope for v1 UI:

- Catalog editor.
- Settings screen for API keys.
- Per-item avoid/pin controls.
- Staging outfit browser.

## Manual Verification

No automated tests will be written for v1.

Manual checks before considering implementation done:

- Run the CSV import script and confirm canonical items and images import correctly.
- Confirm representative image selection prefers worn references and falls back to the first mapped filename.
- Start the backend and frontend locally.
- Send a styling request and confirm 3 outfit cards appear by default.
- Confirm every recommended item ID exists in the DB.
- Confirm each outfit has top + bottom + shoes.
- Confirm image citations render and expandable additional images work.
- Ask for more outfits in the same conversation and confirm exact item sets do not repeat.
- Trigger or simulate invalid model output and confirm the client receives a clear error.
- Save an outfit and confirm it appears in the saved outfit list with exact stylist notes.
- Reload the app and confirm conversations and saved outfits persist.

## Explicit Non-Goals For V1

- No automated tests.
- No use of `data/staging_outfit/`.
- No image or multimodal model inspection.
- No catalog editing.
- No DB-to-CSV write-back.
- No CSV export or backup feature.
- No app settings UI for credentials.
- No per-request avoid/pin controls.
- No filtering based on the `Status` column.
