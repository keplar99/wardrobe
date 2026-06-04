"""
find_unprocessed.py
-------------------
List images in `data/Raw Images/` that have NOT yet been processed.

**Source of truth for "processed" is `working/image_reference_map.csv`.**
A file is "processed" iff its filename appears in the `Image Filename`
column of the reference map. The reference map records every image that
has been triaged — even if it doesn't end up with a row in
`wardrobe_catalog.csv` (some images intentionally don't, e.g. because
they were determined to be duplicates of an already-cataloged item or
because the photo is uninformative).

`wardrobe_catalog.csv` is the final curated catalog; not every ref-map
entry needs a catalog row, and that's fine.

By default the listing is capped at 10 filenames — one batch's worth —
to match the per-batch workflow in SKILL.md. Pass an explicit integer to
override the cap, `--all` (or `0`) to disable it, or `--count` for the
summary line only.

Usage (run from the Wardrobe/ directory):
    python3 .claude/skills/wardrobe-cataloging/scripts/find_unprocessed.py            # first 10 (default)
    python3 .claude/skills/wardrobe-cataloging/scripts/find_unprocessed.py 5          # first 5
    python3 .claude/skills/wardrobe-cataloging/scripts/find_unprocessed.py --all      # all unprocessed
    python3 .claude/skills/wardrobe-cataloging/scripts/find_unprocessed.py --count    # summary only
"""
import sys
from pathlib import Path
import pandas as pd


def _find_wardrobe_root() -> Path:
    start = Path(__file__).resolve().parent
    for candidate in [start, *start.parents]:
        if (candidate / "data" / "Raw Images").is_dir() and (candidate / "working").is_dir():
            return candidate
    raise RuntimeError(
        "Could not locate Wardrobe root. Expected an ancestor directory "
        "containing both `data/Raw Images/` and `working/`."
    )


WARDROBE = _find_wardrobe_root()
RAW = WARDROBE / "data" / "Raw Images"
REF_MAP = WARDROBE / "working" / "image_reference_map.csv"

IMAGE_EXTS = {".jpeg", ".jpg", ".png", ".heic", ".webp"}

DEFAULT_LIMIT = 10


def list_raw_images() -> list[str]:
    """Return all image filenames in `data/Raw Images/`, sorted."""
    return sorted(
        p.name for p in RAW.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def list_processed_filenames() -> set[str]:
    """Return the set of filenames present in `image_reference_map.csv`.

    The reference map is the single source of truth for "has this image
    been triaged?" — see SKILL.md.
    """
    if not REF_MAP.exists():
        return set()
    df = pd.read_csv(REF_MAP)
    if "Image Filename" not in df.columns:
        raise RuntimeError(
            f"{REF_MAP.name} is missing the required 'Image Filename' column."
        )
    return {str(name).strip() for name in df["Image Filename"].dropna() if str(name).strip()}


def find_unprocessed() -> list[str]:
    raw = list_raw_images()
    processed = list_processed_filenames()
    return [f for f in raw if f not in processed]


def main() -> None:
    args = sys.argv[1:]
    count_only = "--count" in args
    show_all = "--all" in args
    args = [a for a in args if a not in {"--count", "--all"}]

    # Resolve the effective limit:
    #   - explicit positional integer wins (0 disables the cap)
    #   - else, --all disables the cap
    #   - else, fall back to DEFAULT_LIMIT (10)
    if args:
        n = int(args[0])
        limit = None if n == 0 else n
    elif show_all:
        limit = None
    else:
        limit = DEFAULT_LIMIT

    unprocessed = find_unprocessed()
    total_raw = len(list_raw_images())
    total_processed = total_raw - len(unprocessed)

    print(
        f"# Raw Images: {total_raw} | Processed: {total_processed} | "
        f"Unprocessed: {len(unprocessed)}  (source of truth: image_reference_map.csv)"
    )
    if count_only:
        return

    items = unprocessed if limit is None else unprocessed[:limit]
    if limit is not None and len(unprocessed) > limit:
        print(f"# Showing first {limit} of {len(unprocessed)} unprocessed (pass --all to see the rest)")
    for f in items:
        print(f)


if __name__ == "__main__":
    main()
