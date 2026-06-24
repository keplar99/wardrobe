import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "backend"))

import llm  # noqa: E402
from db import apply_schema, list_catalog_items  # noqa: E402
from catalog_import import (  # noqa: E402
    UploadedImage,
    create_import_batch,
    get_import_batch,
    publish_draft_item,
    process_import_batch,
    reject_draft_item,
    update_draft_item,
    write_unique_file,
)
from llm import LLMError, OpenAICatalogProvider, build_catalog_request_body  # noqa: E402


class FakeCatalogProvider:
    def generate_drafts(self, images, published_items):
        return {
            "draft_items": [
                {
                    "source_image_ids": [images[0]["id"]],
                    "proposed_item_id": "TOP",
                    "category": "Shirt",
                    "sub_category": "Linen shirt",
                    "brand": "Unidentified",
                    "color_primary": "warm white",
                    "color_secondary": "\u2014",
                    "pattern": "Solid",
                    "fit": "Regular",
                    "rise": "",
                    "length": "Long-sleeve",
                    "silhouette": "Straight",
                    "neckline": "Camp collar",
                    "drape_notes": "No worn photo available",
                    "fit_source": "Flat lay only",
                    "fabric": "linen",
                    "weight": "Light",
                    "stretch": "No",
                    "breathability": "High",
                    "surface_texture": "slubby",
                    "formality": 3,
                    "vibe_tags": "coastal, clean",
                    "occasion_tags": "brunch, beach/Goa",
                    "layering_position": "Base / open as outer",
                    "season": "Summer",
                    "max_comfortable_temp_c": "32",
                    "condition": "Good",
                    "wear_frequency_estimate": "Regular",
                    "color_temperature": "Warm",
                    "skin_tone_interaction": "Soft contrast on warm light-brown skin.",
                    "skin_tone_caution_flag": "No",
                    "contrast_level": "Low",
                    "versatility_score": 4,
                    "role_in_outfit": "Supporting",
                    "volume_visual_weight": "Low",
                    "shoe_type": "",
                    "sole_profile": "",
                    "aesthetic_range": "",
                    "top_compatibility_note": "",
                    "client_notes": "Generated draft for review.",
                    "image_reference": "Img draft 1 (flat)",
                    "generation_notes": "Single flat lay image.",
                    "validation_warnings": [],
                    "representative_source_image_id": images[0]["id"],
                }
            ],
            "observations": [
                {
                    "draft_index": 0,
                    "category": "Shirt",
                    "observation_type": "Fit source",
                    "detail": "Only a flat lay was available.",
                    "action_needed": "Review fit after worn photo is added.",
                }
            ],
        }


class InvalidSourceImageProvider(FakeCatalogProvider):
    def generate_drafts(self, images, published_items):
        payload = super().generate_drafts(images, published_items)
        payload["draft_items"][0]["source_image_ids"] = [999999]
        payload["draft_items"][0]["representative_source_image_id"] = 999999
        return payload


class DuplicateSourceImageProvider(FakeCatalogProvider):
    def generate_drafts(self, images, published_items):
        payload = super().generate_drafts(images, published_items)
        payload["draft_items"][0]["source_image_ids"] = [
            images[0]["id"],
            images[0]["id"],
            images[0]["id"],
        ]
        return payload


class PublishedStatusProvider(FakeCatalogProvider):
    def generate_drafts(self, images, published_items):
        payload = super().generate_drafts(images, published_items)
        payload["draft_items"][0]["status"] = "published"
        return payload


class EmptyDraftsProvider:
    def generate_drafts(self, images, published_items):
        return {"draft_items": [], "observations": []}


class PartialImageCoverageProvider(FakeCatalogProvider):
    def generate_drafts(self, images, published_items):
        return super().generate_drafts(images, published_items)


class MalformedWarningsProvider(FakeCatalogProvider):
    def __init__(self, validation_warnings):
        self.validation_warnings = validation_warnings

    def generate_drafts(self, images, published_items):
        payload = super().generate_drafts(images, published_items)
        payload["draft_items"][0]["validation_warnings"] = self.validation_warnings
        return payload


