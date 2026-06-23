# Saved Outfits Page And Soft Delete Design

Date: 2026-06-22

## Goal

Move saved outfits out of the chat side drawer and into a first-class `/saved` page. Saved outfits should render with the same rich outfit card used in chat, including stylist notes, why/wear/caution text, item citations, and image preview behavior.

Add a two-step remove action for saved outfits.

Change catalog item deletion to soft deletion. Removed catalog items should not be used for new recommendations, but historical saved outfits should still show them with a clear removed indication.

## Approved Direction

Use route-based navigation alongside the existing app pages:

- `/chat` remains the recommendation chat.
- `/catalog` remains the catalog editor.
- `/saved` shows saved outfits as a card grid.
- `/` continues to default to `/chat`.

The saved page reuses the existing `OutfitCard` presentation component so saved outfits match chat recommendation cards. The saved page passes a remove action into the card instead of the chat save action.

## Saved Outfit Removal

Add a backend endpoint:

- `DELETE /api/saved-outfits/{id}`

The endpoint deletes the saved outfit snapshot and its join rows. This is a real delete because it only removes the user's saved bookmark, not catalog data.

Frontend behavior:

1. First click changes the remove button into a confirmation state.
2. Second click calls the delete endpoint.
3. On success, remove the saved outfit from local state and show a status line.
4. On failure, keep the card visible and show the error.

## Catalog Soft Delete

Add a nullable deletion marker to catalog items, `deleted_at`.

Catalog item delete should become:

- `DELETE /api/items/{item_id}` sets `deleted_at = CURRENT_TIMESTAMP`.
- It does not delete `items` rows.
- It does not delete `item_images`.
- It does not break saved outfit history.

Deleted items are unavailable for new styling:

- `list_items_for_prompt` returns only active items.
- recommendation validation accepts only active item IDs.
- category validation for top/bottom/shoe uses only active items.

Catalog browsing should show only active items for this pass. The deletion action still removes the item from the visible catalog list after a successful soft delete.

Saved outfits should continue to include deleted items. Each deleted item citation should render with an indication such as "Removed from catalog" and subdued styling.

## Data Flow

On app boot, fetch saved outfits as before and keep them in app state.

On `/saved`, render:

- topbar with saved-outfit title and count/status.
- empty state when no saved outfits exist.
- grid of `OutfitCard` cards.

Each saved outfit from the backend already includes joined item records. Add enough fields to the saved outfit payload for `OutfitCard` compatibility:

- `item_ids`
- `item_roles`
- `items`
- existing title, labels, and stylist notes

## Testing

Backend tests should cover:

- deleting a catalog item marks it deleted without removing images.
- deleted catalog items are excluded from prompt items and active recommendation validation.
- saved outfits still return deleted items with the deletion marker.
- saved outfit deletion removes the saved snapshot and join rows.

Frontend verification should cover:

- build succeeds.
- `/saved` renders saved outfit cards with the same card component as chat.
- two-step remove deletes a saved outfit from the page.
- removed catalog items show a removed indication inside saved outfit citations.
