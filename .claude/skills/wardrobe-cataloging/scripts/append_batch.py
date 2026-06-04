"""
append_batch.py
---------------
Library helpers + CLI for appending a batch of new rows to the three
wardrobe CSVs. Designed to be imported by an ad-hoc per-batch script
(see scripts/example_batch_append.py).

Why a library and not a fully-automatic CLI?
    The per-image metadata is built by a vision-capable agent (Claude)
    after looking at each image. The agent constructs the row data in
    memory and then calls these helpers to persist it.

Usage (from a per-batch script):

    from append_batch import (
        CATALOG_COLS, REF_COLS, OBS_COLS,
        append_catalog, append_reference_map, append_observations,
    )

    append_catalog([
        ["TOP-09", "filename.jpeg", "Img 21 (flat)", "T-Shirt", ...],
        ...
    ])

Run directly for a quick sanity check:
    python3 .claude/skills/wardrobe-cataloging/scripts/append_batch.py --sanity-check
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd


def _find_wardrobe_root() -> Path:
    """Walk up from this file to locate the Wardrobe root.

    The Wardrobe root is identified by containing BOTH a
    ``data/Raw Images/`` directory and a ``working/`` directory. This
    works regardless of where these scripts live inside the project
    (e.g. nested under .claude/skills/...).
    """
    start = Path(__file__).resolve().parent
    for candidate in [start, *start.parents]:
        if (candidate / "data" / "Raw Images").is_dir() and (candidate / "working").is_dir():
            return candidate
    raise RuntimeError(
        "Could not locate Wardrobe root. Expected an ancestor directory "
        "containing both `data/Raw Images/` and `working/`."
    )


WARDROBE = _find_wardrobe_root()
DATA = WARDROBE / "data"
WORKING = WARDROBE / "working"
CATALOG = WORKING / "wardrobe_catalog.csv"
REF_MAP = WORKING / "image_reference_map.csv"
OBS = WORKING / "observations_open_questions.csv"

# Fixed column schemas. Do not reorder or rename without also editing SKILL.md.
CATALOG_COLS: list[str] = [
    "Item ID", "Item Image Name", "Image References", "Category", "Sub-Category",
    "Brand", "Color (Primary)", "Color (Secondary)", "Pattern",
    "Fit", "Rise", "Length", "Silhouette", "Neckline", "Drape Notes", "Fit Source",
    "Fabric", "Weight", "Stretch", "Breathability", "Surface Texture",
    "Formality (1-5)", "Vibe Tags", "Occasion Tags", "Layering Position",
    "Season", "Max Comfortable Temp (C)", "Condition", "Wear Frequency Estimate",
    "Color Temperature", "Skin Tone Interaction", "Skin Tone Caution Flag",
    "Contrast Level", "Versatility Score (1-5)", "Role in Outfit",
    "Volume/Visual Weight",
    "Shoe Type", "Sole Profile", "Aesthetic Range", "Top Compatibility Note",
    "Client notes", "Status",
]

REF_COLS: list[str] = [
    "Image Number", "Image Filename", "Description", "Image Type",
    "Mapped Item ID(s)", "Notes",
]

OBS_COLS: list[str] = [
    "Item ID", "Image(s)", "Category", "Observation Type", "Detail", "Action Needed",
]


def _append(path: Path, columns: Sequence[str], rows: Iterable[Sequence]) -> int:
    """Validate columns, append rows, return new total row count."""
    rows = list(rows)
    if not rows:
        df = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=columns)
        return len(df)

    for i, r in enumerate(rows):
        if len(r) != len(columns):
            raise ValueError(
                f"Row {i} has {len(r)} fields but expected {len(columns)}. "
                f"Row preview: {list(r)[:3]}..."
            )

    df_new = pd.DataFrame(rows, columns=list(columns))
    if path.exists():
        df_existing = pd.read_csv(path)
        if list(df_existing.columns) != list(columns):
            raise ValueError(
                f"Existing columns in {path.name} do not match expected schema.\n"
                f"  Expected: {list(columns)}\n"
                f"  Found:    {list(df_existing.columns)}"
            )
        df = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return len(df)


def append_catalog(rows: Iterable[Sequence]) -> int:
    """Append rows to wardrobe_catalog.csv. Returns new total row count."""
    return _append(CATALOG, CATALOG_COLS, rows)


def append_reference_map(rows: Iterable[Sequence]) -> int:
    """Append rows to image_reference_map.csv. Returns new total row count."""
    return _append(REF_MAP, REF_COLS, rows)


def append_observations(rows: Iterable[Sequence]) -> int:
    """Append rows to observations_open_questions.csv. Returns new total row count."""
    return _append(OBS, OBS_COLS, rows)


def next_image_number() -> int:
    """Return the next Img N number based on existing image_reference_map.csv."""
    if not REF_MAP.exists():
        return 1
    df = pd.read_csv(REF_MAP)
    if df.empty:
        return 1
    highest = 0
    for v in df["Image Number"].dropna():
        s = str(v).strip()
        if s.lower().startswith("img"):
            try:
                highest = max(highest, int(s.split()[1]))
            except (IndexError, ValueError):
                pass
    return highest + 1


def next_item_id(prefix: str) -> int:
    """Return the next numeric suffix for a given prefix (TOP, BOT, SHOE, ACC)."""
    if not CATALOG.exists():
        return 1
    df = pd.read_csv(CATALOG)
    highest = 0
    for v in df["Item ID"].dropna():
        s = str(v).strip()
        if s.startswith(f"{prefix}-"):
            try:
                highest = max(highest, int(s.split("-")[1]))
            except (IndexError, ValueError):
                pass
    return highest + 1


def _sanity_check() -> None:
    print(f"Wardrobe dir: {WARDROBE}")
    for path, cols in [(CATALOG, CATALOG_COLS), (REF_MAP, REF_COLS), (OBS, OBS_COLS)]:
        if not path.exists():
            print(f"  {path.name}: MISSING")
            continue
        df = pd.read_csv(path)
        ok = list(df.columns) == cols
        marker = "OK" if ok else "SCHEMA MISMATCH"
        print(f"  {path.name}: {len(df)} rows | {len(df.columns)} cols | {marker}")
    print(f"  Next image number: Img {next_image_number()}")
    for p in ("TOP", "BOT", "SHOE", "ACC"):
        print(f"  Next {p}: {p}-{next_item_id(p):02d}")


if __name__ == "__main__":
    if "--sanity-check" in sys.argv:
        _sanity_check()
    else:
        print(__doc__)
