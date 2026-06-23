# Wardrobe Catalog Import Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an import workflow where 1 to 100 uploaded wardrobe images are saved as canonical local assets, processed into reviewable draft catalog items in batches, and published into the live catalog only after review.

**Architecture:** Keep the live catalog unchanged until publication by adding SQLite draft tables and a focused backend import domain module. The backend owns canonical file storage, draft generation, validation, publishing, and route handling; the frontend adds a `/catalog/import` route that reuses the existing catalog field groups for draft review.

**Tech Stack:** Python standard library HTTP server, SQLite, React/Vite, lucide-react, OpenAI Responses API through the existing `urllib` provider pattern.

---

## File Map

- Modify `app/backend/schema.sql`: add import batch, import image, draft item, draft item image, and draft observation tables.
- Modify `app/backend/db.py`: drop new draft tables in `reset_database`.
- Create `app/backend/catalog_import.py`: import domain logic for uploads, listing, draft updates, processing, publishing, and rejection.
- Modify `app/backend/llm.py`: add image-capable catalog generation support while keeping outfit recommendation calls unchanged.
- Modify `app/backend/server.py`: add import API routes, multipart upload parsing, draft image streaming, and CORS method/header coverage.
- Modify `app/frontend/src/api.js`: add multipart upload request handling and import/draft API methods.
- Modify `app/frontend/src/App.jsx`: add `/catalog/import`, import navigation, upload page, batch list, process controls, draft review editor, publish/reject actions.
- Modify `app/frontend/src/styles.css`: style the import queue, upload controls, draft review list, and draft status states within the existing dense app design.
- Create `tests/test_catalog_import.py`: backend unit tests for upload, draft processing, updates, publish, reject, and live catalog visibility.

---

## Task 1: Draft Schema

**Files:**
- Modify: `app/backend/schema.sql`
- Modify: `app/backend/db.py`
- Test: `tests/test_catalog_import.py`

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_catalog_import.py` with:

```python
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "backend"))

from db import apply_schema  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportSchemaTests.test_apply_schema_creates_import_tables
```

Expected: FAIL with `AssertionError: 'import_batches' not found`.

- [ ] **Step 3: Add the draft tables**

Append these table definitions to `app/backend/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS import_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  status TEXT NOT NULL CHECK (status IN ('uploaded', 'processing', 'needs_review', 'partially_published', 'published', 'failed')),
  original_file_count INTEGER NOT NULL DEFAULT 0,
  uploaded_file_count INTEGER NOT NULL DEFAULT 0,
  processed_file_count INTEGER NOT NULL DEFAULT 0,
  published_item_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  original_filename TEXT NOT NULL,
  canonical_filename TEXT NOT NULL,
  canonical_path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('uploaded', 'processing', 'processed', 'failed', 'rejected', 'published')),
  draft_item_id INTEGER REFERENCES draft_items(id) ON DELETE SET NULL,
  error_message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_import_images_batch_id ON import_images(batch_id);
CREATE INDEX IF NOT EXISTS idx_import_images_draft_item_id ON import_images(draft_item_id);

CREATE TABLE IF NOT EXISTS draft_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('generated', 'needs_review', 'published', 'rejected')),
  proposed_item_id TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  sub_category TEXT NOT NULL DEFAULT '',
  brand TEXT NOT NULL DEFAULT '',
  color_primary TEXT NOT NULL DEFAULT '',
  color_secondary TEXT NOT NULL DEFAULT '',
  pattern TEXT NOT NULL DEFAULT '',
  fit TEXT NOT NULL DEFAULT '',
  rise TEXT NOT NULL DEFAULT '',
  length TEXT NOT NULL DEFAULT '',
  silhouette TEXT NOT NULL DEFAULT '',
  neckline TEXT NOT NULL DEFAULT '',
  drape_notes TEXT NOT NULL DEFAULT '',
  fit_source TEXT NOT NULL DEFAULT '',
  fabric TEXT NOT NULL DEFAULT '',
  weight TEXT NOT NULL DEFAULT '',
  stretch TEXT NOT NULL DEFAULT '',
  breathability TEXT NOT NULL DEFAULT '',
  surface_texture TEXT NOT NULL DEFAULT '',
  formality INTEGER,
  vibe_tags TEXT NOT NULL DEFAULT '',
  occasion_tags TEXT NOT NULL DEFAULT '',
  layering_position TEXT NOT NULL DEFAULT '',
  season TEXT NOT NULL DEFAULT '',
  max_comfortable_temp_c TEXT NOT NULL DEFAULT '',
  condition TEXT NOT NULL DEFAULT '',
  wear_frequency_estimate TEXT NOT NULL DEFAULT '',
  color_temperature TEXT NOT NULL DEFAULT '',
  skin_tone_interaction TEXT NOT NULL DEFAULT '',
  skin_tone_caution_flag TEXT NOT NULL DEFAULT '',
  contrast_level TEXT NOT NULL DEFAULT '',
  versatility_score INTEGER,
  role_in_outfit TEXT NOT NULL DEFAULT '',
  volume_visual_weight TEXT NOT NULL DEFAULT '',
  shoe_type TEXT NOT NULL DEFAULT '',
  sole_profile TEXT NOT NULL DEFAULT '',
  aesthetic_range TEXT NOT NULL DEFAULT '',
  top_compatibility_note TEXT NOT NULL DEFAULT '',
  client_notes TEXT NOT NULL DEFAULT '',
  image_reference TEXT NOT NULL DEFAULT '',
  generation_notes TEXT NOT NULL DEFAULT '',
  validation_warnings_json TEXT NOT NULL DEFAULT '[]',
  raw_model_json TEXT NOT NULL DEFAULT '{}',
  published_item_id TEXT REFERENCES items(item_id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_draft_items_batch_id ON draft_items(batch_id);

CREATE TABLE IF NOT EXISTS draft_item_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_item_id INTEGER NOT NULL REFERENCES draft_items(id) ON DELETE CASCADE,
  import_image_id INTEGER NOT NULL REFERENCES import_images(id) ON DELETE CASCADE,
  image_reference TEXT NOT NULL DEFAULT '',
  is_representative INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_draft_item_images_draft_item_id ON draft_item_images(draft_item_id);

CREATE TABLE IF NOT EXISTS draft_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  draft_item_id INTEGER REFERENCES draft_items(id) ON DELETE CASCADE,
  category TEXT NOT NULL DEFAULT '',
  observation_type TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  action_needed TEXT NOT NULL DEFAULT ''
);
```

In `app/backend/db.py`, add draft tables to `reset_database()` before dropping `items`:

```python
        DROP TABLE IF EXISTS draft_observations;
        DROP TABLE IF EXISTS draft_item_images;
        DROP TABLE IF EXISTS draft_items;
        DROP TABLE IF EXISTS import_images;
        DROP TABLE IF EXISTS import_batches;
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportSchemaTests.test_apply_schema_creates_import_tables
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/schema.sql app/backend/db.py tests/test_catalog_import.py
git commit -m "Add catalog import draft schema"
```

---

## Task 2: Canonical Upload Domain

**Files:**
- Create: `app/backend/catalog_import.py`
- Test: `tests/test_catalog_import.py`

- [ ] **Step 1: Write failing upload tests**

Append to `tests/test_catalog_import.py`:

```python
import tempfile

