from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from db import (
    EDITABLE_ITEM_FIELDS,
    INTEGER_ITEM_FIELDS,
    RAW_IMAGES_DIR,
    get_catalog_item,
    list_items_for_prompt,
    normalize_item_updates,
    row_to_dict,
)


ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MAX_UPLOAD_COUNT = 100
ITEM_FIELD_ORDER = sorted(EDITABLE_ITEM_FIELDS)
DRAFT_UPDATE_FIELDS = set(EDITABLE_ITEM_FIELDS) | {
    "status",
    "generation_notes",
    "validation_warnings_json",
    "image_reference",
    "proposed_item_id",
}


@dataclass(frozen=True)
class UploadedImage:
    filename: str
    content: bytes
    content_type: str


class CatalogDraftProvider(Protocol):
    def generate_drafts(
        self,
        images: list[dict[str, Any]],
        published_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        pass


def create_import_batch(
    conn: sqlite3.Connection,
    files: list[UploadedImage],
    raw_images_dir: Path = RAW_IMAGES_DIR,
) -> dict[str, Any]:
    if not files:
        raise ValueError("At least one image is required.")
    if len(files) > MAX_UPLOAD_COUNT:
        raise ValueError("Upload at most 100 images at a time.")

    for image in files:
        validate_uploaded_image(image)

    raw_images_dir.mkdir(parents=True, exist_ok=True)
    saved_images = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        batch_cursor = conn.execute(
            """
            INSERT INTO import_batches
              (status, original_file_count, uploaded_file_count)
            VALUES (?, ?, ?)
            """,
            ("uploaded", len(files), len(files)),
        )
        batch_id = batch_cursor.lastrowid

        for index, image in enumerate(files, start=1):
            content_hash = hashlib.sha256(image.content).hexdigest()
            canonical_filename = canonical_image_filename(
                image.filename,
                content_hash,
                index,
                timestamp,
            )
            canonical_path = write_unique_file(raw_images_dir / canonical_filename, image.content)
            saved_images.append(canonical_path)

            conn.execute(
                """
                INSERT INTO import_images
                  (
                    batch_id,
                    original_filename,
                    canonical_filename,
                    canonical_path,
                    content_hash,
                    status
                  )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    image.filename,
                    canonical_path.name,
                    str(canonical_path),
                    content_hash,
                    "uploaded",
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        for path in saved_images:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise

    batch = get_import_batch(conn, batch_id)
    if batch is None:
        raise RuntimeError(f"Import batch not found after creation: {batch_id}")
    return batch


def validate_uploaded_image(image: UploadedImage) -> None:
    extension = Path(image.filename).suffix.lower()
    content_type = image.content_type.split(";", 1)[0].strip().lower()
    if not content_type:
        content_type = (mimetypes.guess_type(image.filename)[0] or "").lower()

    if content_type not in ALLOWED_CONTENT_TYPES or extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported image type: {image.filename}")


def canonical_image_filename(
    original_filename: str,
    content_hash: str,
    index: int,
    timestamp: str,
) -> str:
    original_path = Path(original_filename)
    extension = original_path.suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9]+", "-", original_path.stem).strip("-").lower()
    if not stem:
        stem = "image"
    return f"upload_{timestamp}_{index:03d}_{content_hash[:10]}_{stem}{extension}"


def write_unique_file(path: Path, content: bytes) -> Path:
    candidate = path
    counter = 1
    while True:
        try:
            with candidate.open("xb") as handle:
                handle.write(content)
            return candidate
        except FileExistsError:
            candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            counter += 1
        except Exception:
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
            raise


def list_import_images(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM import_images
        WHERE batch_id = ?
        ORDER BY id
        """,
        (batch_id,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def process_import_batch(
    conn: sqlite3.Connection,
    batch_id: int,
    provider: CatalogDraftProvider,
    limit: int = 10,
) -> dict[str, Any]:
    batch_row = conn.execute("SELECT id FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
    if batch_row is None:
        raise ValueError("Import batch not found.")

    rows = conn.execute(
        """
        SELECT *
        FROM import_images
        WHERE batch_id = ?
          AND status IN ('uploaded', 'failed')
        ORDER BY id
        LIMIT ?
        """,
        (batch_id, limit),
    ).fetchall()
    images = [row_to_dict(row) for row in rows]
    if not images:
        return refresh_import_batch_status(conn, batch_id)

    image_ids = [image["id"] for image in images]
    placeholders = ", ".join("?" for _ in image_ids)
    claim_cursor = conn.execute(
        f"""
        UPDATE import_images
        SET status = 'processing',
            error_message = ''
        WHERE id IN ({placeholders})
          AND status IN ('uploaded', 'failed')
        """,
        image_ids,
    )
    if claim_cursor.rowcount != len(image_ids):
        conn.rollback()
        raise ValueError("Import images were already claimed for processing.")

    conn.execute(
        """
        UPDATE import_batches
        SET status = 'processing',
            error_message = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (batch_id,),
    )
    conn.commit()

    try:
        payload = provider.generate_drafts(images, list_items_for_prompt(conn))
        create_draft_records(conn, batch_id, payload, images)
        return refresh_import_batch_status(conn, batch_id)
    except Exception as exc:
        conn.rollback()
        mark_import_images_failed(conn, batch_id, image_ids, str(exc))
        return refresh_import_batch_status(conn, batch_id)


def create_draft_records(
    conn: sqlite3.Connection,
    batch_id: int,
    payload: dict[str, Any],
    images: list[dict[str, Any]],
) -> list[int]:
    selected_image_ids = {image["id"] for image in images}
    created_draft_ids: list[int] = []
    draft_items = payload.get("draft_items") or []
    if not draft_items:
        raise ValueError("draft_items must include at least one draft item.")

    referenced_image_ids = set()
    for draft in draft_items:
        source_image_ids = source_image_ids_for_draft(draft, selected_image_ids)
        referenced_image_ids.update(source_image_ids)
        normalized = normalize_draft_item(draft)
        columns = ["batch_id", *normalized.keys()]
        values = [batch_id, *normalized.values()]
        placeholders = ", ".join("?" for _ in columns)
        cursor = conn.execute(
            f"INSERT INTO draft_items ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        draft_item_id = int(cursor.lastrowid)
        created_draft_ids.append(draft_item_id)

        representative_id = draft.get("representative_source_image_id")
        if representative_id not in source_image_ids and source_image_ids:
            representative_id = source_image_ids[0]

        for image_id in source_image_ids:
            conn.execute(
                """
                INSERT INTO draft_item_images
                  (draft_item_id, import_image_id, image_reference, is_representative)
                VALUES (?, ?, ?, ?)
                """,
                (
                    draft_item_id,
                    image_id,
                    normalized["image_reference"],
                    1 if image_id == representative_id else 0,
                ),
            )
            conn.execute(
                """
                UPDATE import_images
                SET status = 'processed',
                    draft_item_id = ?,
                    error_message = ''
                WHERE id = ?
                """,
                (draft_item_id, image_id),
            )

    missing_image_ids = selected_image_ids - referenced_image_ids
    if missing_image_ids:
        raise ValueError("draft_items must reference every selected import image id.")

    for observation in payload.get("observations", []):
        draft_index = observation.get("draft_index")
        draft_item_id = None
        if isinstance(draft_index, int) and 0 <= draft_index < len(created_draft_ids):
            draft_item_id = created_draft_ids[draft_index]
        conn.execute(
            """
            INSERT INTO draft_observations
              (batch_id, draft_item_id, category, observation_type, detail, action_needed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                draft_item_id,
                str(observation.get("category") or "").strip(),
                str(observation.get("observation_type") or "").strip(),
                str(observation.get("detail") or "").strip(),
                str(observation.get("action_needed") or "").strip(),
            ),
        )

    return created_draft_ids


def source_image_ids_for_draft(
    draft: dict[str, Any],
    selected_image_ids: set[int],
) -> list[int]:
    source_image_ids = []
    seen = set()
    for image_id in draft.get("source_image_ids") or []:
        if image_id not in selected_image_ids:
            raise ValueError("source_image_ids must reference selected import image ids.")
        if image_id not in seen:
            source_image_ids.append(image_id)
            seen.add(image_id)
    if not source_image_ids:
        raise ValueError("source_image_ids must reference at least one selected import image id.")
    return source_image_ids


def normalize_draft_item(draft: dict[str, Any]) -> dict[str, Any]:
    item_updates: dict[str, Any] = {}
    for field in ITEM_FIELD_ORDER:
        if field in INTEGER_ITEM_FIELDS:
            item_updates[field] = draft.get(field)
        else:
            item_updates[field] = draft.get(field, "")

    normalized = normalize_item_updates(item_updates)
    validation_warnings = normalize_validation_warnings(draft.get("validation_warnings"))
    normalized.update(
        {
            "status": "needs_review",
            "proposed_item_id": str(draft.get("proposed_item_id") or "").strip(),
            "image_reference": str(draft.get("image_reference") or "").strip(),
            "generation_notes": str(draft.get("generation_notes") or "").strip(),
            "validation_warnings_json": json.dumps(validation_warnings, ensure_ascii=False),
            "raw_model_json": json.dumps(draft, ensure_ascii=False),
        }
    )
    return normalized


def normalize_validation_warnings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def mark_import_images_failed(
    conn: sqlite3.Connection,
    batch_id: int,
    image_ids: list[int],
    error_message: str,
) -> None:
    placeholders = ", ".join("?" for _ in image_ids)
    conn.execute(
        f"""
        UPDATE import_images
        SET status = 'failed',
            draft_item_id = NULL,
            error_message = ?
        WHERE batch_id = ?
          AND id IN ({placeholders})
        """,
        [error_message, batch_id, *image_ids],
    )
    conn.execute(
        """
        UPDATE import_batches
        SET status = 'failed',
            error_message = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (error_message, batch_id),
    )
    conn.commit()


def draft_item_images(conn: sqlite3.Connection, draft_item_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          import_images.*,
          draft_item_images.image_reference AS draft_image_reference,
          draft_item_images.is_representative AS is_representative
        FROM draft_item_images
        JOIN import_images ON import_images.id = draft_item_images.import_image_id
        WHERE draft_item_images.draft_item_id = ?
        ORDER BY draft_item_images.is_representative DESC, import_images.id ASC
        """,
        (draft_item_id,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def draft_item_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    draft = row_to_dict(row)
    warnings_json = draft.get("validation_warnings_json") or "[]"
    try:
        draft["validation_warnings"] = json.loads(warnings_json)
    except json.JSONDecodeError:
        draft["validation_warnings"] = []
    draft["images"] = draft_item_images(conn, draft["id"])
    return draft


def get_draft_item(conn: sqlite3.Connection, draft_item_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM draft_items WHERE id = ?", (draft_item_id,)).fetchone()
    if row is None:
        return None
    return draft_item_to_dict(conn, row)


def update_draft_item(
    conn: sqlite3.Connection,
    draft_item_id: int,
    changes: dict[str, Any],
) -> dict[str, Any] | None:
    if get_draft_item(conn, draft_item_id) is None:
        return None

    catalog_changes: dict[str, Any] = {}
    draft_changes: dict[str, Any] = {}
    for field, value in changes.items():
        if field not in DRAFT_UPDATE_FIELDS:
            raise ValueError(f"Unknown draft field: {field}")
        if field in EDITABLE_ITEM_FIELDS:
            catalog_changes[field] = value
        else:
            draft_changes[field] = normalize_draft_only_update(field, value)

    updates = normalize_item_updates(catalog_changes)
    updates.update(draft_changes)
    if updates:
        assignments = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(
            f"""
            UPDATE draft_items
            SET {assignments},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [*updates.values(), draft_item_id],
        )
        conn.commit()
    return get_draft_item(conn, draft_item_id)


def normalize_draft_only_update(field: str, value: Any) -> Any:
    if field in {"generation_notes", "image_reference", "proposed_item_id"}:
        return "" if value is None else str(value).strip()
    if field == "status":
        status = "" if value is None else str(value).strip()
        if status not in {"generated", "needs_review", "published", "rejected"}:
            raise ValueError("status must be one of generated, needs_review, published, rejected")
        return status
    if field == "validation_warnings_json":
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("validation_warnings_json must be a JSON list") from exc
        if not isinstance(decoded, list):
            raise ValueError("validation_warnings_json must be a JSON list")
        return json.dumps(decoded, ensure_ascii=False)
    raise ValueError(f"Unknown draft field: {field}")


def prefix_for_draft(draft: dict[str, Any]) -> str:
    proposed = (draft.get("proposed_item_id") or "").upper()
    category = (draft.get("category") or "").lower()
    if proposed.startswith("TOP") or any(
        term in category for term in ["shirt", "t-shirt", "jacket", "sweater"]
    ):
        return "TOP"
    if proposed.startswith("BOT") or any(
        term in category for term in ["trouser", "jeans", "shorts", "bottom"]
    ):
        return "BOT"
    if proposed.startswith("SHOE") or "shoe" in category:
        return "SHOE"
    return "ACC"


def next_item_id(conn: sqlite3.Connection, prefix: str) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    highest = 0
    rows = conn.execute(
        "SELECT item_id FROM items WHERE item_id LIKE ?",
        (f"{prefix}-%",),
    ).fetchall()
    for row in rows:
        match = pattern.match(row["item_id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:02d}"


def publish_draft_item(conn: sqlite3.Connection, draft_item_id: int) -> dict[str, Any] | None:
    started_transaction = False
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
        started_transaction = True

    try:
        draft = get_draft_item(conn, draft_item_id)
        if draft is None:
            if started_transaction:
                conn.rollback()
            return None
        if draft["status"] == "rejected":
            if started_transaction:
                conn.rollback()
            raise ValueError("Rejected draft items cannot be published.")
        if draft["status"] == "published" and draft["published_item_id"]:
            item = get_catalog_item(conn, draft["published_item_id"])
            if started_transaction:
                conn.commit()
            return item

        item_id = next_item_id(conn, prefix_for_draft(draft))
        columns = ["item_id", *ITEM_FIELD_ORDER, "raw_json"]
        raw_json = json.dumps({"draft_item_id": draft_item_id}, ensure_ascii=False)
        values = [item_id, *[draft[field] for field in ITEM_FIELD_ORDER], raw_json]
        placeholders = ", ".join("?" for _ in columns)

        conn.execute(
            f"INSERT INTO items ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        for image in draft["images"]:
            conn.execute(
                """
                INSERT INTO item_images
                  (item_id, filename, path, image_reference, is_representative)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    image["canonical_filename"],
                    image["canonical_path"],
                    image.get("draft_image_reference") or draft["image_reference"],
                    image["is_representative"],
                ),
            )

        image_ids = [image["id"] for image in draft["images"]]
        if image_ids:
            placeholders = ", ".join("?" for _ in image_ids)
            conn.execute(
                f"UPDATE import_images SET status = 'published', error_message = '' WHERE id IN ({placeholders})",
                image_ids,
            )
        conn.execute(
            """
            UPDATE draft_items
            SET status = 'published',
                published_item_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (item_id, draft_item_id),
        )
        refresh_import_batch_status(conn, draft["batch_id"], commit=False)
        if started_transaction:
            conn.commit()
    except Exception:
        if started_transaction:
            conn.rollback()
        raise

    return get_catalog_item(conn, item_id)


def reject_draft_item(conn: sqlite3.Connection, draft_item_id: int) -> dict[str, Any] | None:
    draft = get_draft_item(conn, draft_item_id)
    if draft is None:
        return None
    if draft["status"] == "published":
        raise ValueError("Published draft items cannot be rejected.")

    try:
        conn.execute(
            """
            UPDATE draft_items
            SET status = 'rejected',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (draft_item_id,),
        )
        image_ids = [image["id"] for image in draft["images"]]
        if image_ids:
            placeholders = ", ".join("?" for _ in image_ids)
            conn.execute(
                f"UPDATE import_images SET status = 'rejected', error_message = '' WHERE id IN ({placeholders})",
                image_ids,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    refresh_import_batch_status(conn, draft["batch_id"])
    return get_draft_item(conn, draft_item_id)


def list_draft_items(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM draft_items
        WHERE batch_id = ?
        ORDER BY id
        """,
        (batch_id,),
    ).fetchall()
    return [draft_item_to_dict(conn, row) for row in rows]


def list_draft_observations(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM draft_observations
        WHERE batch_id = ?
        ORDER BY id
        """,
        (batch_id,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def attach_import_batch_children(conn: sqlite3.Connection, batch: dict[str, Any]) -> dict[str, Any]:
    batch["images"] = list_import_images(conn, batch["id"])
    batch["draft_items"] = list_draft_items(conn, batch["id"])
    batch["observations"] = list_draft_observations(conn, batch["id"])
    return batch


def refresh_import_batch_status(
    conn: sqlite3.Connection,
    batch_id: int,
    commit: bool = True,
) -> dict[str, Any]:
    counts = conn.execute(
        """
        SELECT
          COUNT(*) AS total_count,
          SUM(CASE WHEN status IN ('processed', 'published', 'rejected') THEN 1 ELSE 0 END) AS processed_count,
          SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) AS processing_count,
          SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count
        FROM import_images
        WHERE batch_id = ?
        """,
        (batch_id,),
    ).fetchone()
    draft_counts = conn.execute(
        """
        SELECT
          COUNT(*) AS draft_count,
          SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) AS published_count,
          SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
          SUM(CASE WHEN status IN ('generated', 'needs_review') THEN 1 ELSE 0 END) AS review_count
        FROM draft_items
        WHERE batch_id = ?
        """,
        (batch_id,),
    ).fetchone()

    total_count = counts["total_count"] or 0
    processed_count = counts["processed_count"] or 0
    processing_count = counts["processing_count"] or 0
    failed_count = counts["failed_count"] or 0
    draft_count = draft_counts["draft_count"] or 0
    published_count = draft_counts["published_count"] or 0
    rejected_count = draft_counts["rejected_count"] or 0
    review_count = draft_counts["review_count"] or 0

    if review_count:
        status = "needs_review"
    elif draft_count and published_count == draft_count and processed_count == total_count:
        status = "published"
    elif draft_count and rejected_count == draft_count and processed_count == total_count:
        status = "failed"
    elif published_count:
        status = "partially_published"
    elif processing_count:
        status = "processing"
    elif failed_count and failed_count == total_count:
        status = "failed"
    else:
        status = "uploaded"

    conn.execute(
        """
        UPDATE import_batches
        SET status = ?,
            processed_file_count = ?,
            published_item_count = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, processed_count, published_count, batch_id),
    )
    if commit:
        conn.commit()

    batch = get_import_batch(conn, batch_id)
    if batch is None:
        raise ValueError("Import batch not found.")
    return batch


def get_import_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM import_batches
        WHERE id = ?
        """,
        (batch_id,),
    ).fetchone()
    if row is None:
        return None

    batch = row_to_dict(row)
    return attach_import_batch_children(conn, batch)
