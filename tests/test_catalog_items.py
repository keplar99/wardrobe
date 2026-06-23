import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "backend"))

from db import (  # noqa: E402
    CatalogValidationError,
    apply_schema,
    delete_catalog_item,
    get_catalog_item,
    list_items_for_prompt,
    list_catalog_items,
    list_saved_outfits,
    save_outfit,
    update_catalog_item,
)
import db  # noqa: E402


TEXT_FIELDS = [
    "category",
    "sub_category",
    "brand",
    "color_primary",
    "color_secondary",
    "pattern",
    "fit",
    "rise",
    "length",
    "silhouette",
    "neckline",
    "drape_notes",
    "fit_source",
    "fabric",
    "weight",
    "stretch",
    "breathability",
    "surface_texture",
    "vibe_tags",
    "occasion_tags",
    "layering_position",
    "season",
    "max_comfortable_temp_c",
    "condition",
    "wear_frequency_estimate",
    "color_temperature",
    "skin_tone_interaction",
    "skin_tone_caution_flag",
    "contrast_level",
    "role_in_outfit",
    "volume_visual_weight",
    "shoe_type",
    "sole_profile",
    "aesthetic_range",
    "top_compatibility_note",
    "client_notes",
]


def make_item(item_id, category, **overrides):
    item = {field: "" for field in TEXT_FIELDS}
    item.update(
        {
            "item_id": item_id,
            "category": category,
            "sub_category": f"{category} sub",
            "brand": "Unidentified",
            "color_primary": "navy",
            "color_secondary": "—",
            "pattern": "Solid",
            "fit": "Regular",
            "condition": "Good",
            "formality": 3,
            "versatility_score": 4,
            "raw_json": "{}",
        }
    )
    item.update(overrides)
    return item


class CatalogItemTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        apply_schema(self.conn)
        self.insert_item(make_item("TOP-01", "T-Shirt", client_notes="soft tee"))
        self.insert_item(make_item("BOT-01", "Trousers", color_primary="khaki"))
        self.insert_item(make_item("SHOE-01", "Shoes", shoe_type="Sneaker"))
        self.conn.execute(
            """
            INSERT INTO item_images
              (item_id, filename, path, image_reference, is_representative)
            VALUES
              ('TOP-01', 'top-flat.jpeg', '/tmp/top-flat.jpeg', 'Img 1 (flat)', 0),
              ('TOP-01', 'top-worn.jpeg', '/tmp/top-worn.jpeg', 'Img 2 (worn)', 1)
            """
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def insert_item(self, item):
        columns = list(item.keys())
        placeholders = ", ".join("?" for _ in columns)
        self.conn.execute(
            f"INSERT INTO items ({', '.join(columns)}) VALUES ({placeholders})",
            [item[column] for column in columns],
        )

    def test_lists_catalog_items_filtered_by_type_with_representative_image(self):
        tops = list_catalog_items(self.conn, "top")

        self.assertEqual([item["item_id"] for item in tops], ["TOP-01"])
        self.assertEqual(tops[0]["type"], "top")
        self.assertEqual(tops[0]["representative_image"]["filename"], "top-worn.jpeg")

    def test_get_catalog_item_returns_all_images(self):
        item = get_catalog_item(self.conn, "TOP-01")

        self.assertEqual(item["item_id"], "TOP-01")
        self.assertEqual([image["filename"] for image in item["images"]], ["top-worn.jpeg", "top-flat.jpeg"])

    def test_updates_editable_item_fields_and_persists(self):
        updated = update_catalog_item(
            self.conn,
            "TOP-01",
            {"brand": "Muji", "client_notes": "great under overshirts", "formality": "4"},
        )

        self.assertEqual(updated["brand"], "Muji")
        self.assertEqual(updated["client_notes"], "great under overshirts")
        self.assertEqual(updated["formality"], 4)
        persisted = get_catalog_item(self.conn, "TOP-01")
        self.assertEqual(persisted["brand"], "Muji")

    def test_blank_numeric_update_is_stored_as_null(self):
        updated = update_catalog_item(self.conn, "TOP-01", {"versatility_score": ""})

        self.assertIsNone(updated["versatility_score"])

    def test_rejects_unknown_and_read_only_fields(self):
        with self.assertRaises(CatalogValidationError):
            update_catalog_item(self.conn, "TOP-01", {"not_a_field": "x"})

        with self.assertRaises(CatalogValidationError):
            update_catalog_item(self.conn, "TOP-01", {"item_id": "TOP-99"})

    def test_rejects_invalid_numeric_fields(self):
        with self.assertRaises(CatalogValidationError):
            update_catalog_item(self.conn, "TOP-01", {"formality": "smart casual"})

    def test_deletes_catalog_item_softly_and_keeps_mapped_images(self):
        deleted = delete_catalog_item(self.conn, "TOP-01")

        self.assertTrue(deleted)
        item = get_catalog_item(self.conn, "TOP-01")
        self.assertIsNotNone(item)
        self.assertIsNotNone(item["deleted_at"])
        image_count = self.conn.execute(
            "SELECT COUNT(*) FROM item_images WHERE item_id = 'TOP-01'"
        ).fetchone()[0]
        self.assertEqual(image_count, 2)

    def test_soft_deleted_catalog_items_are_excluded_from_prompt_and_type_buckets(self):
        delete_catalog_item(self.conn, "TOP-01")

        prompt_ids = {item["item_id"] for item in list_items_for_prompt(self.conn)}
        buckets = db.item_ids_by_category(self.conn)

        self.assertNotIn("TOP-01", prompt_ids)
        self.assertNotIn("TOP-01", buckets["tops"])
        self.assertIn("BOT-01", prompt_ids)

    def test_saved_outfits_keep_soft_deleted_items_with_deleted_marker(self):
        saved_id = save_outfit(
            self.conn,
            {
                "title": "Saved office outfit",
                "time_of_day": "all-day",
                "occasion": "office",
                "stylist_notes": "A useful saved outfit with enough surrounding context for display.",
                "why_it_works": "The tones stay cohesive while the proportions remain office appropriate.",
                "wearing_notes": "Wear the tee tucked slightly and keep the shoes clean.",
                "cautions": "Skip this if the office dress code is formal.",
                "item_ids": ["TOP-01", "BOT-01", "SHOE-01"],
                "item_roles": {"TOP-01": "top", "BOT-01": "bottom", "SHOE-01": "shoes"},
            },
            None,
            None,
        )
        delete_catalog_item(self.conn, "TOP-01")

        saved = list_saved_outfits(self.conn)

        self.assertEqual(saved[0]["id"], saved_id)
        self.assertEqual(
            saved[0]["why_it_works"],
            "The tones stay cohesive while the proportions remain office appropriate.",
        )
        self.assertEqual(saved[0]["wearing_notes"], "Wear the tee tucked slightly and keep the shoes clean.")
        self.assertEqual(saved[0]["cautions"], "Skip this if the office dress code is formal.")
        top = next(item for item in saved[0]["items"] if item["item_id"] == "TOP-01")
        self.assertIsNotNone(top["deleted_at"])

    def test_deletes_saved_outfit_snapshot_and_join_rows(self):
        saved_id = save_outfit(
            self.conn,
            {
                "title": "Saved office outfit",
                "time_of_day": "all-day",
                "occasion": "office",
                "stylist_notes": "A useful saved outfit with enough surrounding context for display.",
                "item_ids": ["TOP-01", "BOT-01", "SHOE-01"],
                "item_roles": {"TOP-01": "top", "BOT-01": "bottom", "SHOE-01": "shoes"},
            },
            None,
            None,
        )

        deleted = db.delete_saved_outfit(self.conn, saved_id)

        self.assertTrue(deleted)
        self.assertEqual(list_saved_outfits(self.conn), [])
        join_count = self.conn.execute(
            "SELECT COUNT(*) FROM saved_outfit_items WHERE saved_outfit_id = ?",
            (saved_id,),
        ).fetchone()[0]
        self.assertEqual(join_count, 0)

    def test_delete_missing_catalog_item_returns_false(self):
        deleted = delete_catalog_item(self.conn, "TOP-99")

        self.assertFalse(deleted)


if __name__ == "__main__":
    unittest.main()
