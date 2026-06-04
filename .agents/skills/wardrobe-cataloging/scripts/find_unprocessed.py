"""
find_unprocessed.py
-------------------
List images in Raw Images/ that have NOT yet been processed into the
wardrobe catalog.

A file is considered "processed" if its filename appears anywhere in the
"Item Image Name" column of wardrobe_catalog.csv (filenames are stored
either as a single name or pipe-separated when one item appears in
multiple images).

Usage (from the Wardrobe/ directory):
    python3 .claude/skills/wardrobe-cataloging/scripts/find_unprocessed.py
    python3 .claude/skills/wardrobe-cataloging/scripts/find_unprocessed.py 10
    python3 .claude/skills/wardrobe-cataloging/scripts/find_unprocessed.py --count
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
CATALOG = WARDROBE / "working" / "wardrobe_catalog.csv"

IMAGE_EXTS = {".jpeg", ".jpg", ".png", ".heic", ".webp"}


def list_raw_images() -> list[str]:
    """Return all image filenames in Raw Images/, sorted."""
    return sorted(
        p.name for p in RAW.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def list_processed_filenames() -> set[str]:
    """Return the set of filenames already cataloged.

    Filenames may be stored as a single value or pipe-separated.
    """
    if not CATALOG.exists():
        return set()
    df = pd.read_csv(CATALOG)
    processed: set[str] = set()
    for cell in df["Item Image Name"].dropna():
        for name in str(cell).split("|"):
            name = name.strip()
            if name:
                processed.add(name)
    return processed


def find_unprocessed() -> list[str]:
    raw = list_raw_images()
    processed = list_processed_filenames()
    return [f for f in raw if f not in processed]


def main() -> None:
    args = sys.argv[1:]
    count_only = "--count" in args
    args = [a for a in args if a != "--count"]
    limit = int(args[0]) if args else None

    unprocessed = find_unprocessed()
    total_raw = len(list_raw_images())
    total_processed = total_raw - len(unprocessed)

    print(
        f"# Raw Images: {total_raw} | Processed: {total_processed} | "
        f"Unprocessed: {len(unprocessed)}"
    )
    if count_only:
        return

    items = unprocessed if limit is None else unprocessed[:limit]
    for f in items:
        print(f)


if __name__ == "__main__":
    main()