from catalog_import import UploadedImage, create_import_batch, get_import_batch  # noqa: E402


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportUploadTests
```

Expected: import error for missing `catalog_import`.

- [ ] **Step 3: Implement upload helpers**

Create `app/backend/catalog_import.py`:

```python
from __future__ import annotations

import hashlib
import mimetypes
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from db import RAW_IMAGES_DIR, row_to_dict

ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


@dataclass(frozen=True)
class UploadedImage:
    filename: str
    content: bytes
    content_type: str


def create_import_batch(
    conn: sqlite3.Connection,
    files: list[UploadedImage],
    raw_images_dir: Path = RAW_IMAGES_DIR,
) -> dict[str, Any]:
    if not files:
        raise ValueError("At least one image is required.")
    if len(files) > 100:
        raise ValueError("Upload at most 100 images at a time.")
    raw_images_dir.mkdir(parents=True, exist_ok=True)
    cur = conn.execute(
        """
        INSERT INTO import_batches
          (status, original_file_count, uploaded_file_count, processed_file_count, published_item_count)
        VALUES ('uploaded', ?, 0, 0, 0)
        """,
        (len(files),),
    )
    batch_id = int(cur.lastrowid)
    uploaded_count = 0
    for file_index, uploaded in enumerate(files, start=1):
        validate_uploaded_image(uploaded)
        digest = hashlib.sha256(uploaded.content).hexdigest()
        canonical_filename = canonical_image_filename(uploaded.filename, digest, file_index)
        path = unique_path(raw_images_dir / canonical_filename)
        path.write_bytes(uploaded.content)
        conn.execute(
            """
            INSERT INTO import_images
              (batch_id, original_filename, canonical_filename, canonical_path, content_hash, status)
            VALUES (?, ?, ?, ?, ?, 'uploaded')
            """,
            (batch_id, uploaded.filename, path.name, str(path), digest),
        )
        uploaded_count += 1
    conn.execute(
        """
        UPDATE import_batches
        SET uploaded_file_count = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (uploaded_count, batch_id),
    )
    conn.commit()
    return get_import_batch(conn, batch_id)


def validate_uploaded_image(uploaded: UploadedImage) -> None:
    suffix = Path(uploaded.filename).suffix.lower()
    guessed_type = mimetypes.guess_type(uploaded.filename)[0] or ""
    content_type = (uploaded.content_type or guessed_type).split(";", 1)[0].lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS or content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise ValueError(f"Unsupported image type: {uploaded.filename}")


def canonical_image_filename(original_filename: str, digest: str, index: int) -> str:
    original_path = Path(original_filename)
    suffix = original_path.suffix.lower() or ".jpg"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", original_path.stem).strip("._-") or "image"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"upload_{timestamp}_{index:03d}_{digest[:10]}_{stem}{suffix}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def list_import_images(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    return [
        row_to_dict(row)
        for row in conn.execute(
            "SELECT * FROM import_images WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        )
    ]


def get_import_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None:
        return None
    batch = row_to_dict(row)
    batch["images"] = list_import_images(conn, batch_id)
    batch["draft_items"] = []
    batch["observations"] = []
    return batch
```

- [ ] **Step 4: Run upload tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportUploadTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/catalog_import.py tests/test_catalog_import.py
git commit -m "Add canonical image import batches"
```

---

## Task 3: Draft Processing With Injectable Provider

**Files:**
- Modify: `app/backend/catalog_import.py`
- Test: `tests/test_catalog_import.py`

- [ ] **Step 1: Write failing processing test**

Append to `tests/test_catalog_import.py`:

```python
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
                    "color_secondary": "—",
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
```

Add this import near the existing `catalog_import` import:

```python
from catalog_import import process_import_batch  # noqa: E402
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportProcessingTests.test_process_import_batch_creates_reviewable_draft
```

Expected: import error or attribute error for `process_import_batch`.

- [ ] **Step 3: Implement draft processing**

In `app/backend/catalog_import.py`, add imports:

```python
import json
from typing import Protocol

from db import EDITABLE_ITEM_FIELDS, INTEGER_ITEM_FIELDS, list_items_for_prompt, normalize_item_updates
```

Add the provider protocol:

```python
class CatalogDraftProvider(Protocol):
    def generate_drafts(self, images: list[dict[str, Any]], published_items: list[dict[str, Any]]) -> dict[str, Any]:
        ...
```

Add draft helpers:

```python
DRAFT_UPDATE_FIELDS = set(EDITABLE_ITEM_FIELDS) | {
    "status",
    "generation_notes",
    "validation_warnings_json",
    "image_reference",
    "proposed_item_id",
}


def process_import_batch(
    conn: sqlite3.Connection,
    batch_id: int,
    provider: CatalogDraftProvider,
    limit: int = 10,
) -> dict[str, Any]:
    batch = get_import_batch(conn, batch_id)
    if batch is None:
        raise ValueError("Import batch not found.")
    images = [
        row_to_dict(row)
        for row in conn.execute(
            """
            SELECT * FROM import_images
            WHERE batch_id = ? AND status IN ('uploaded', 'failed')
            ORDER BY id
            LIMIT ?
            """,
            (batch_id, limit),
        )
    ]
    if not images:
        return refresh_import_batch_status(conn, batch_id)
    image_ids = [image["id"] for image in images]
    conn.executemany(
        "UPDATE import_images SET status = 'processing', error_message = '' WHERE id = ?",
        [(image_id,) for image_id in image_ids],
    )
    conn.execute(
        "UPDATE import_batches SET status = 'processing', error_message = '', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (batch_id,),
    )
    conn.commit()
    payload = provider.generate_drafts(images, list_items_for_prompt(conn))
    create_draft_records(conn, batch_id, images, payload)
    return refresh_import_batch_status(conn, batch_id)


def create_draft_records(
    conn: sqlite3.Connection,
    batch_id: int,
    images: list[dict[str, Any]],
    payload: dict[str, Any],
) -> None:
    image_by_id = {image["id"]: image for image in images}
    draft_ids_by_index: dict[int, int] = {}
    for index, draft in enumerate(payload.get("draft_items", [])):
        source_ids = [int(value) for value in draft.get("source_image_ids", []) if int(value) in image_by_id]
        if not source_ids:
            continue
        normalized = normalize_draft_item(draft)
        columns = ["batch_id", "status", *normalized.keys(), "raw_model_json"]
        values = [batch_id, "needs_review", *normalized.values(), json.dumps(draft, ensure_ascii=False)]
        cur = conn.execute(
            f"INSERT INTO draft_items ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            values,
        )
        draft_id = int(cur.lastrowid)
        draft_ids_by_index[index] = draft_id
        representative_source_id = int(draft.get("representative_source_image_id") or source_ids[0])
        for source_id in source_ids:
            conn.execute(
                """
                INSERT INTO draft_item_images (draft_item_id, import_image_id, image_reference, is_representative)
                VALUES (?, ?, ?, ?)
                """,
                (draft_id, source_id, draft.get("image_reference", ""), 1 if source_id == representative_source_id else 0),
            )
            conn.execute(
                "UPDATE import_images SET status = 'processed', draft_item_id = ?, error_message = '' WHERE id = ?",
                (draft_id, source_id),
            )
    for observation in payload.get("observations", []):
        draft_index = int(observation.get("draft_index", -1))
        conn.execute(
            """
            INSERT INTO draft_observations
              (batch_id, draft_item_id, category, observation_type, detail, action_needed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                draft_ids_by_index.get(draft_index),
                str(observation.get("category") or ""),
                str(observation.get("observation_type") or ""),
                str(observation.get("detail") or ""),
                str(observation.get("action_needed") or ""),
            ),
        )
    conn.commit()


