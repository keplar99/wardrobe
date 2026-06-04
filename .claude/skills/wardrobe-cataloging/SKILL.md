---
name: wardrobe-cataloging
description: Use this skill when cataloging, organizing, or analyzing clothing items in the Wardrobe folder. Triggers include processing raw clothing images, building or updating wardrobe_catalog.csv, classifying items into tops/bottoms/shoes/outfits, generating styling observations, reviewing staging folders, or answering questions about what is in the user's wardrobe.
---

# Wardrobe Cataloging Skill

This skill governs the Pass 1 metadata cataloging workflow for Varun's
wardrobe. The goal is to observe, identify, deduplicate, and accurately
tag every garment image in `data/Raw Images/` into three CSVs in
`working/`. **No outfit recommendations, gap analysis, or combos in
this pass.**

The scripts referenced below live in `scripts/` next to this file.

## Client profile

- Build: 6'0", athletic, works out regularly
- Complexion: Indian, light brown / warm undertone
- Face shape: oval
- Base: Bangalore, India (travels frequently — domestic and international)
- Style range: context-switches across street/rugged, Goa/hippie,
  cosmopolitan/refined, metalhead/grunge, "designer software dev." Not
  one fixed aesthetic — maximum versatility across occasions is the goal.
- Comfort: non-negotiable. Nothing stiff, restrictive, or uncomfortable
  regardless of appearance.
- Occasions: office (startup/creative), date nights (casual and
  upscale), parties, restaurants, hanging out with friends, travel
  days, beach/Goa, concerts.

## File structure

```
Wardrobe/
├── CLAUDE.md                            ← thin project pointer (points at this skill)
├── .claude/skills/wardrobe-cataloging/
│   ├── SKILL.md                          ← this file (operational doc)
│   └── scripts/
│       ├── README.md
│       ├── find_unprocessed.py           ← list images not yet cataloged
│       ├── append_batch.py               ← schema + safe-append helpers
│       ├── example_batch_append.py       ← template for a per-batch run
│       └── verify_csvs.py                ← end-to-end integrity check
├── data/
│   ├── Raw Images/                       ← input photos (the source of truth)
│   ├── staging_top/                      ← partially populated; intended for triage by garment type
│   ├── staging_bottom/
│   ├── staging_shoes/
│   └── staging_outfit/
└── working/
    ├── wardrobe_catalog.csv              ← one row per unique garment
    ├── image_reference_map.csv           ← one row per image (audit trail)
    └── observations_open_questions.csv   ← unresolved flags & questions
```

The staging folders under `data/` are a partial triage artifact from an
earlier categorization pass — they currently hold roughly the first 20
images. They are not authoritative; `working/wardrobe_catalog.csv` and
`working/image_reference_map.csv` are the source of truth for what is
processed.

## Workflow per batch (10 images at a time)

Run from the `Wardrobe/` directory. The user expects a pause after each
batch and the word "continue" before starting the next.

1. **Find the next 10 unprocessed images.** Whether a file is processed
   is determined solely by whether its filename appears in the
   `Image Filename` column of `working/image_reference_map.csv` (the
   reference map is the source of truth for triage state — see Critical
   rules below). Do not rely on session state, transcripts, or memory.
   ```
   python3 .claude/skills/wardrobe-cataloging/scripts/find_unprocessed.py
   ```
   The script defaults to a batch of 10 — no positional argument
   needed. Pass an explicit integer to override (e.g. `5`), or
   `--all` / `0` to disable the cap, or `--count` for just the
   summary line.
2. **Read each image** with the Read tool (they live in
   `data/Raw Images/`). Identify the garment type (flat lay / worn /
   shoe / accessory / duplicate angle of a prior image).
3. **Deduplicate against the existing catalog.** Match on color +
   pattern (primary), fabric texture (secondary), construction details
   (collar, button color, pocket placement, distressing), and visible
   brand. Three outcomes per photo:
   - **Same as an existing cataloged item** → pipe-append the filename
     to that catalog row's `Item Image Name` and append the image-ref
     designator to `Image References`. Add a ref-map row mapping the
     image to the existing item ID.
   - **A genuinely new item** → create a new catalog row using the next
     free ID for the prefix. Add a ref-map row mapping the image to
     that new ID. **Never reuse a retired ID** — see Critical rules.
   - **Triaged but no catalog row warranted** (duplicate-angle of an
     already-mapped image; user previously invalidated this item;
     unrelated to wardrobe contents) → still add a ref-map row so the
     image counts as processed, leave `Mapped Item ID(s)` blank or
     point to the relevant existing item without modifying the catalog.
     Note the reason in `Notes`.
   If unsure whether two near-similar items are the same, **do not
   silently merge** — list as separate IDs and add a
   "POSSIBLE DUPLICATE of [ID]" row to
   `working/observations_open_questions.csv`.