class MissingWarningsProvider(FakeCatalogProvider):
    def generate_drafts(self, images, published_items):
        payload = super().generate_drafts(images, published_items)
        del payload["draft_items"][0]["validation_warnings"]
        return payload


class ObservesProcessingStatusProvider(FakeCatalogProvider):
    def __init__(self, db_path):
        self.db_path = db_path
        self.observed_statuses = []

    def generate_drafts(self, images, published_items):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            placeholders = ", ".join("?" for _ in images)
            rows = conn.execute(
                f"SELECT status FROM import_images WHERE id IN ({placeholders}) ORDER BY id",
                [image["id"] for image in images],
            ).fetchall()
            self.observed_statuses = [row["status"] for row in rows]
        finally:
            conn.close()
        return super().generate_drafts(images, published_items)


class CountingCatalogProvider(FakeCatalogProvider):
    def __init__(self):
        self.calls = 0

    def generate_drafts(self, images, published_items):
        self.calls += 1
        return super().generate_drafts(images, published_items)


class StaleClaimConnection(sqlite3.Connection):
    def execute(self, sql, parameters=()):
        if (
            "UPDATE import_images" in sql
            and "status = 'processing'" in sql
            and "AND status IN ('uploaded', 'failed')" in sql
            and not getattr(self, "_stale_claim_applied", False)
        ):
            self._stale_claim_applied = True
            placeholders = ", ".join("?" for _ in parameters)
            super().execute(
                f"UPDATE import_images SET status = 'processing' WHERE id IN ({placeholders})",
                parameters,
            )
        return super().execute(sql, parameters)