def normalize_draft_item(draft: dict[str, Any]) -> dict[str, Any]:
    allowed = {field: draft.get(field, "") for field in EDITABLE_ITEM_FIELDS if field in draft}
    normalized = normalize_item_updates(allowed)
    for field in EDITABLE_ITEM_FIELDS:
        normalized.setdefault(field, None if field in INTEGER_ITEM_FIELDS else "")
    normalized["proposed_item_id"] = str(draft.get("proposed_item_id") or "")
    normalized["image_reference"] = str(draft.get("image_reference") or "")
    normalized["generation_notes"] = str(draft.get("generation_notes") or "")
    normalized["validation_warnings_json"] = json.dumps(draft.get("validation_warnings", []), ensure_ascii=False)
    return normalized
```

Add list helpers:

```python
def draft_item_images(conn: sqlite3.Connection, draft_item_id: int) -> list[dict[str, Any]]:
    return [
        row_to_dict(row)
        for row in conn.execute(
            """
            SELECT import_images.*, draft_item_images.image_reference, draft_item_images.is_representative
            FROM draft_item_images
            JOIN import_images ON import_images.id = draft_item_images.import_image_id
            WHERE draft_item_images.draft_item_id = ?
            ORDER BY draft_item_images.is_representative DESC, import_images.id
            """,
            (draft_item_id,),
        )
    ]


def draft_item_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    draft = row_to_dict(row)
    draft["images"] = draft_item_images(conn, draft["id"])
    draft["representative_image"] = draft["images"][0] if draft["images"] else None
    draft["validation_warnings"] = json.loads(draft.get("validation_warnings_json") or "[]")
    return draft


