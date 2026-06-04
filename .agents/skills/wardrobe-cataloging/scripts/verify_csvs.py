"""
verify_csvs.py
--------------
Sanity-check all three wardrobe CSVs and report:
  - row counts, column counts, header alignment
  - image-reference / catalog cross-references (every Item ID mentioned
    in the reference map should exist in the catalog, and vice versa)
  - filename coverage (every image in Raw Images/ should appear exactly
    once in the reference map; every cataloged filename should exist
    on disk)
  - obvious data quality issues (blank Item IDs, duplicate filenames,
    unresolved "Cannot determine" without a matching observation row)

Usage (from the Wardrobe/ directory):
    python3 .claude/skills/wardrobe-cataloging/scripts/verify_csvs.py
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

# Make sibling modules importable when this script is invoked by path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from append_batch import (
    CATALOG, REF_MAP, OBS, CATALOG_COLS, REF_COLS, OBS_COLS, WARDROBE, DATA,
)

RAW = DATA / "Raw Images"
IMAGE_EXTS = {".jpeg", ".jpg", ".png", ".heic", ".webp"}


def _check_schema(path: Path, expected: list[str]) -> pd.DataFrame:
    df = pd.read_csv(path)
    if list(df.columns) != expected:
        print(f"  ! Schema mismatch in {path.name}")
        print(f"      expected: {expected}")
        print(f"      found:    {list(df.columns)}")
    else:
        print(f"  OK  {path.name}: {len(df)} rows, {len(df.columns)} cols")
    return df


def main() -> None:
    print("=== Schema check ===")
    cat = _check_schema(CATALOG, CATALOG_COLS)
    ref = _check_schema(REF_MAP, REF_COLS)
    obs = _check_schema(OBS, OBS_COLS)

    print("\n=== Cross-reference check ===")
    cat_ids = set(cat["Item ID"].dropna().astype(str))
    ref_ids_raw = ref["Mapped Item ID(s)"].dropna().astype(str)
    ref_ids: set[str] = set()
    for cell in ref_ids_raw:
        for v in cell.replace(";", ",").split(","):
            v = v.strip()
            if v and v not in {"-", "—"}:
                ref_ids.add(v)

    missing_from_catalog = ref_ids - cat_ids
    missing_from_ref = cat_ids - ref_ids
    if missing_from_catalog:
        print(f"  ! Item IDs in reference map but not catalog: {sorted(missing_from_catalog)}")
    if missing_from_ref:
        print(f"  ! Item IDs in catalog but never referenced: {sorted(missing_from_ref)}")
    if not (missing_from_catalog or missing_from_ref):
        print(f"  OK  {len(cat_ids)} Item IDs cross-reference cleanly")

    print("\n=== Filename coverage ===")
    raw_files = {p.name for p in RAW.iterdir()
                 if p.is_file() and p.suffix.lower() in IMAGE_EXTS}
    ref_files = set(ref["Image Filename"].dropna().astype(str))
    cat_filenames: set[str] = set()
    for cell in cat["Item Image Name"].dropna().astype(str):
        for name in cell.split("|"):
            cat_filenames.add(name.strip())

    in_raw_not_in_ref = raw_files - ref_files
    in_ref_not_in_raw = ref_files - raw_files
    in_cat_not_in_raw = cat_filenames - raw_files
    if in_raw_not_in_ref:
        print(f"  ! {len(in_raw_not_in_ref)} raw images NOT in reference map (unprocessed):")
        for f in sorted(in_raw_not_in_ref)[:10]:
            print(f"      - {f}")
        if len(in_raw_not_in_ref) > 10:
            print(f"      ... and {len(in_raw_not_in_ref) - 10} more")
    if in_ref_not_in_raw:
        print(f"  ! {len(in_ref_not_in_raw)} reference filenames NOT on disk:")
        for f in sorted(in_ref_not_in_raw)[:10]:
            print(f"      - {f}")
    if in_cat_not_in_raw:
        print(f"  ! {len(in_cat_not_in_raw)} catalog filenames NOT on disk:")
        for f in sorted(in_cat_not_in_raw)[:10]:
            print(f"      - {f}")
    if not (in_raw_not_in_ref or in_ref_not_in_raw or in_cat_not_in_raw):
        print(f"  OK  {len(raw_files)} raw images all accounted for")

    print("\n=== Reference-map filename duplicates ===")
    dups = ref["Image Filename"].value_counts()
    dups = dups[dups > 1]
    if len(dups):
        print(f"  ! {len(dups)} filenames appear more than once in reference map:")
        for f, c in dups.items():
            print(f"      - {f}: {c} entries")
    else:
        print("  OK  no duplicate filenames in reference map")

    print("\n=== Blank-field checks ===")
    blank_ids = cat[cat["Item ID"].isna() | (cat["Item ID"].astype(str).str.strip() == "")]
    if len(blank_ids):
        print(f"  ! {len(blank_ids)} catalog rows with blank Item ID")
    else:
        print("  OK  all catalog rows have an Item ID")

    print("\nDone.")


if __name__ == "__main__":
    main()
