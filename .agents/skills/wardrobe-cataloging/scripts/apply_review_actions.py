#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
import re


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
REF_MAP = WORKING / "image_reference_map.csv"
OBS = WORKING / "observations_open_questions.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply manual review actions exported from wardrobe_review.html "
            "to wardrobe_catalog.csv, image_reference_map.csv, and "
            "observations_open_questions.csv."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to the exported review JSON.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the changes back to the CSVs. Without this flag the script runs in dry-run mode.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help=(
            "Directory for CSV backups when --apply is used. "
            "Default: working/review_backups/<timestamp>/"
        ),
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


def split_pipe_field(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def join_pipe_field(values: list[str]) -> str:
    return " | ".join(value for value in values if value)


def split_item_ids(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*,\s*", text) if part.strip()]


def join_item_ids(values: list[str]) -> str:
    return ", ".join(value for value in values if value)


def extract_img_id(value: str) -> str:
    match = re.search(r"(Img\s+\d+)", value or "")
    return match.group(1) if match else (value or "").strip()


def extract_img_ids(value: str) -> list[str]:
    return re.findall(r"Img\s+\d+", value or "")


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def append_note(existing: str, note: str) -> str:
    current = (existing or "").strip()
    if not current:
        return note
    if note in current:
        return current
    return current + " | " + note


def load_review_actions(path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    invalid_items_raw = data.get("invalid_items", [])
    detached_images_raw = data.get("detached_images", [])

    invalid_items = invalid_items_raw if isinstance(invalid_items_raw, list) else list(invalid_items_raw.values())
    detached_images = detached_images_raw if isinstance(detached_images_raw, list) else list(detached_images_raw.values())

    normalized_invalid_items: list[dict[str, object]] = []
    for entry in invalid_items:
        if not isinstance(entry, dict) or not entry.get("item_id"):
            continue
        normalized_invalid_items.append(
            {
                "item_id": str(entry["item_id"]),
                "filenames": [str(value) for value in entry.get("filenames", []) if value],
                "catalog_refs": [str(value) for value in entry.get("catalog_refs", []) if value],
                "marked_at": str(entry.get("marked_at", "")),
            }
        )

    normalized_detached_images: list[dict[str, object]] = []
    for entry in detached_images:
        if not isinstance(entry, dict) or not entry.get("item_id") or not entry.get("filename"):
            continue
        normalized_detached_images.append(
            {
                "item_id": str(entry["item_id"]),
                "filename": str(entry["filename"]),
                "catalog_ref": str(entry.get("catalog_ref", "")),
                "reference_image_ids": [str(value) for value in entry.get("reference_image_ids", []) if value],
                "other_item_ids": [str(value) for value in entry.get("other_item_ids", []) if value],
                "marked_at": str(entry.get("marked_at", "")),
            }
        )

    return normalized_invalid_items, normalized_detached_images


def make_catalog_index(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        item_id = row["Item ID"].strip()
        index[item_id] = row
    return index


def backup_files(paths: list[Path], backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, backup_dir / path.name)


def main() -> None:
    args = parse_args()

    invalid_items, detached_images = load_review_actions(args.input)
    catalog_fields, catalog_rows = read_csv(CATALOG)
    ref_fields, ref_rows = read_csv(REF_MAP)
    obs_fields, obs_rows = read_csv(OBS)

    review_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    warnings: list[str] = []
    summary = {
        "catalog_rows_removed": 0,
        "catalog_rows_updated": 0,
        "image_ref_rows_updated": 0,
        "observation_rows_removed": 0,
        "detached_images_applied": 0,
        "invalid_items_applied": 0,
    }

    invalid_item_ids_requested = [str(entry["item_id"]) for entry in invalid_items]
    invalid_item_ids_requested_set = set(invalid_item_ids_requested)
    catalog_by_id = make_catalog_index(catalog_rows)

    valid_invalid_item_ids: set[str] = set()
    for entry in invalid_items:
        item_id = str(entry["item_id"])
        if item_id not in catalog_by_id:
            warnings.append(f"Invalid-item action skipped: {item_id} does not exist in wardrobe_catalog.csv")
            continue
        valid_invalid_item_ids.add(item_id)
        summary["invalid_items_applied"] += 1

    if valid_invalid_item_ids:
        kept_catalog_rows: list[dict[str, str]] = []
        for row in catalog_rows:
            item_id = row["Item ID"].strip()
            if item_id in valid_invalid_item_ids:
                summary["catalog_rows_removed"] += 1
            else:
                kept_catalog_rows.append(row)
        catalog_rows = kept_catalog_rows
        catalog_by_id = make_catalog_index(catalog_rows)

        updated_ref_rows = 0
        for row in ref_rows:
            mapped_ids = split_item_ids(row["Mapped Item ID(s)"])
            removed_item_ids = [item_id for item_id in mapped_ids if item_id in valid_invalid_item_ids]
            if not removed_item_ids:
                continue
            row["Mapped Item ID(s)"] = join_item_ids([item_id for item_id in mapped_ids if item_id not in valid_invalid_item_ids])
            row["Notes"] = append_note(
                row.get("Notes", ""),
                f"Manual review cleanup {review_stamp}: removed invalid item mapping(s) {', '.join(removed_item_ids)}",
            )
            updated_ref_rows += 1
        summary["image_ref_rows_updated"] += updated_ref_rows

        kept_obs_rows: list[dict[str, str]] = []
        for row in obs_rows:
            if row["Item ID"].strip() in valid_invalid_item_ids:
                summary["observation_rows_removed"] += 1
            else:
                kept_obs_rows.append(row)
        obs_rows = kept_obs_rows

    detached_images = [
        entry for entry in detached_images if str(entry["item_id"]) not in invalid_item_ids_requested_set
    ]

    for entry in detached_images:
        item_id = str(entry["item_id"])
        filename = str(entry["filename"])
        requested_ref_ids = dedupe_keep_order(
            [str(entry.get("catalog_ref", ""))] +
            [str(value) for value in entry.get("reference_image_ids", []) if value]
        )

        if item_id not in catalog_by_id:
            warnings.append(
                f"Detached-image action skipped: {item_id} does not exist in wardrobe_catalog.csv "
                f"(possibly already removed by an invalid-item action)."
            )
            continue

        row = catalog_by_id[item_id]
        filenames = split_pipe_field(row["Item Image Name"])
        image_refs = split_pipe_field(row["Image References"])

        matching_indexes = [index for index, value in enumerate(filenames) if value == filename]
        if not matching_indexes:
            warnings.append(
                f"Detached-image action skipped: {filename} is not currently listed under {item_id}."
            )
            continue

        chosen_index = matching_indexes[0]
        for index in matching_indexes:
            if index < len(image_refs) and extract_img_id(image_refs[index]) in requested_ref_ids:
                chosen_index = index
                break

        removed_ref_label = image_refs.pop(chosen_index) if chosen_index < len(image_refs) else ""
        filenames.pop(chosen_index)

        summary["detached_images_applied"] += 1

        if filenames:
            row["Item Image Name"] = join_pipe_field(filenames)
            row["Image References"] = join_pipe_field(image_refs)
            summary["catalog_rows_updated"] += 1
        else:
            catalog_rows = [catalog_row for catalog_row in catalog_rows if catalog_row["Item ID"].strip() != item_id]
            catalog_by_id.pop(item_id, None)
            summary["catalog_rows_removed"] += 1

            kept_obs_rows = []
            for obs_row in obs_rows:
                if obs_row["Item ID"].strip() == item_id:
                    summary["observation_rows_removed"] += 1
                else:
                    kept_obs_rows.append(obs_row)
            obs_rows = kept_obs_rows

        ref_row_updated = False
        for ref_row in ref_rows:
            if ref_row["Image Filename"].strip() != filename:
                continue
            mapped_ids = split_item_ids(ref_row["Mapped Item ID(s)"])
            if item_id not in mapped_ids:
                continue
            ref_row["Mapped Item ID(s)"] = join_item_ids([mapped_id for mapped_id in mapped_ids if mapped_id != item_id])
            ref_row["Notes"] = append_note(
                ref_row.get("Notes", ""),
                f"Manual review cleanup {review_stamp}: removed {filename} from {item_id}",
            )
            ref_row_updated = True
            summary["image_ref_rows_updated"] += 1

        if not ref_row_updated:
            warnings.append(
                f"Reference-map row not found for detached image action: {filename} under {item_id}."
            )

        if item_id in catalog_by_id:
            relevant_img_ids = set(dedupe_keep_order(
                requested_ref_ids + ([extract_img_id(removed_ref_label)] if removed_ref_label else [])
            ))
            if relevant_img_ids:
                kept_obs_rows = []
                for obs_row in obs_rows:
                    if obs_row["Item ID"].strip() != item_id:
                        kept_obs_rows.append(obs_row)
                        continue
                    obs_img_ids = set(extract_img_ids(obs_row.get("Image(s)", "")))
                    if relevant_img_ids.intersection(obs_img_ids):
                        summary["observation_rows_removed"] += 1
                    else:
                        kept_obs_rows.append(obs_row)
                obs_rows = kept_obs_rows

    if args.apply:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = args.backup_dir
        if backup_dir is None:
            backup_dir = WORKING / "review_backups" / timestamp
        elif not backup_dir.is_absolute():
            backup_dir = (WARDROBE / backup_dir).resolve()

        backup_files([CATALOG, REF_MAP, OBS], backup_dir)
        write_csv(CATALOG, catalog_fields, catalog_rows)
        write_csv(REF_MAP, ref_fields, ref_rows)
        write_csv(OBS, obs_fields, obs_rows)
        print(f"Applied review actions. Backups written to {backup_dir}")
    else:
        print("Dry run only. No CSV files were changed. Re-run with --apply to write updates.")

    print(f"Invalid items applied: {summary['invalid_items_applied']}")
    print(f"Detached images applied: {summary['detached_images_applied']}")
    print(f"Catalog rows removed: {summary['catalog_rows_removed']}")
    print(f"Catalog rows updated: {summary['catalog_rows_updated']}")
    print(f"Reference-map rows updated: {summary['image_ref_rows_updated']}")
    print(f"Observation rows removed: {summary['observation_rows_removed']}")

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