class CatalogImportAITests(unittest.TestCase):
    def make_openai_catalog_provider(self):
        provider = object.__new__(OpenAICatalogProvider)
        provider.api_key = "test-key"
        provider.model = "gpt-test"
        return provider

    def test_build_catalog_request_body_includes_image_data_urls_and_schema(self):
        body = build_catalog_request_body(
            model="gpt-test",
            images=[
                {
                    "id": 7,
                    "canonical_filename": "shirt.jpeg",
                    "canonical_path": "/tmp/shirt.jpeg",
                    "original_filename": "shirt-original.jpeg",
                    "content_type": "image/jpeg",
                    "data_url": "data:image/jpeg;base64,YWJj",
                }
            ],
            published_items=[{"item_id": "TOP-01", "category": "Shirt"}],
        )

        self.assertEqual(body["model"], "gpt-test")
        content = body["input"][0]["content"]
        image_parts = [part for part in content if part["type"] == "input_image"]
        self.assertEqual(image_parts[0]["image_url"], "data:image/jpeg;base64,YWJj")
        self.assertEqual(body["text"]["format"]["name"], "wardrobe_catalog_drafts")
        self.assertIn("draft_items", body["text"]["format"]["schema"]["properties"])
        self.assertEqual(body["text"]["format"]["strict"], True)

    def test_catalog_draft_schema_requires_all_object_properties(self):
        def assert_strict_objects(schema):
            if schema.get("type") == "object":
                properties = schema.get("properties", {})
                self.assertEqual(schema.get("additionalProperties"), False)
                self.assertEqual(set(schema.get("required", [])), set(properties.keys()))
                for child in properties.values():
                    assert_strict_objects(child)
            if schema.get("type") == "array":
                assert_strict_objects(schema["items"])

        assert_strict_objects(llm.CATALOG_DRAFT_SCHEMA)

    def test_openai_catalog_provider_wraps_unreadable_image_as_llm_error(self):
        with self.assertRaises(LLMError) as caught:
            self.make_openai_catalog_provider().generate_drafts(
                [
                    {
                        "id": 7,
                        "canonical_filename": "missing.jpeg",
                        "canonical_path": "/tmp/wardrobe-missing-image.jpeg",
                        "original_filename": "missing-original.jpeg",
                        "content_type": "image/jpeg",
                        "status": "processing",
                    }
                ],
                [],
            )

        self.assertIn("Could not read import image missing.jpeg", str(caught.exception))

    def test_openai_catalog_provider_rejects_unsupported_image_mime_type(self):
        with self.assertRaises(LLMError) as caught:
            self.make_openai_catalog_provider().generate_drafts(
                [
                    {
                        "id": 7,
                        "canonical_filename": "shirt.heic",
                        "canonical_path": "/tmp/wardrobe-missing-image.heic",
                        "original_filename": "shirt-original.heic",
                        "content_type": "image/heic",
                        "status": "processing",
                    }
                ],
                [],
            )

        self.assertEqual(
            str(caught.exception),
            "Unsupported OpenAI image MIME type for shirt.heic: image/heic",
        )

    def test_openai_catalog_provider_rejects_too_large_single_image(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "large.jpeg"
            path.write_bytes(b"abcd")

            with mock.patch.object(llm, "MAX_CATALOG_IMAGE_BYTES", 3, create=True), mock.patch.object(
                llm.urllib.request,
                "urlopen",
                side_effect=AssertionError("network should not be called"),
            ):
                with self.assertRaises(LLMError) as caught:
                    self.make_openai_catalog_provider().generate_drafts(
                        [
                            {
                                "id": 7,
                                "canonical_filename": "large.jpeg",
                                "canonical_path": str(path),
                                "original_filename": "large-original.jpeg",
                                "content_type": "image/jpeg",
                                "status": "processing",
                            }
                        ],
                        [],
                    )

        self.assertIn("Import image large.jpeg is too large", str(caught.exception))

    def test_openai_catalog_provider_rejects_too_large_image_batch(self):
        with tempfile.TemporaryDirectory() as tempdir:
            first = Path(tempdir) / "first.jpeg"
            second = Path(tempdir) / "second.jpeg"
            first.write_bytes(b"abc")
            second.write_bytes(b"abc")

            with mock.patch.object(
                llm,
                "MAX_CATALOG_IMAGE_BATCH_BYTES",
                5,
                create=True,
            ), mock.patch.object(
                llm.urllib.request,
                "urlopen",
                side_effect=AssertionError("network should not be called"),
            ):
                with self.assertRaises(LLMError) as caught:
                    self.make_openai_catalog_provider().generate_drafts(
                        [
                            {
                                "id": 7,
                                "canonical_filename": "first.jpeg",
                                "canonical_path": str(first),
                                "original_filename": "first-original.jpeg",
                                "content_type": "image/jpeg",
                                "status": "processing",
                            },
                            {
                                "id": 8,
                                "canonical_filename": "second.jpeg",
                                "canonical_path": str(second),
                                "original_filename": "second-original.jpeg",
                                "content_type": "image/jpeg",
                                "status": "processing",
                            },
                        ],
                        [],
                    )

        self.assertIn("Import image batch is too large", str(caught.exception))


class CatalogImportSchemaTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_apply_schema_creates_import_tables(self):
        apply_schema(self.conn)

        table_names = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        self.assertIn("import_batches", table_names)
        self.assertIn("import_images", table_names)
        self.assertIn("draft_items", table_names)
        self.assertIn("draft_item_images", table_names)
        self.assertIn("draft_observations", table_names)


class CatalogImportUploadTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        apply_schema(self.conn)
        self.tempdir = tempfile.TemporaryDirectory()
        self.raw_dir = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()
        self.conn.close()

    def test_create_import_batch_saves_canonical_files(self):
        batch = create_import_batch(
            self.conn,
            [
                UploadedImage("linen shirt.JPG", b"first image bytes", "image/jpeg"),
                UploadedImage("linen shirt.JPG", b"second image bytes", "image/jpeg"),
            ],
            raw_images_dir=self.raw_dir,
        )

        self.assertEqual(batch["status"], "uploaded")
        self.assertEqual(batch["original_file_count"], 2)
        self.assertEqual(batch["uploaded_file_count"], 2)
        self.assertEqual(len(batch["images"]), 2)
        filenames = [image["canonical_filename"] for image in batch["images"]]
        self.assertEqual(len(set(filenames)), 2)
        for image in batch["images"]:
            path = Path(image["canonical_path"])
            self.assertTrue(path.exists())
            self.assertEqual(path.parent, self.raw_dir)
            self.assertEqual(image["status"], "uploaded")

    def test_create_import_batch_rejects_non_images(self):
        with self.assertRaises(ValueError) as caught:
            create_import_batch(
                self.conn,
                [UploadedImage("notes.txt", b"not an image", "text/plain")],
                raw_images_dir=self.raw_dir,
            )

        self.assertEqual(str(caught.exception), "Unsupported image type: notes.txt")

    def test_create_import_batch_rejects_more_than_100_images(self):
        files = [
            UploadedImage(f"image-{index}.jpeg", b"image bytes", "image/jpeg")
            for index in range(101)
        ]

        with self.assertRaises(ValueError) as caught:
            create_import_batch(self.conn, files, raw_images_dir=self.raw_dir)

        self.assertEqual(str(caught.exception), "Upload at most 100 images at a time.")

    def test_get_import_batch_returns_images(self):
        created = create_import_batch(
            self.conn,
            [UploadedImage("tee.png", b"png bytes", "image/png")],
            raw_images_dir=self.raw_dir,
        )

        loaded = get_import_batch(self.conn, created["id"])

        self.assertEqual(loaded["id"], created["id"])
        self.assertEqual(loaded["images"][0]["original_filename"], "tee.png")

    def test_create_import_batch_removes_written_files_if_image_insert_fails(self):
        self.conn.execute(
            """
            CREATE TRIGGER fail_import_image_insert
            BEFORE INSERT ON import_images
            BEGIN
              SELECT RAISE(FAIL, 'forced import image failure');
            END
            """
        )

        with self.assertRaises(sqlite3.IntegrityError):
            create_import_batch(
                self.conn,
                [UploadedImage("tee.png", b"png bytes", "image/png")],
                raw_images_dir=self.raw_dir,
            )

        self.assertEqual(list(self.raw_dir.iterdir()), [])
        batch_count = self.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
        self.assertEqual(batch_count, 0)

    def test_write_unique_file_removes_created_path_if_write_fails(self):
        target = self.raw_dir / "partial.png"

        with self.assertRaises(TypeError):
            write_unique_file(target, object())

        self.assertFalse(target.exists())


class CatalogImportProcessingTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        apply_schema(self.conn)
        self.tempdir = tempfile.TemporaryDirectory()
        self.raw_dir = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()
        self.conn.close()

    def create_processed_batch(self):
        batch = create_import_batch(
            self.conn,
            [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
            raw_images_dir=self.raw_dir,
        )
        return process_import_batch(self.conn, batch["id"], FakeCatalogProvider(), limit=10)

    def test_process_import_batch_creates_reviewable_draft(self):
        batch = create_import_batch(
            self.conn,
            [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
            raw_images_dir=self.raw_dir,
        )

        processed = process_import_batch(self.conn, batch["id"], FakeCatalogProvider(), limit=10)

        self.assertEqual(processed["status"], "needs_review")
        self.assertEqual(processed["processed_file_count"], 1)
        self.assertEqual(len(processed["draft_items"]), 1)
        draft = processed["draft_items"][0]
        self.assertEqual(draft["status"], "needs_review")
        self.assertEqual(draft["category"], "Shirt")
        self.assertEqual(draft["images"][0]["canonical_filename"].endswith("shirt.jpeg"), True)
        self.assertEqual(processed["observations"][0]["observation_type"], "Fit source")

    def test_invalid_source_image_ids_fail_chunk_without_processing_leftovers(self):
        batch = create_import_batch(
            self.conn,
            [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
            raw_images_dir=self.raw_dir,
        )

        processed = process_import_batch(self.conn, batch["id"], InvalidSourceImageProvider(), limit=10)

        self.assertEqual(processed["status"], "failed")
        self.assertEqual(processed["processed_file_count"], 0)
        self.assertEqual(processed["draft_items"], [])
        self.assertEqual(processed["images"][0]["status"], "failed")
        self.assertIn("source_image_ids", processed["images"][0]["error_message"])

    def test_duplicate_source_image_ids_create_one_mapping(self):
        batch = create_import_batch(
            self.conn,
            [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
            raw_images_dir=self.raw_dir,
        )

        processed = process_import_batch(self.conn, batch["id"], DuplicateSourceImageProvider(), limit=10)

        self.assertEqual(processed["status"], "needs_review")
        self.assertEqual(len(processed["draft_items"][0]["images"]), 1)
        mapping_count = self.conn.execute("SELECT COUNT(*) FROM draft_item_images").fetchone()[0]
        self.assertEqual(mapping_count, 1)

    def test_provider_published_status_still_requires_review(self):
        batch = create_import_batch(
            self.conn,
            [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
            raw_images_dir=self.raw_dir,
        )

        processed = process_import_batch(self.conn, batch["id"], PublishedStatusProvider(), limit=10)

        self.assertEqual(processed["status"], "needs_review")
        self.assertEqual(processed["draft_items"][0]["status"], "needs_review")

    def test_empty_draft_items_fail_chunk_without_processing_leftovers(self):
        batch = create_import_batch(
            self.conn,
            [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
            raw_images_dir=self.raw_dir,
        )

        processed = process_import_batch(self.conn, batch["id"], EmptyDraftsProvider(), limit=10)

        self.assertNotEqual(processed["status"], "processing")
        self.assertEqual(processed["images"][0]["status"], "failed")
        self.assertEqual(processed["draft_items"], [])

    def test_partial_image_coverage_fails_chunk_without_partial_drafts(self):
        batch = create_import_batch(
            self.conn,
            [
                UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg"),
                UploadedImage("pants.jpeg", b"pants bytes", "image/jpeg"),
            ],
            raw_images_dir=self.raw_dir,
        )

        processed = process_import_batch(self.conn, batch["id"], PartialImageCoverageProvider(), limit=10)

        self.assertNotEqual(processed["status"], "processing")
        self.assertEqual([image["status"] for image in processed["images"]], ["failed", "failed"])
        self.assertEqual(processed["draft_items"], [])
        draft_count = self.conn.execute("SELECT COUNT(*) FROM draft_items").fetchone()[0]
        self.assertEqual(draft_count, 0)

    def test_malformed_validation_warnings_decode_as_list(self):
        cases = [
            (MalformedWarningsProvider("review color"), ["review color"]),
            (MalformedWarningsProvider([1, None, "review fit"]), ["1", "None", "review fit"]),
            (MalformedWarningsProvider({"field": "color"}), ["{'field': 'color'}"]),
            (MissingWarningsProvider(), []),
        ]

        for provider, expected in cases:
            with self.subTest(expected=expected):
                batch = create_import_batch(
                    self.conn,
                    [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
                    raw_images_dir=self.raw_dir,
                )

                processed = process_import_batch(self.conn, batch["id"], provider, limit=10)

                self.assertEqual(processed["draft_items"][0]["validation_warnings"], expected)

    def test_update_draft_item_reuses_catalog_validation(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]

        updated = update_draft_item(
            self.conn,
            draft_id,
            {"brand": "Muji", "formality": "4", "generation_notes": "Reviewed by hand."},
        )

        self.assertEqual(updated["brand"], "Muji")
        self.assertEqual(updated["formality"], 4)
        self.assertEqual(updated["generation_notes"], "Reviewed by hand.")

    def test_publish_draft_item_creates_live_catalog_item(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]

        item = publish_draft_item(self.conn, draft_id)

        self.assertEqual(item["item_id"], "TOP-01")
        self.assertEqual(item["category"], "Shirt")
        self.assertTrue(item["representative_image"]["filename"].endswith("shirt.jpeg"))
        self.assertEqual([item["item_id"] for item in list_catalog_items(self.conn, "all")], ["TOP-01"])

    def test_reject_draft_item_keeps_it_out_of_live_catalog(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]

        rejected = reject_draft_item(self.conn, draft_id)

        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(list_catalog_items(self.conn, "all"), [])

    def test_rejected_draft_item_cannot_be_published(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]
        reject_draft_item(self.conn, draft_id)

        with self.assertRaises(ValueError) as caught:
            publish_draft_item(self.conn, draft_id)

        self.assertEqual(str(caught.exception), "Rejected draft items cannot be published.")
        self.assertEqual(list_catalog_items(self.conn, "all"), [])

    def test_reject_draft_item_sets_terminal_batch_and_image_statuses(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]

        reject_draft_item(self.conn, draft_id)
        batch = get_import_batch(self.conn, processed["id"])

        self.assertEqual(batch["status"], "failed")
        self.assertEqual(batch["processed_file_count"], 1)
        self.assertEqual(batch["images"][0]["status"], "rejected")

    def test_publish_draft_item_is_idempotent_without_duplicate_images(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]

        first = publish_draft_item(self.conn, draft_id)
        second = publish_draft_item(self.conn, draft_id)

        self.assertEqual(first["item_id"], second["item_id"])
        image_count = self.conn.execute(
            "SELECT COUNT(*) FROM item_images WHERE item_id = ?",
            (first["item_id"],),
        ).fetchone()[0]
        self.assertEqual(image_count, 1)

    def test_publish_draft_item_skips_existing_item_ids(self):
        first_batch = self.create_processed_batch()
        publish_draft_item(self.conn, first_batch["draft_items"][0]["id"])
        second_batch = self.create_processed_batch()

        item = publish_draft_item(self.conn, second_batch["draft_items"][0]["id"])

        self.assertEqual(item["item_id"], "TOP-02")

    def test_publish_draft_item_locks_item_id_allocation(self):
        processed = self.create_processed_batch()
        statements = []
        self.conn.set_trace_callback(statements.append)
        try:
            publish_draft_item(self.conn, processed["draft_items"][0]["id"])
        finally:
            self.conn.set_trace_callback(None)

        self.assertIn("BEGIN IMMEDIATE", statements)

    def test_process_import_batch_commits_processing_claim_before_provider_call(self):
        with tempfile.TemporaryDirectory() as db_dir:
            db_path = Path(db_dir) / "wardrobe.sqlite"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            apply_schema(conn)
            try:
                batch = create_import_batch(
                    conn,
                    [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
                    raw_images_dir=self.raw_dir,
                )
                provider = ObservesProcessingStatusProvider(db_path)

                process_import_batch(conn, batch["id"], provider, limit=10)

                self.assertEqual(provider.observed_statuses, ["processing"])
            finally:
                conn.close()

    def test_process_import_batch_rejects_stale_processing_claim(self):
        conn = sqlite3.connect(":memory:", factory=StaleClaimConnection)
        conn.row_factory = sqlite3.Row
        apply_schema(conn)
        provider = CountingCatalogProvider()
        try:
            batch = create_import_batch(
                conn,
                [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
                raw_images_dir=self.raw_dir,
            )

            with self.assertRaises(ValueError) as caught:
                process_import_batch(conn, batch["id"], provider, limit=10)

            self.assertEqual(str(caught.exception), "Import images were already claimed for processing.")
            self.assertEqual(provider.calls, 0)
            draft_count = conn.execute("SELECT COUNT(*) FROM draft_items").fetchone()[0]
            self.assertEqual(draft_count, 0)
        finally:
            conn.close()

    def test_reject_draft_item_refuses_published_drafts(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]
        publish_draft_item(self.conn, draft_id)

        with self.assertRaises(ValueError) as caught:
            reject_draft_item(self.conn, draft_id)

        self.assertEqual(str(caught.exception), "Published draft items cannot be rejected.")
        batch = get_import_batch(self.conn, processed["id"])
        self.assertEqual(batch["draft_items"][0]["status"], "published")
        self.assertEqual([item["item_id"] for item in list_catalog_items(self.conn, "all")], ["TOP-01"])

    def test_publish_draft_item_preserves_caller_transaction(self):
        processed = self.create_processed_batch()
        self.conn.execute("BEGIN")

        try:
            publish_draft_item(self.conn, processed["draft_items"][0]["id"])

            self.assertTrue(self.conn.in_transaction)
        finally:
            if self.conn.in_transaction:
                self.conn.rollback()


if __name__ == "__main__":
    unittest.main()