def list_draft_items(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    return [
        draft_item_to_dict(conn, row)
        for row in conn.execute(
            "SELECT * FROM draft_items WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        )
    ]


def list_draft_observations(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    return [
        row_to_dict(row)
        for row in conn.execute(
            "SELECT * FROM draft_observations WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        )
    ]


def attach_import_batch_children(conn: sqlite3.Connection, batch: dict[str, Any]) -> dict[str, Any]:
    batch["images"] = list_import_images(conn, batch["id"])
    batch["draft_items"] = list_draft_items(conn, batch["id"])
    batch["observations"] = list_draft_observations(conn, batch["id"])
    return batch


def refresh_import_batch_status(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any]:
    counts = conn.execute(
        """
        SELECT
          SUM(CASE WHEN status IN ('processed', 'published', 'rejected') THEN 1 ELSE 0 END) AS processed,
          SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) AS published,
          SUM(CASE WHEN status IN ('uploaded', 'failed') THEN 1 ELSE 0 END) AS remaining,
          SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
        FROM import_images
        WHERE batch_id = ?
        """,
        (batch_id,),
    ).fetchone()
    published_items = conn.execute(
        "SELECT COUNT(*) AS count FROM draft_items WHERE batch_id = ? AND status = 'published'",
        (batch_id,),
    ).fetchone()["count"]
    remaining = int(counts["remaining"] or 0)
    failed = int(counts["failed"] or 0)
    if failed and remaining == failed:
        status = "failed"
    elif remaining:
        status = "needs_review" if int(counts["processed"] or 0) else "uploaded"
    elif published_items:
        total_drafts = conn.execute(
            "SELECT COUNT(*) AS count FROM draft_items WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()["count"]
        status = "published" if published_items == total_drafts else "partially_published"
    else:
        status = "needs_review"
    conn.execute(
        """
        UPDATE import_batches
        SET status = ?, processed_file_count = ?, published_item_count = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, int(counts["processed"] or 0), int(counts["published"] or 0), batch_id),
    )
    conn.commit()
    batch = get_import_batch(conn, batch_id)
    return attach_import_batch_children(conn, batch)
```

Also update `get_import_batch` after `attach_import_batch_children` exists:

```python
def get_import_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None:
        return None
    return attach_import_batch_children(conn, row_to_dict(row))
```

- [ ] **Step 4: Run processing test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportProcessingTests.test_process_import_batch_creates_reviewable_draft
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/catalog_import.py tests/test_catalog_import.py
git commit -m "Add import draft processing"
```

---

## Task 4: Draft Update, Publish, And Reject

**Files:**
- Modify: `app/backend/catalog_import.py`
- Test: `tests/test_catalog_import.py`

- [ ] **Step 1: Write failing review and publish tests**

Append to `CatalogImportProcessingTests` in `tests/test_catalog_import.py`:

```python
    def create_processed_batch(self):
        batch = create_import_batch(
            self.conn,
            [UploadedImage("shirt.jpeg", b"shirt bytes", "image/jpeg")],
            raw_images_dir=self.raw_dir,
        )
        return process_import_batch(self.conn, batch["id"], FakeCatalogProvider(), limit=10)

    def test_update_draft_item_reuses_catalog_validation(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]

        updated = update_draft_item(
            self.conn,
            draft_id,
            {"brand": "Muji", "formality": "4", "generation_notes": "Reviewed against image."},
        )

        self.assertEqual(updated["brand"], "Muji")
        self.assertEqual(updated["formality"], 4)
        self.assertEqual(updated["generation_notes"], "Reviewed against image.")

    def test_publish_draft_item_creates_live_catalog_item(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]

        published = publish_draft_item(self.conn, draft_id)

        self.assertEqual(published["item_id"], "TOP-01")
        self.assertEqual(published["category"], "Shirt")
        self.assertEqual(published["representative_image"]["filename"].endswith("shirt.jpeg"), True)
        catalog_ids = [item["item_id"] for item in list_catalog_items(self.conn, "all")]
        self.assertEqual(catalog_ids, ["TOP-01"])

    def test_reject_draft_item_keeps_it_out_of_live_catalog(self):
        processed = self.create_processed_batch()
        draft_id = processed["draft_items"][0]["id"]

        rejected = reject_draft_item(self.conn, draft_id)

        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(list_catalog_items(self.conn, "all"), [])
```

Add imports:

```python
from catalog_import import publish_draft_item, reject_draft_item, update_draft_item  # noqa: E402
from db import list_catalog_items  # noqa: E402
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportProcessingTests
```

Expected: import error or attribute error for the new functions.

- [ ] **Step 3: Implement draft update, publish, reject**

In `app/backend/catalog_import.py`, add:

```python
def get_draft_item(conn: sqlite3.Connection, draft_item_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM draft_items WHERE id = ?", (draft_item_id,)).fetchone()
    return draft_item_to_dict(conn, row) if row else None


def update_draft_item(conn: sqlite3.Connection, draft_item_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
    if get_draft_item(conn, draft_item_id) is None:
        return None
    updates: dict[str, Any] = {}
    catalog_changes = {key: value for key, value in changes.items() if key in EDITABLE_ITEM_FIELDS}
    updates.update(normalize_item_updates(catalog_changes))
    for field in ["generation_notes", "image_reference", "proposed_item_id"]:
        if field in changes:
            updates[field] = "" if changes[field] is None else str(changes[field]).strip()
    if "validation_warnings_json" in changes:
        json.loads(changes["validation_warnings_json"] or "[]")
        updates["validation_warnings_json"] = changes["validation_warnings_json"] or "[]"
    if "status" in changes:
        status = str(changes["status"])
        if status not in {"generated", "needs_review", "published", "rejected"}:
            raise ValueError("Invalid draft status.")
        updates["status"] = status
    unknown = set(changes) - DRAFT_UPDATE_FIELDS
    if unknown:
        raise ValueError(f"Unknown draft field: {sorted(unknown)[0]}")
    if updates:
        assignments = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(
            f"UPDATE draft_items SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [*updates.values(), draft_item_id],
        )
        conn.commit()
    return get_draft_item(conn, draft_item_id)


def publish_draft_item(conn: sqlite3.Connection, draft_item_id: int) -> dict[str, Any] | None:
    draft = get_draft_item(conn, draft_item_id)
    if draft is None:
        return None
    if draft["status"] == "published" and draft["published_item_id"]:
        from db import get_catalog_item
        return get_catalog_item(conn, draft["published_item_id"])
    item_id = next_item_id(conn, prefix_for_draft(draft))
    item = {field: draft.get(field) for field in EDITABLE_ITEM_FIELDS}
    item["item_id"] = item_id
    item["raw_json"] = json.dumps({"draft_item_id": draft_item_id}, ensure_ascii=False)
    columns = ["item_id", *EDITABLE_ITEM_FIELDS, "raw_json"]
    conn.execute(
        f"INSERT INTO items ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [item.get(column, "") for column in columns],
    )
    for image in draft["images"]:
        conn.execute(
            """
            INSERT INTO item_images (item_id, filename, path, image_reference, is_representative)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item_id,
                image["canonical_filename"],
                image["canonical_path"],
                image.get("image_reference") or draft.get("image_reference") or "",
                int(image.get("is_representative") or 0),
            ),
        )
        conn.execute("UPDATE import_images SET status = 'published' WHERE id = ?", (image["id"],))
    conn.execute(
        """
        UPDATE draft_items
        SET status = 'published', published_item_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (item_id, draft_item_id),
    )
    conn.commit()
    refresh_import_batch_status(conn, draft["batch_id"])
    from db import get_catalog_item
    return get_catalog_item(conn, item_id)


def reject_draft_item(conn: sqlite3.Connection, draft_item_id: int) -> dict[str, Any] | None:
    draft = get_draft_item(conn, draft_item_id)
    if draft is None:
        return None
    conn.execute(
        "UPDATE draft_items SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (draft_item_id,),
    )
    conn.execute(
        """
        UPDATE import_images
        SET status = 'rejected'
        WHERE id IN (SELECT import_image_id FROM draft_item_images WHERE draft_item_id = ?)
        """,
        (draft_item_id,),
    )
    conn.commit()
    refresh_import_batch_status(conn, draft["batch_id"])
    return get_draft_item(conn, draft_item_id)


def prefix_for_draft(draft: dict[str, Any]) -> str:
    proposed = (draft.get("proposed_item_id") or "").upper()
    category = (draft.get("category") or "").lower()
    if proposed.startswith("TOP") or any(term in category for term in ["shirt", "t-shirt", "jacket", "sweater"]):
        return "TOP"
    if proposed.startswith("BOT") or any(term in category for term in ["trouser", "jeans", "shorts", "bottom"]):
        return "BOT"
    if proposed.startswith("SHOE") or "shoe" in category:
        return "SHOE"
    return "ACC"


def next_item_id(conn: sqlite3.Connection, prefix: str) -> str:
    rows = conn.execute(
        "SELECT item_id FROM items WHERE item_id LIKE ?",
        (f"{prefix}-%",),
    ).fetchall()
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for row in rows:
        match = pattern.match(row["item_id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:02d}"
```

- [ ] **Step 4: Run review and publish tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportProcessingTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/catalog_import.py tests/test_catalog_import.py
git commit -m "Add draft review publishing"
```

---

## Task 5: Catalog AI Provider

**Files:**
- Modify: `app/backend/llm.py`
- Modify: `app/backend/catalog_import.py`
- Test: `tests/test_catalog_import.py`

- [ ] **Step 1: Write failing AI request-shape test**

Append to `tests/test_catalog_import.py`:

```python
from llm import build_catalog_request_body  # noqa: E402


class CatalogImportAITests(unittest.TestCase):
    def test_build_catalog_request_body_includes_image_data_urls_and_schema(self):
        body = build_catalog_request_body(
            model="gpt-test",
            images=[
                {
                    "id": 7,
                    "canonical_filename": "shirt.jpeg",
                    "canonical_path": "/tmp/shirt.jpeg",
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportAITests
```

Expected: import error for `build_catalog_request_body`.

- [ ] **Step 3: Add catalog generation request helpers**

In `app/backend/llm.py`, add imports:

```python
import base64
from pathlib import Path
```

Add a catalog schema constant and request builder:

```python
CATALOG_DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["draft_items", "observations"],
    "properties": {
        "draft_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": ["source_image_ids", "category", "sub_category", "brand", "color_primary", "pattern"],
                "properties": {
                    "source_image_ids": {"type": "array", "items": {"type": "integer"}},
                    "representative_source_image_id": {"type": "integer"},
                    "proposed_item_id": {"type": "string"},
                    "category": {"type": "string"},
                    "sub_category": {"type": "string"},
                    "brand": {"type": "string"},
                    "color_primary": {"type": "string"},
                    "color_secondary": {"type": "string"},
                    "pattern": {"type": "string"},
                    "image_reference": {"type": "string"},
                    "generation_notes": {"type": "string"},
                    "validation_warnings": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["draft_index", "category", "observation_type", "detail", "action_needed"],
                "properties": {
                    "draft_index": {"type": "integer"},
                    "category": {"type": "string"},
                    "observation_type": {"type": "string"},
                    "detail": {"type": "string"},
                    "action_needed": {"type": "string"},
                },
            },
        },
    },
}


CATALOG_SYSTEM_PROMPT = """
You catalog Varun's wardrobe images into reviewable draft metadata.
Follow the wardrobe cataloging rules: worn photos override flat lays, do not guess brands,
use precise color names, flag warm-skin caution cases, do not inflate versatility,
and flag uncertain duplicates rather than silently merging them.
Return draft metadata for the catalog fields visible in the input images.
"""


def build_catalog_request_body(
    model: str,
    images: list[dict[str, Any]],
    published_items: list[dict[str, Any]],
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                f"{CATALOG_SYSTEM_PROMPT}\n\n"
                f"PUBLISHED_CATALOG_JSON:\n{json.dumps(published_items, ensure_ascii=False)}\n\n"
                f"IMPORT_IMAGES_JSON:\n{json.dumps(strip_image_bytes(images), ensure_ascii=False)}"
            ),
        }
    ]
    for image in images:
        content.append({"type": "input_image", "image_url": image["data_url"]})
    return {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "wardrobe_catalog_drafts",
                "strict": False,
                "schema": CATALOG_DRAFT_SCHEMA,
            }
        },
    }


def strip_image_bytes(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": image["id"],
            "canonical_filename": image["canonical_filename"],
            "original_filename": image.get("original_filename", ""),
            "status": image.get("status", ""),
        }
        for image in images
    ]


def image_data_url(path: Path, mime_type: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
```

Add a provider class:

```python
class OpenAICatalogProvider:
    def __init__(self) -> None:
        load_dotenv()
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.model = normalize_openai_model(os.environ.get("OPENAI_MODEL", ""))
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is not configured.")
        if not self.model:
            raise LLMError("OPENAI_MODEL is not configured.")

    def generate_drafts(self, images: list[dict[str, Any]], published_items: list[dict[str, Any]]) -> dict[str, Any]:
        hydrated_images = []
        for image in images:
            path = Path(image["canonical_path"])
            mime_type = image.get("content_type") or "image/jpeg"
            hydrated = dict(image)
            hydrated["data_url"] = image_data_url(path, mime_type)
            hydrated_images.append(hydrated)
        body = build_catalog_request_body(self.model, hydrated_images, published_items)
        request = urllib.request.Request(
            OPENAI_RESPONSES_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"OpenAI catalog request failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"OpenAI catalog request failed: {exc.reason}") from exc
        text = extract_response_text(payload)
        if not text:
            raise LLMError("OpenAI catalog response did not include structured text output.")
        return json.loads(text)
```

In `app/backend/catalog_import.py`, import `OpenAICatalogProvider` only where needed in server task, not inside the domain tests.

- [ ] **Step 4: Run AI test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportAITests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/llm.py tests/test_catalog_import.py
git commit -m "Add catalog image generation provider"
```

---

## Task 6: Import API Routes

**Files:**
- Modify: `app/backend/server.py`
- Test: `tests/test_catalog_import.py`

- [ ] **Step 1: Write failing multipart parser test**

Append to `tests/test_catalog_import.py`:

```python
from server import parse_multipart_images  # noqa: E402


class CatalogImportServerTests(unittest.TestCase):
    def test_parse_multipart_images_extracts_uploads(self):
        boundary = "----wardrobe-test"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="shirt.jpeg"\r\n'
            "Content-Type: image/jpeg\r\n\r\n"
            "image-bytes\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        uploads = parse_multipart_images(
            f"multipart/form-data; boundary={boundary}",
            body,
        )

        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0].filename, "shirt.jpeg")
        self.assertEqual(uploads[0].content, b"image-bytes")
        self.assertEqual(uploads[0].content_type, "image/jpeg")
```

- [ ] **Step 2: Run parser test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportServerTests
```

Expected: import error for `parse_multipart_images`.

- [ ] **Step 3: Add multipart parser and route handlers**

In `app/backend/server.py`, add imports:

```python
import email
from io import BytesIO

from catalog_import import (
    UploadedImage,
    create_import_batch,
    get_import_batch,
    list_import_batches,
    process_import_batch,
    publish_draft_item,
    reject_draft_item,
    update_draft_item,
)
from llm import OpenAICatalogProvider
```

Add this helper near the bottom:

```python
def parse_multipart_images(content_type: str, body: bytes) -> list[UploadedImage]:
    if "multipart/form-data" not in content_type:
        raise ValueError("Content-Type must be multipart/form-data.")
    header_blob = (
        f"Content-Type: {content_type}\r\n"
        f"MIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8")
    message = email.message_from_binary_file(BytesIO(header_blob + body))
    uploads: list[UploadedImage] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        uploads.append(UploadedImage(filename, payload, part.get_content_type()))
    return uploads
```

In `ApiHandler.do_GET`, before conversations routes:

```python
            elif path == "/api/import-batches":
                with connect() as conn:
                    apply_schema(conn)
                    self.json_response({"batches": list_import_batches(conn)})
            elif path.startswith("/api/import-batches/"):
                batch_id = int(path.rsplit("/", 1)[1])
                with connect() as conn:
                    apply_schema(conn)
                    batch = get_import_batch(conn, batch_id)
                if batch is None:
                    self.error_response(404, "Import batch not found")
                else:
                    self.json_response({"batch": batch})
```

Add `list_import_batches` to `catalog_import.py`:

```python
def list_import_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        get_import_batch(conn, row["id"])
        for row in conn.execute("SELECT id FROM import_batches ORDER BY updated_at DESC, id DESC")
    ]
```

Adjust `do_POST` so multipart upload is handled before JSON reading:

```python
            path = urlparse(self.path).path
            if path == "/api/import-batches":
                self.create_import_batch_route()
                return
            if path.startswith("/api/import-batches/") and path.endswith("/process"):
                batch_id = int(path.split("/")[3])
                body = self.read_json()
                limit = int(body.get("limit") or 10)
                with connect() as conn:
                    apply_schema(conn)
                    batch = process_import_batch(conn, batch_id, OpenAICatalogProvider(), limit=limit)
                self.json_response({"batch": batch})
                return
            if path.startswith("/api/draft-items/") and path.endswith("/publish"):
                draft_id = int(path.split("/")[3])
                with connect() as conn:
                    apply_schema(conn)
                    item = publish_draft_item(conn, draft_id)
                if item is None:
                    self.error_response(404, "Draft item not found")
                else:
                    self.json_response({"item": item})
                return
            if path.startswith("/api/draft-items/") and path.endswith("/reject"):
                draft_id = int(path.split("/")[3])
                with connect() as conn:
                    apply_schema(conn)
                    draft = reject_draft_item(conn, draft_id)
                if draft is None:
                    self.error_response(404, "Draft item not found")
                else:
                    self.json_response({"draft_item": draft})
                return
            body = self.read_json()
```

Add route method:

```python
    def create_import_batch_route(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length)
        uploads = parse_multipart_images(self.headers.get("Content-Type", ""), body)
        with connect() as conn:
            apply_schema(conn)
            batch = create_import_batch(conn, uploads)
        self.json_response({"batch": batch}, 201)
```

In `do_PATCH`, before live item route:

```python
            if path.startswith("/api/draft-items/"):
                draft_id = int(path.rsplit("/", 1)[1])
                body = self.read_json()
                with connect() as conn:
                    apply_schema(conn)
                    draft = update_draft_item(conn, draft_id, body)
                if draft is None:
                    self.error_response(404, "Draft item not found")
                else:
                    self.json_response({"draft_item": draft})
                return
```

Catch `ValueError` in `do_GET`, `do_POST`, and `do_PATCH` the same way as `CatalogValidationError`:

```python
        except (CatalogValidationError, ValueError) as exc:
            self.error_response(400, str(exc))
```

- [ ] **Step 4: Run server parser test and full backend tests**

Run:

```bash
python3 -m unittest tests.test_catalog_import tests.test_catalog_items
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/server.py app/backend/catalog_import.py tests/test_catalog_import.py
git commit -m "Add catalog import API routes"
```

---

## Task 7: Frontend API And Import Route

**Files:**
- Modify: `app/frontend/src/api.js`
- Modify: `app/frontend/src/App.jsx`
- Modify: `app/frontend/src/styles.css`

- [ ] **Step 1: Add frontend API methods**

In `app/frontend/src/api.js`, add a request helper that does not force JSON headers for multipart:

```javascript
async function rawRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}
```

Add methods to `api`:

```javascript
  uploadImportBatch: (files) => {
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    return rawRequest("/api/import-batches", {
      method: "POST",
      body: form,
    });
  },
  listImportBatches: () => request("/api/import-batches"),
  getImportBatch: (batchId) => request(`/api/import-batches/${encodeURIComponent(batchId)}`),
  processImportBatch: (batchId, limit = 10) =>
    request(`/api/import-batches/${encodeURIComponent(batchId)}/process`, {
      method: "POST",
      body: JSON.stringify({ limit }),
    }),
  updateDraftItem: (draftItemId, changes) =>
    request(`/api/draft-items/${encodeURIComponent(draftItemId)}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  publishDraftItem: (draftItemId) =>
    request(`/api/draft-items/${encodeURIComponent(draftItemId)}/publish`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  rejectDraftItem: (draftItemId) =>
    request(`/api/draft-items/${encodeURIComponent(draftItemId)}/reject`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
```

- [ ] **Step 2: Add route and navigation**

In `app/frontend/src/App.jsx`, add imports:

```javascript
  Upload,
  Play,
  Check,
  Ban,
```

Update the API import line:

```javascript
import { API_BASE, api, imageUrl } from "./api";
```

Change routes:

```javascript
const routes = ["/chat", "/catalog", "/catalog/import"];
```

Update `cleanRoute` to keep the import route:

```javascript
function cleanRoute(pathname) {
  return routes.includes(pathname) ? pathname : "/chat";
}
```

Add Import buttons to `Sidebar`, `MobileNav`, and catalog topbar using `Upload`.

In the main render, route import separately:

```jsx
      {route === "/catalog/import" ? (
        <CatalogImportPage status={status} setStatus={setStatus} navigate={navigate} onPreviewImage={setPreviewImage} />
      ) : route === "/catalog" ? (
        <CatalogPage status={status} setStatus={setStatus} navigate={navigate} onPreviewImage={setPreviewImage} />
      ) : (
```

- [ ] **Step 3: Add import page components**

Add this component below `CatalogPage`:

```jsx
function CatalogImportPage({ status, setStatus, navigate, onPreviewImage }) {
  const [batches, setBatches] = useState([]);
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    loadBatches();
  }, []);

  async function loadBatches() {
    setStatus("");
    try {
      const data = await api.listImportBatches();
      setBatches(data.batches);
      if (!selectedBatch && data.batches[0]) setSelectedBatch(data.batches[0]);
    } catch (error) {
      setStatus(error.message);
    }
  }

  async function uploadFiles(event) {
    event.preventDefault();
    if (!files.length || uploading) return;
    setUploading(true);
    setStatus("");
    try {
      const data = await api.uploadImportBatch(files);
      setSelectedBatch(data.batch);
      setFiles([]);
      await loadBatches();
      setStatus(`${data.batch.uploaded_file_count} images uploaded.`);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setUploading(false);
    }
  }

  async function processNext() {
    if (!selectedBatch || processing) return;
    setProcessing(true);
    setStatus("");
    try {
      const data = await api.processImportBatch(selectedBatch.id, 10);
      setSelectedBatch(data.batch);
      await loadBatches();
      setStatus(`Processed ${data.batch.processed_file_count} images.`);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setProcessing(false);
    }
  }

  function replaceDraft(nextDraft) {
    setSelectedBatch((current) => ({
      ...current,
      draft_items: current.draft_items.map((draft) => (draft.id === nextDraft.id ? nextDraft : draft)),
    }));
  }

  async function publishDraft(draftId) {
    const data = await api.publishDraftItem(draftId);
    setStatus(`${data.item.item_id} published.`);
    const refreshed = await api.getImportBatch(selectedBatch.id);
    setSelectedBatch(refreshed.batch);
    await loadBatches();
  }

  async function rejectDraft(draftId) {
    const data = await api.rejectDraftItem(draftId);
    replaceDraft(data.draft_item);
    setStatus("Draft rejected.");
    await loadBatches();
  }

  return (
    <main className="catalog-panel">
      <header className="topbar catalog-topbar">
        <div>
          <p className="eyebrow">Catalog import</p>
          <h2>Upload images, process drafts, then publish reviewed items.</h2>
        </div>
        <div className="topbar-actions">
          <MobileNav route="/catalog/import" navigate={navigate} />
          <button className="icon-text" onClick={() => navigate("/catalog")}>
            <List size={17} />
            Catalog
          </button>
        </div>
      </header>

      <section className="catalog-content import-layout">
        <form className="import-upload" onSubmit={uploadFiles}>
          <label className="field wide">
            <span>Images</span>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
              multiple
              onChange={(event) => setFiles(Array.from(event.target.files || []))}
            />
          </label>
          <button className="tool-button primary" disabled={!files.length || uploading}>
            {uploading ? <Loader2 className="spin" size={17} /> : <Upload size={17} />}
            Upload
          </button>
          <p className="muted">{files.length ? `${files.length} selected` : "No files selected"}</p>
        </form>

        {status && <div className="status-line catalog-status">{status}</div>}

        <div className="import-grid">
          <BatchList batches={batches} selectedBatch={selectedBatch} setSelectedBatch={setSelectedBatch} />
          <BatchReview
            batch={selectedBatch}
            processing={processing}
            processNext={processNext}
            replaceDraft={replaceDraft}
            publishDraft={publishDraft}
            rejectDraft={rejectDraft}
            onPreviewImage={onPreviewImage}
          />
        </div>
      </section>
    </main>
  );
}
```

Add batch and draft components:

```jsx
function BatchList({ batches, selectedBatch, setSelectedBatch }) {
  return (
    <aside className="batch-list">
      <h3>Import batches</h3>
      {batches.length === 0 && <p className="muted">No import batches yet.</p>}
      {batches.map((batch) => (
        <button
          key={batch.id}
          className={selectedBatch?.id === batch.id ? "batch-row active" : "batch-row"}
          onClick={() => setSelectedBatch(batch)}
        >
          <strong>Batch {batch.id}</strong>
          <span>{batch.status}</span>
          <small>{batch.processed_file_count}/{batch.uploaded_file_count} processed</small>
        </button>
      ))}
    </aside>
  );
}

function BatchReview({ batch, processing, processNext, replaceDraft, publishDraft, rejectDraft, onPreviewImage }) {
  if (!batch) return <section className="draft-review"><p className="muted">Upload images to start an import batch.</p></section>;
  return (
    <section className="draft-review">
      <header className="draft-review-header">
        <div>
          <h3>Batch {batch.id}</h3>
          <p className="muted">{batch.uploaded_file_count} uploaded, {batch.processed_file_count} processed, {batch.published_item_count} published</p>
        </div>
        <button className="tool-button primary" onClick={processNext} disabled={processing}>
          {processing ? <Loader2 className="spin" size={17} /> : <Play size={17} />}
          Process next 10
        </button>
      </header>
      <div className="draft-list">
        {batch.draft_items?.length ? (
          batch.draft_items.map((draft) => (
            <DraftItemCard
              key={draft.id}
              draft={draft}
              replaceDraft={replaceDraft}
              publishDraft={publishDraft}
              rejectDraft={rejectDraft}
              onPreviewImage={onPreviewImage}
            />
          ))
        ) : (
          <p className="muted">No drafts generated yet.</p>
        )}
      </div>
    </section>
  );
}
```

Add a draft editor that reuses existing field groups:

```jsx
function DraftItemCard({ draft, replaceDraft, publishDraft, rejectDraft, onPreviewImage }) {
  const [form, setForm] = useState(() => draftFormFromItem(draft));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setForm(draftFormFromItem(draft));
  }, [draft]);

  function setField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function saveDraft(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const data = await api.updateDraftItem(draft.id, form);
      replaceDraft(data.draft_item);
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className={`draft-card ${draft.status}`}>
      <header className="draft-card-header">
        <div className="item-id-cell">
          {draft.representative_image && (
            <ImportImageThumb image={draft.representative_image} alt={`Draft ${draft.id}`} onPreviewImage={onPreviewImage} />
          )}
          <div>
            <strong>Draft {draft.id}</strong>
            <small>{draft.color_primary} {draft.sub_category}</small>
          </div>
        </div>
        <span className="type-pill">{draft.status}</span>
      </header>
      {draft.validation_warnings?.length > 0 && (
        <div className="warning-list">
          {draft.validation_warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}
      <div className="editor-images">
        {draft.images?.map((image) => (
          <figure key={image.id}>
            <ImportImageThumb image={image} alt={image.canonical_filename} onPreviewImage={onPreviewImage} />
            <figcaption>{image.image_reference || image.canonical_filename}</figcaption>
          </figure>
        ))}
      </div>
      <form className="editor-form compact" onSubmit={saveDraft}>
        {fieldGroups.map((group) => (
          <fieldset key={group.title}>
            <legend>{group.title}</legend>
            <div className="field-grid">
              {group.fields.map((field) => (
                <label key={field} className={longFields.has(field) ? "field wide" : "field"}>
                  <span>{fieldLabel(field)}</span>
                  {longFields.has(field) ? (
                    <textarea value={form[field]} onChange={(event) => setField(field, event.target.value)} rows={3} />
                  ) : (
                    <input
                      type={numberFields.has(field) ? "number" : "text"}
                      value={form[field]}
                      onChange={(event) => setField(field, event.target.value)}
                      min={numberFields.has(field) ? 1 : undefined}
                      max={numberFields.has(field) ? 5 : undefined}
                    />
                  )}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        {error && <div className="error-line">{error}</div>}
        <footer className="editor-actions">
          <button className="icon-text" type="submit" disabled={saving || draft.status === "published"}>
            {saving ? <Loader2 className="spin" size={17} /> : <Save size={17} />}
            Save Draft
          </button>
          <button className="tool-button primary" type="button" onClick={() => publishDraft(draft.id)} disabled={draft.status === "published"}>
            <Check size={17} />
            Publish
          </button>
          <button className="icon-text" type="button" onClick={() => rejectDraft(draft.id)} disabled={draft.status === "published"}>
            <Ban size={17} />
            Reject
          </button>
        </footer>
      </form>
    </article>
  );
}

function draftFormFromItem(draft) {
  const next = {};
  fieldGroups.forEach((group) => {
    group.fields.forEach((field) => {
      next[field] = draft[field] ?? "";
    });
  });
  next.generation_notes = draft.generation_notes || "";
  next.validation_warnings_json = draft.validation_warnings_json || "[]";
  return next;
}

function ImportImageThumb({ image, alt, onPreviewImage }) {
  return (
    <button
      type="button"
      className="image-thumb"
      onClick={() => onPreviewImage({ ...image, filename: image.canonical_filename, path: image.canonical_path, alt })}
      title="Open import image"
    >
      <img src={`${API_BASE}/api/import-images/${image.id}`} alt={alt} />
    </button>
  );
}
```

If `API_BASE` is not exported, export it from `api.js`:

```javascript
export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8765";
```

- [ ] **Step 4: Add import styles**

Append to `app/frontend/src/styles.css`:

```css
.import-layout {
  display: grid;
  gap: 14px;
}

.import-upload {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) auto auto;
  gap: 12px;
  align-items: end;
  border: 1px solid #ded8cf;
  border-radius: 8px;
  background: #fffdfa;
  padding: 14px;
}

.import-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.batch-list,
.draft-review,
.draft-card {
  border: 1px solid #ded8cf;
  border-radius: 8px;
  background: #fffdfa;
}

.batch-list {
  padding: 12px;
  display: grid;
  gap: 8px;
}

.batch-list h3,
.draft-review h3 {
  margin: 0;
  font-size: 16px;
}

.batch-row {
  text-align: left;
  border: 1px solid #d8d0c4;
  background: #fffdfa;
  border-radius: 8px;
  padding: 10px;
  display: grid;
  gap: 4px;
}

.batch-row.active {
  border-color: #61766f;
  background: #f8fbf8;
}

.batch-row span {
  text-transform: capitalize;
  color: #304c43;
}

.draft-review {
  padding: 14px;
  display: grid;
  gap: 14px;
}

.draft-review-header,
.draft-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.draft-list {
  display: grid;
  gap: 14px;
}

.draft-card {
  padding: 14px;
  display: grid;
  gap: 12px;
}

.draft-card.published {
  opacity: 0.72;
}

.warning-list {
  border: 1px solid #e4c36a;
  background: #fff8df;
  border-radius: 8px;
  padding: 8px 10px;
  color: #5d4a11;
}

.warning-list p {
  margin: 0;
  font-size: 13px;
}

.editor-form.compact {
  max-height: none;
}

@media (max-width: 900px) {
  .import-upload,
  .import-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Build frontend**

Run:

```bash
cd app/frontend
npm run build
```

Expected: PASS with Vite build output.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/api.js app/frontend/src/App.jsx app/frontend/src/styles.css
git commit -m "Add catalog import review UI"
```

---

## Task 8: Import Image Streaming

**Files:**
- Modify: `app/backend/catalog_import.py`
- Modify: `app/backend/server.py`
- Test: `tests/test_catalog_import.py`

- [ ] **Step 1: Write failing import image path test**

Append to `CatalogImportUploadTests`:

```python
    def test_import_image_path_by_id_returns_canonical_path(self):
        batch = create_import_batch(
            self.conn,
            [UploadedImage("tee.png", b"png bytes", "image/png")],
            raw_images_dir=self.raw_dir,
        )

        path = import_image_path_by_id(self.conn, batch["images"][0]["id"])

        self.assertEqual(path, Path(batch["images"][0]["canonical_path"]))
```

Add import:

```python
from catalog_import import import_image_path_by_id  # noqa: E402
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_catalog_import.CatalogImportUploadTests.test_import_image_path_by_id_returns_canonical_path
```

Expected: import error for `import_image_path_by_id`.

- [ ] **Step 3: Implement image path helper and route**

In `app/backend/catalog_import.py`, add:

```python
def import_image_path_by_id(conn: sqlite3.Connection, image_id: int) -> Path | None:
    row = conn.execute("SELECT canonical_path FROM import_images WHERE id = ?", (image_id,)).fetchone()
    return Path(row["canonical_path"]) if row else None
```

In `app/backend/server.py`, import it:

```python
from catalog_import import import_image_path_by_id
```

In `do_GET`, before `/api/item-images/`:

```python
            elif path.startswith("/api/import-images/"):
                image_id = int(path.rsplit("/", 1)[1])
                self.stream_import_image(image_id)
```

Add handler method:

```python
    def stream_import_image(self, image_id: int) -> None:
        with connect() as conn:
            apply_schema(conn)
            path = import_image_path_by_id(conn, image_id)
        if path is None or not path.exists():
            self.error_response(404, "Import image not found")
            return
        mime_type, _ = mimetypes.guess_type(str(path))
        data = path.read_bytes()
        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_catalog_import tests.test_catalog_items
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/catalog_import.py app/backend/server.py tests/test_catalog_import.py
git commit -m "Serve imported draft images"
```

---

## Task 9: End-To-End Verification

**Files:**
- Modify: none unless verification finds a defect.

- [ ] **Step 1: Run backend tests**

Run:

```bash
python3 -m unittest tests.test_catalog_import tests.test_catalog_items
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd app/frontend
npm run build
```

Expected: PASS.

- [ ] **Step 3: Start backend**

Run:

```bash
python3 app/backend/server.py
```

Expected: backend prints `Wardrobe stylist backend listening on http://127.0.0.1:8765`.

- [ ] **Step 4: Start frontend**

Run:

```bash
cd app/frontend
npm run dev -- --port 5173
```

Expected: Vite prints a local URL at `http://127.0.0.1:5173/`.

- [ ] **Step 5: Manual browser check**

Open `http://127.0.0.1:5173/catalog/import` and verify:

- The upload panel renders.
- Selecting two local images shows the selected count.
- Upload creates a batch.
- The batch appears in the batch list.
- If `OPENAI_API_KEY` and `OPENAI_MODEL` are configured, `Process next 10` produces drafts.
- Saving a draft keeps the draft visible with updated fields.
- Publishing a draft makes it appear in `/catalog`.
- Rejecting a draft keeps it out of `/catalog`.

- [ ] **Step 6: Final status**

Run:

```bash
git status --short
```

Expected: only intentional source changes are present, or a clean working tree after commits.