4. **Construct rows** for all three CSVs using the schemas in
   `scripts/append_batch.py`. Column order matters; row length is
   validated.
5. **Append the rows** via the library. The reference-map append is
   **required for every photo in the batch** (that's how triage state
   is recorded). The catalog and observations appends are conditional —
   only when a photo introduces a new item or surfaces a flag worth
   logging:
   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, ".claude/skills/wardrobe-cataloging/scripts")
   from append_batch import (
       append_catalog, append_reference_map, append_observations,
   )
   append_reference_map(ref_rows)   # always — one row per triaged photo
   append_catalog(catalog_rows)     # only for new items
   append_observations(obs_rows)    # only when flagging something
   ```
   (Or copy `scripts/example_batch_append.py` and run it directly.)
6. **Verify integrity:**
   ```
   python3 .claude/skills/wardrobe-cataloging/scripts/append_batch.py --sanity-check
   python3 .claude/skills/wardrobe-cataloging/scripts/verify_csvs.py
   ```
7. **Pause** and report a batch summary (new IDs, items merged, flags
   raised, brands identified, anything surprising). Wait for the user
   to say "continue".

## Identifier scheme

- `TOP-XX` — shirts, tees, sweaters, jackets, anything worn on the torso
- `BOT-XX` — jeans, trousers, shorts, anything worn on the legs
- `SHOE-XX` — every footwear item
- `ACC-XX` — belts, watches, hats, bags, jewelry, sunglasses, etc.

`scripts/append_batch.py --sanity-check` prints the next ID for each
prefix.

## Image numbering

The "Image Number" column uses `Img 1, Img 2, ...` in the order images
were processed (which matches alphabetical filename order, since
WhatsApp timestamps sort cleanly). `scripts/append_batch.py
next_image_number()` returns the next number to use.

## Schema — wardrobe_catalog.csv (41 columns, in order)

**Identity (1–9)**
1. Item ID — `TOP-XX` / `BOT-XX` / `SHOE-XX` / `ACC-XX`
2. Item Image Name — exact filename. Pipe-separate if multiple images show this item.
3. Image References — `Img N (flat)` / `Img N (worn front)` / `Img N (worn side)`, comma-separated
4. Category — Shirt, T-Shirt, Jeans, Trousers, Shorts, Sweater, Jacket, Shoes, Accessory, etc.
5. Sub-Category — specific: "Camp collar shirt", "Mandarin collar shirt", "Distressed denim shorts", "Chelsea boots", etc.
6. Brand — from visible tag. "Unidentified" if not. **Do not guess.**
7. Color (Primary) — precise: "steel blue", "navy", "indigo", "powder blue" (not "blue"); "charcoal", "heather grey", "warm grey", "cool grey" (not "grey").
8. Color (Secondary) — for patterns/accents/stitching contrast. Use "—" for solid pieces.
9. Pattern — Solid, striped (specify vertical/horizontal/pin), abstract print, floral, tropical, acid-wash, distressed, knit texture, marled, graphic, etc.

**Shape & Fit (10–16)**
10. Fit — Slim / Regular / Relaxed / Oversized. **Base on worn photo if available.**
11. Rise — Low / Mid / Mid-high / High. Bottoms only; blank for tops.
12. Length — Full / Cropped / Ankle / Above-knee / Short-sleeve / Long-sleeve / 3/4 sleeve. For shorts, specify inseam vs knee.
13. Silhouette — Tapered, Straight, Wide, Boxy, Fitted, Drop-shoulder. **Defer to worn photo.**
14. Neckline — Crew / V-neck / Camp collar / Button-down collar / Mandarin / Mock neck / Polo, etc. Tops only.
15. Drape Notes — Worn-photo-only. Write "No worn photo available" if flat-lay only.
16. Fit Source — "Worn photo (Img N front, Img M side) — ground truth" OR "Flat lay only".

**Material & Feel (17–21)**
17. Fabric — specific: "cotton jersey", "cotton-linen blend", "heavyweight denim", "open-knit cotton-acrylic", etc.
18. Weight — Light / Mid / Heavy
19. Stretch — Yes / No / Slight
20. Breathability — Low / Medium / High
21. Surface Texture — Smooth / textured / rough / slubby / crisp / soft-washed / brushed / ribbed / open-weave, etc.

**Style & Occasion (22–25)**
22. Formality (1–5) — 1=loungewear/gym, 2=very casual, 3=smart casual, 4=business casual, 5=formal
23. Vibe Tags — comma-separated; pull from: clean, minimal, street, rugged, metalhead, grunge, preppy, coastal, earthy, artisan, Goa/hippie, cosmopolitan, designer-dev, editorial, bold, maximalist, Scandi, safari, surf
24. Occasion Tags — comma-separated; pull from: office, date night (casual), date night (upscale), party, restaurant, casual hangout, boys night, travel day, beach/Goa, concert, brunch
25. Layering Position — Base / Mid / Outer / "Base / open as outer". Tops only; blank for bottoms.

**Seasonality (26–27)**
26. Season — Summer / Monsoon / Winter / All-season. Bangalore-calibrated.
27. Max Comfortable Temp (C) — upper limit where the garment is still comfortable.

**Condition & Usage (28–29)**
28. Condition — New (tags on) / Good / Worn / Faded / Distressed (intentional). Note design vs actual wear.
29. Wear Frequency Estimate — Daily rotation / Regular / Occasional / Rare.

**Color Science (30–33)**
30. Color Temperature — Warm / Cool / Neutral
31. Skin Tone Interaction — How the color sits against light brown / warm Indian skin. Be honest. Beige, sand, tan, khaki, nude, pastel yellow risk disappearing.
32. Skin Tone Caution Flag — `YES` / `No`
33. Contrast Level — High (white, black, deep navy) / Medium (olive, grey, indigo) / Low (sand, beige, tan)

**Pairing Utility (34–36)**
34. Versatility Score (1–5) — 5=goes-with-almost-anything workhorse, 1=one-trick pony. Bold prints score low.
35. Role in Outfit — Star (focal point) / Supporting (recedes) / Both (context-dependent)
36. Volume/Visual Weight — Low / Medium / High

**Shoes only (37–40, blank for non-shoes)**
37. Shoe Type — Sneaker / Loafer / Boot / Sandal / Slide / Derby / Oxford / Espadrille, etc.
38. Sole Profile — Chunky / Slim / Flat / Platform
39. Aesthetic Range — e.g. "clean casual to smart casual", "street/grunge only"
40. Top Compatibility Note — e.g. "needs a tapered ankle opening — gets lost under wide-leg hems"

**Client context (41)**
41. Client notes — free-text notes from the user about how they wear/feel about the item (e.g. wear frequency, perceived fit issues, retire vs keep). Blank for items the user has not annotated.

## Schema — image_reference_map.csv (6 columns)

1. Image Number — `Img N`
2. Image Filename — exact filename from `data/Raw Images/`
3. Description — one-line description of what's in the photo
4. Image Type — one of:
   - `Flat lay` — single garment laid flat
   - `Worn photo` — client wearing a garment that this image is cataloging (used for fit/drape ground truth)
   - `Duplicate angle` — same garment as a prior image, different angle
   - `Shoe` / `Accessory` — flat lays of footwear or accessories
5. Mapped Item ID(s) — the item(s) this image is *cataloging*. For a flat lay, that's the single garment shown. For a worn photo, that's the new garment being added to the catalog from this image. Do **not** also map already-cataloged items that happen to appear in the frame (e.g., if a worn photo shows a new top with previously cataloged jeans, list only the new top's `TOP-XX`). The wardrobe is a catalog of individual items, not outfits.
6. Notes — anything special: "Shows how fabric drapes at waist", "Back view", "Same as Img 3 different angle", possible-duplicate flags, etc.

## Schema — observations_open_questions.csv (6 columns)

1. Item ID — the affected item (or `GENERAL` for batch-wide notes)
2. Image(s) — `Img N` or `Img N, Img M`
3. Category — garment category (T-Shirt, Shirt, Trousers, etc., or `—` for general notes)
4. Observation Type — short tag: "Brand identification", "Skin tone caution", "POSSIBLE DUPLICATE of XXX-YY", "Color resolution", etc.
5. Detail — what was observed and why it's flagged
6. Action Needed — what to do about it, or "No action — flag is for downstream pairing decisions"

## Critical rules

- **Worn photos override flat lays** for fit, silhouette, drape. Flat
  lays exaggerate boxiness. If a worn photo exists, base fit data on
  it and note "Worn photo (Img N) — ground truth" in Fit Source.
- **Be precise with color names.** "Blue" / "grey" / "green" are not
  colors. Use navy, indigo, steel blue, powder blue, cobalt, sky blue
  — or charcoal, heather grey, warm grey, cool grey — or olive,
  forest, sage, kelly.
- **Flag skin-tone risk** clearly. Warm light-brown skin + beige/sand/
  tan/khaki/nude/pastel-yellow = caution. Set Skin Tone Caution Flag to
  `YES` and add a row to `working/observations_open_questions.csv`.
- **No "pairs with everything."** Nothing pairs with everything. Even
  white tees have constraints (high-contrast, base layer only,
  formality cap).
- **Do not guess brands.** "Unidentified" beats wrong attribution.
  Flag partial/visible labels in observations so the user can
  physically verify.
- **Do not inflate versatility.** Bold prints, heavy distressing,
  statement washes score 2–3 max. Honest scoring is more useful than
  flattering scoring.
- **Do not silently merge possible duplicates.** If two items look
  similar but might be different, list separate IDs and flag the
  possible duplicate in observations.
- **Use blank for "field doesn't apply"** (e.g., Rise on a tee,
  Layering Position on trousers, shoe-only fields on a top). Use "—"
  for "deliberately empty solid color" (Color Secondary). Use
  "Cannot determine from photo" only when the data is genuinely
  unobtainable from the image.
- **`image_reference_map.csv` is the source of truth for "processed".**
  A filename in the `Image Filename` column means the photo has been
  triaged — that's the only signal `find_unprocessed.py` looks at. The
  reference map records every triaged image regardless of whether it
  ends up in `wardrobe_catalog.csv`.
- **`wardrobe_catalog.csv` is a curated subset of the reference map,
  not a 1:1 mirror.** Some triaged photos intentionally have no catalog
  row — e.g. duplicate-angle photos already represented by another row,
  photos of items the user has explicitly invalidated, or photos that
  turned out to be uninformative. Do **not** treat "no catalog row for
  this ref-map filename" as a bug — it's a deliberate state.
- **Never reuse an item ID.** If a row was deleted/invalidated, its ID
  is retired. Use the next free integer for the prefix
  (`scripts/append_batch.py --sanity-check` reports the next ID).
  Re-introducing a previously-invalidated ID destroys audit history.
- **Process exactly one batch per invocation.** After completing step 7
  and reporting the batch summary, stop completely. Do not loop back to
  step 1. The next batch begins only when the user sends "continue".

## Mistakes to avoid

- Tagging fit from flat lays when a worn photo exists.
- Generic color names ("blue", "grey", "green").
- Inflating versatility scores on statement pieces.
- Guessing brands.
- Creating duplicate entries when an item appears in multiple images
  — merge into one row with pipe-separated filenames.
- Using "Cannot determine from photo" as a lazy out for things that
  ARE visible (fabric family, broad fit category, color, basic
  construction).

## Notes for future batches

- `scripts/find_unprocessed.py` is authoritative for what's left.
  Default invocation returns at most 10 filenames (one batch). The
  summary header line always shows the true totals, so the count of
  remaining work is visible regardless of the cap. To see the full
  list of unprocessed files, pass `--all` (or `0`). To check
  completion at a glance, use `--count`: if Unprocessed = 0,
  Pass 1 is done.
- New image extensions (`.heic`, `.webp`) are handled automatically
  by the scripts.
- If the schema needs to change, update `scripts/append_batch.py`
  (`CATALOG_COLS` / `REF_COLS` / `OBS_COLS`) AND this file at the
  same time, then re-run `verify_csvs.py` on the existing data.
- The staging folders under `data/` are partial — only ~20 of 100+
  images have been triaged into them. They're useful as a quick visual
  index but should not be treated as authoritative; `working/`
  CSVs are the source of truth.
