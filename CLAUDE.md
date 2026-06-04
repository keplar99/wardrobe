# Wardrobe

Pass 1 metadata cataloging project for Varun's wardrobe.

The full operational workflow — client profile, batch process, all
three CSV schemas, critical rules, and helper scripts — lives in the
**wardrobe-cataloging** skill at:

```
.claude/skills/wardrobe-cataloging/SKILL.md
```

Read that file before doing any cataloging work.

## Quick layout reminder

- `data/Raw Images/` — input photos (122 files, source of truth).
- `data/staging_*/` — partial triage by garment type (only ~20 images
  have been moved in so far; not authoritative).
- `working/` — the three output CSVs:
  `wardrobe_catalog.csv`, `image_reference_map.csv`,
  `observations_open_questions.csv`.
- `.claude/skills/wardrobe-cataloging/scripts/` — helper scripts:
  `find_unprocessed.py`, `append_batch.py`, `verify_csvs.py`,
  `example_batch_append.py`.

Run all scripts from the `Wardrobe/` directory.
