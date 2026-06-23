from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

from db import RAW_IMAGES_DIR, ROOT, apply_schema, connect, reset_database

CATALOG_PATH = ROOT / "working" / "wardrobe_catalog.csv"

COL_MAP = {
    "Item ID": "item_id",
    "Category": "category",
    "Sub-Category": "sub_category",
    "Brand": "brand",
    "Color (Primary)": "color_primary",
    "Color (Secondary)": "color_secondary",
    "Pattern": "pattern",
    "Fit": "fit",
    "Rise": "rise",
    "Length": "length",
    "Silhouette": "silhouette",
    "Neckline": "neckline",
    "Drape Notes": "drape_notes",
    "Fit Source": "fit_source",
    "Fabric": "fabric",
    "Weight": "weight",
    "Stretch": "stretch",
    "Breathability": "breathability",
    "Surface Texture": "surface_texture",
    "Formality (1-5)": "formality",
    "Vibe Tags": "vibe_tags",
    "Occasion Tags": "occasion_tags",
    "Layering Position": "layering_position",
    "Season": "season",
    "Max Comfortable Temp (C)": "max_comfortable_temp_c",
    "Condition": "condition",
    "Wear Frequency Estimate": "wear_frequency_estimate",
    "Color Temperature": "color_temperature",
    "Skin Tone Interaction": "skin_tone_interaction",
    "Skin Tone Caution Flag": "skin_tone_caution_flag",
    "Contrast Level": "contrast_level",
    "Versatility Score (1-5)": "versatility_score",
    "Role in Outfit": "role_in_outfit",
    "Volume/Visual Weight": "volume_visual_weight",
    "Shoe Type": "shoe_type",
    "Sole Profile": "sole_profile",
    "Aesthetic Range": "aesthetic_range",
    "Top Compatibility Note": "top_compatibility_note",
    "Client notes": "client_notes",
}


def clean(value: str | None) -> str:
    return (value or "").strip()


def int_or_none(value: str | None) -> int | None:
    match = re.search(r"\d+", clean(value))
    return int(match.group(0)) if match else None


def split_filenames(value: str) -> list[str]:
    return [part.strip() for part in clean(value).split("|") if part.strip()]


def split_references(value: str, count: int) -> list[str]:
    refs = [part.strip() for part in clean(value).split(",") if part.strip()]
    if len(refs) < count:
        refs.extend([""] * (count - len(refs)))
    return refs[:count]


def representative_index(filenames: list[str], refs: list[str]) -> int:
    for index, ref in enumerate(refs):
        if "worn" in ref.lower():
            return index
    for index, filename in enumerate(filenames):
        if "worn" in filename.lower():
            return index
    return 0


def import_catalog(conn: sqlite3.Connection) -> tuple[int, int]:
    with CATALOG_PATH.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        item_count = 0
        image_count = 0
        for row in reader:
            item_id = clean(row.get("Item ID"))
            if not item_id:
                continue
            item = {target: clean(row.get(source)) for source, target in COL_MAP.items()}
            item["formality"] = int_or_none(row.get("Formality (1-5)"))
            item["versatility_score"] = int_or_none(row.get("Versatility Score (1-5)"))
            item["raw_json"] = json.dumps(row, ensure_ascii=False)
            columns = list(item.keys())
            placeholders = ", ".join("?" for _ in columns)
            conn.execute(
                f"INSERT OR REPLACE INTO items ({', '.join(columns)}) VALUES ({placeholders})",
                [item[col] for col in columns],
            )
            conn.execute("DELETE FROM item_images WHERE item_id = ?", (item_id,))

            filenames = split_filenames(row.get("Item Image Name", ""))
            refs = split_references(row.get("Image References", ""), len(filenames))
            rep_index = representative_index(filenames, refs) if filenames else -1
            for index, filename in enumerate(filenames):
                path = RAW_IMAGES_DIR / filename
                conn.execute(
                    """
                    INSERT INTO item_images (item_id, filename, path, image_reference, is_representative)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (item_id, filename, str(path), refs[index], 1 if index == rep_index else 0),
                )
                image_count += 1
            item_count += 1
    conn.commit()
    return item_count, image_count


def print_summary(conn: sqlite3.Connection) -> None:
    item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    image_count = conn.execute("SELECT COUNT(*) FROM item_images").fetchone()[0]
    represented = conn.execute("SELECT COUNT(*) FROM item_images WHERE is_representative = 1").fetchone()[0]
    print(f"items={item_count}")
    print(f"images={image_count}")
    print(f"representative_images={represented}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import wardrobe_catalog.csv into the app SQLite database.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate app tables before importing.")
    parser.add_argument("--summary", action="store_true", help="Print current import summary without importing.")
    args = parser.parse_args()

    conn = connect()
    if args.summary:
        apply_schema(conn)
        print_summary(conn)
        return
    if args.reset:
        reset_database(conn)
    else:
        apply_schema(conn)
    item_count, image_count = import_catalog(conn)
    print(f"imported_items={item_count}")
    print(f"imported_images={image_count}")


if __name__ == "__main__":
    main()
