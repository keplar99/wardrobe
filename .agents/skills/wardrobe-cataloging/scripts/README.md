# Wardrobe scripts

Helper scripts for the Pass 1 wardrobe cataloging workflow. See
`../SKILL.md` for the full workflow context, schema reference, and
rules.

All scripts auto-discover the Wardrobe root by walking up until they
find a directory containing both `data/Raw Images/` and `working/`.
Run them from the `Wardrobe/` directory for clean paths.

The CSVs live in `Wardrobe/working/` and the source photos in
`Wardrobe/data/Raw Images/`.

## Files

| Script | Purpose |
|---|---|
| `find_unprocessed.py` | List image filenames in `data/Raw Images/` not yet cataloged. |
| `append_batch.py` | Library + sanity-check CLI. Defines column schemas; helpers for appending validated rows to all three CSVs. |
| `example_batch_append.py` | Reference template for a per-batch append script. |
| `verify_csvs.py` | End-to-end integrity check: schema, cross-references, filename coverage, duplicates. |

## Typical batch (10 images)

```bash
# 1. Find what to process next
python3 .claude/skills/wardrobe-cataloging/scripts/find_unprocessed.py 10

# 2. Claude reads each image, identifies items, dedups against the catalog,
#    and constructs row data (catalog_rows, ref_rows, obs_rows).

# 3. Append the new rows. Put the scripts directory on sys.path:
#
#    import sys
#    sys.path.insert(0, ".claude/skills/wardrobe-cataloging/scripts")
#    from append_batch import (
#        append_catalog, append_reference_map, append_observations,
#    )
#    append_catalog(catalog_rows)
#    append_reference_map(ref_rows)
#    append_observations(obs_rows)

# 4. Sanity check
python3 .claude/skills/wardrobe-cataloging/scripts/append_batch.py --sanity-check

# 5. Full integrity check
python3 .claude/skills/wardrobe-cataloging/scripts/verify_csvs.py
```

## Library helpers (append_batch.py)

| Function | Returns |
|---|---|
| `append_catalog(rows)` | New total row count of `working/wardrobe_catalog.csv`. |
| `append_reference_map(rows)` | New total row count of `working/image_reference_map.csv`. |
| `append_observations(rows)` | New total row count of `working/observations_open_questions.csv`. |
| `next_image_number()` | The next `Img N` to use in the reference map. |
| `next_item_id(prefix)` | The next numeric suffix for `TOP`, `BOT`, `SHOE`, or `ACC`. |

Each `append_*` helper validates row length against the schema and
raises `ValueError` on a mismatch — never silently writes a misaligned
row.

## Column schemas

Defined as module-level constants in `append_batch.py`:

- `CATALOG_COLS` — 40 columns (wardrobe_catalog.csv)
- `REF_COLS` — 6 columns (image_reference_map.csv)
- `OBS_COLS` — 6 columns (observations_open_questions.csv)

Do not reorder or rename without updating `../SKILL.md` at the same
time.
