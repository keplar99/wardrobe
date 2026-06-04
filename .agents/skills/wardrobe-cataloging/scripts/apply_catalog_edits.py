#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path


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
WORKING = WARDROBE / "working"
CATALOG = WORKING / "wardrobe_catalog.csv"

EDITABLE_FIELDS = {
    "Category",
    "Sub-Category",
    "Brand",
    "Color (Primary)",
    "Color (Secondary)",
    "Pattern",
    "Fit",
    "Rise",
    "Length",
    "Silhouette",
    "Neckline",
    "Drape Notes",
    "Fit Source",
    "Fabric",
    "Weight",
    "Stretch",
    "Breathability",
    "Surface Texture",
    "Formality (1-5)",
    "Vibe Tags",
    "Occasion Tags",
    "Layering Position",
    "Season",
    "Max Comfortable Temp (C)",
    "Condition",
    "Wear Frequency Estimate",
    "Color Temperature",
    "Skin Tone Interaction",
    "Skin Tone Caution Flag",
    "Contrast Level",
    "Versatility Score (1-5)",
    "Role in Outfit",
    "Volume/Visual Weight",
    "Shoe Type",
    "Sole Profile",
    "Aesthetic Range",
    "Top Compatibility Note",
    "Client notes",
    "Status",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply exported JSON field edits from wardrobe_catalog_table.html "
            "back into working/wardrobe_catalog.csv."
        )
    )
    parser.add_argument("--input", type=Path, required=True, help="Path to the exported JSON patch.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the CSV changes. Without this flag the script runs in dry-run mode.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Apply even when the current CSV value does not match the patch old_value.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Directory for CSV backups when --apply is used. Default: working/review_backups/<timestamp>/",
    )
    return parser.parse_args()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def file_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def backup_file(path: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)


def load_patch(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Patch file must contain a top-level JSON object.")
    return data


def make_catalog_index(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        item_id = (row.get("Item ID") or "").strip()
        if item_id:
            index[item_id] = row
    return index


def normalize_edits(data: dict[str, object]) -> list[dict[str, object]]:
    edits = data.get("edits", [])
    if not isinstance(edits, list):
        raise ValueError("Patch 'edits' must be a list.")

    normalized: list[dict[str, object]] = []
    for entry in edits:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id", "")).strip()
        changes = entry.get("changes", {})
        if not item_id or not isinstance(changes, dict):
            continue
        normalized.append({"item_id": item_id, "changes": changes})
    return normalized


def main() -> None:
    args = parse_args()
    patch = load_patch(args.input)
    edits = normalize_edits(patch)
    fieldnames, rows = read_csv(CATALOG)
    catalog_by_id = make_catalog_index(rows)

    warnings: list[str] = []
    summary = {
        "item_patches_seen": len(edits),
        "item_patches_applied": 0,
        "field_changes_applied": 0,
        "field_changes_skipped": 0,
    }

    source = patch.get("source", {})
    if isinstance(source, dict):
        patch_mtime = str(source.get("catalog_csv_mtime", "")).strip()
        current_mtime = file_mtime(CATALOG)
        if patch_mtime and patch_mtime != current_mtime:
            warnings.append(
                f"Catalog CSV mtime differs from patch source. Patch saw '{patch_mtime}', current file is '{current_mtime}'."
            )

    for entry in edits:
        item_id = str(entry["item_id"])
        changes = entry["changes"]

        if item_id not in catalog_by_id:
            warnings.append(f"Item {item_id} does not exist in wardrobe_catalog.csv; skipped.")
            summary["field_changes_skipped"] += len(changes) if isinstance(changes, dict) else 0
            continue

        row = catalog_by_id[item_id]
        item_changed = False

        for field_name, change in changes.items():
            if field_name not in EDITABLE_FIELDS:
                warnings.append(f"{item_id}: field '{field_name}' is not editable; skipped.")
                summary["field_changes_skipped"] += 1
                continue

            if field_name not in fieldnames:
                warnings.append(f"{item_id}: field '{field_name}' is not present in the current CSV header; skipped.")
                summary["field_changes_skipped"] += 1
                continue

            if not isinstance(change, dict):
                warnings.append(f"{item_id}: field '{field_name}' change payload is malformed; skipped.")
                summary["field_changes_skipped"] += 1
                continue

            old_value = str(change.get("old_value", ""))
            new_value = str(change.get("new_value", ""))
            current_value = row.get(field_name, "")

            if current_value == new_value:
                continue

            if current_value != old_value and not args.force:
                warnings.append(
                    f"{item_id}: field '{field_name}' current value does not match patch old_value; skipped. "
                    f"Current='{current_value}' PatchOld='{old_value}'"
                )
                summary["field_changes_skipped"] += 1
                continue

            row[field_name] = new_value
            item_changed = True
            summary["field_changes_applied"] += 1

        if item_changed:
            summary["item_patches_applied"] += 1

    if args.apply:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = args.backup_dir
        if backup_dir is None:
            backup_dir = WORKING / "review_backups" / timestamp
        elif not backup_dir.is_absolute():
            backup_dir = (WARDROBE / backup_dir).resolve()

        backup_file(CATALOG, backup_dir)
        write_csv(CATALOG, fieldnames, rows)
        print(f"Applied catalog edits. Backup written to {backup_dir / CATALOG.name}")
    else:
        print("Dry run only. No CSV files were changed. Re-run with --apply to write updates.")

    print(f"Item patches seen: {summary['item_patches_seen']}")
    print(f"Item patches applied: {summary['item_patches_applied']}")
    print(f"Field changes applied: {summary['field_changes_applied']}")
    print(f"Field changes skipped: {summary['field_changes_skipped']}")

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
