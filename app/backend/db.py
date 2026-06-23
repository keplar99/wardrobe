from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "app" / "data" / "wardrobe.sqlite"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
RAW_IMAGES_DIR = ROOT / "data" / "Raw Images"


def load_dotenv(path: Path | None = None) -> None:
    env_paths = [path] if path else [ROOT / ".env", ROOT / ".env.local"]
    for env_path in env_paths:
        if env_path is None or not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def db_path() -> Path:
    configured = os.environ.get("WARDROBE_DB_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_DB_PATH


def connect(path: Path | None = None) -> sqlite3.Connection:
    load_dotenv()
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    ensure_column(conn, "items", "deleted_at", "TEXT")
    ensure_column(conn, "saved_outfits", "why_it_works", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "saved_outfits", "wearing_notes", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "saved_outfits", "cautions", "TEXT NOT NULL DEFAULT ''")
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def reset_database(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS saved_outfit_items;
        DROP TABLE IF EXISTS saved_outfits;
        DROP TABLE IF EXISTS messages;
        DROP TABLE IF EXISTS conversations;
        DROP TABLE IF EXISTS draft_observations;
        DROP TABLE IF EXISTS draft_item_images;
        DROP TABLE IF EXISTS draft_items;
        DROP TABLE IF EXISTS import_images;
        DROP TABLE IF EXISTS import_batches;
        DROP TABLE IF EXISTS item_images;
        DROP TABLE IF EXISTS items;
        """
    )
    apply_schema(conn)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


class CatalogValidationError(ValueError):
    pass


INTEGER_ITEM_FIELDS = {"formality", "versatility_score"}

EDITABLE_ITEM_FIELDS = {
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
    "formality",
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
    "versatility_score",
    "role_in_outfit",
    "volume_visual_weight",
    "shoe_type",
    "sole_profile",
    "aesthetic_range",
    "top_compatibility_note",
    "client_notes",
}

READ_ONLY_ITEM_FIELDS = {
    "item_id",
    "raw_json",
    "deleted_at",
    "created_at",
    "updated_at",
    "images",
    "representative_image",
    "type",
}


def catalog_item_type(item: dict[str, Any]) -> str:
    item_id = item.get("item_id") or ""
    category = (item.get("category") or "").lower()
    if item_id.startswith("TOP-") or any(term in category for term in ["shirt", "t-shirt", "jacket", "sweater"]):
        return "top"
    if item_id.startswith("BOT-") or any(term in category for term in ["trouser", "jeans", "shorts", "bottom"]):
        return "bottom"
    if item_id.startswith("SHOE-") or "shoe" in category:
        return "shoe"
    return "other"


def images_for_item(conn: sqlite3.Connection, item_id: str) -> list[dict[str, Any]]:
    return [
        row_to_dict(row)
        for row in conn.execute(
            "SELECT * FROM item_images WHERE item_id = ? ORDER BY is_representative DESC, id ASC",
            (item_id,),
        )
    ]


def attach_catalog_display_fields(conn: sqlite3.Connection, item: dict[str, Any]) -> dict[str, Any]:
    item["type"] = catalog_item_type(item)
    item["images"] = images_for_item(conn, item["item_id"])
    item["representative_image"] = item["images"][0] if item["images"] else None
    return item


def item_with_images(conn: sqlite3.Connection, item_id: str) -> dict[str, Any] | None:
    item_row = conn.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
    if item_row is None:
        return None
    item = row_to_dict(item_row)
    return attach_catalog_display_fields(conn, item)


def get_catalog_item(conn: sqlite3.Connection, item_id: str) -> dict[str, Any] | None:
    return item_with_images(conn, item_id)


def list_catalog_items(conn: sqlite3.Connection, item_type: str = "all") -> list[dict[str, Any]]:
    normalized_type = (item_type or "all").lower()
    if normalized_type not in {"all", "top", "bottom", "shoe"}:
        raise CatalogValidationError("type must be one of all, top, bottom, shoe")

    items = []
    for row in conn.execute("SELECT * FROM items WHERE deleted_at IS NULL ORDER BY item_id"):
        item = attach_catalog_display_fields(conn, row_to_dict(row))
        if normalized_type == "all" or item["type"] == normalized_type:
            items.append(item)
    return items


def normalize_item_updates(changes: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for field, value in changes.items():
        if field in READ_ONLY_ITEM_FIELDS:
            raise CatalogValidationError(f"{field} is read-only")
        if field not in EDITABLE_ITEM_FIELDS:
            raise CatalogValidationError(f"Unknown item field: {field}")
        if field in INTEGER_ITEM_FIELDS:
            if value is None or value == "":
                normalized[field] = None
                continue
            try:
                normalized[field] = int(value)
            except (TypeError, ValueError) as exc:
                raise CatalogValidationError(f"{field} must be an integer") from exc
        else:
            normalized[field] = "" if value is None else str(value).strip()
    return normalized


def update_catalog_item(conn: sqlite3.Connection, item_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    if get_catalog_item(conn, item_id) is None:
        return None
    updates = normalize_item_updates(changes)
    if updates:
        assignments = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(
            f"UPDATE items SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?",
            [*updates.values(), item_id],
        )
        conn.commit()
    return get_catalog_item(conn, item_id)


def delete_catalog_item(conn: sqlite3.Connection, item_id: str) -> bool:
    cur = conn.execute(
        """
        UPDATE items
        SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE item_id = ?
        """,
        (item_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def list_items(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM items WHERE deleted_at IS NULL ORDER BY item_id").fetchall()
    return [row_to_dict(row) for row in rows]


def list_items_for_prompt(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute("SELECT * FROM items WHERE deleted_at IS NULL ORDER BY item_id"):
        item = row_to_dict(row)
        item.pop("raw_json", None)
        item.pop("deleted_at", None)
        item.pop("created_at", None)
        item.pop("updated_at", None)
        items.append(item)
    return items


def item_ids_by_category(conn: sqlite3.Connection) -> dict[str, set[str]]:
    buckets = {"tops": set(), "bottoms": set(), "shoes": set()}
    for row in conn.execute("SELECT item_id, category FROM items WHERE deleted_at IS NULL"):
        item_id = row["item_id"]
        category = (row["category"] or "").lower()
        if item_id.startswith("TOP-") or any(term in category for term in ["shirt", "t-shirt", "jacket", "sweater"]):
            buckets["tops"].add(item_id)
        if item_id.startswith("BOT-") or any(term in category for term in ["trouser", "jeans", "shorts", "bottom"]):
            buckets["bottoms"].add(item_id)
        if item_id.startswith("SHOE-") or "shoe" in category:
            buckets["shoes"].add(item_id)
    return buckets


def get_or_create_conversation(conn: sqlite3.Connection, conversation_id: int | None, title: str = "New chat") -> int:
    if conversation_id is not None:
        exists = conn.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if exists:
            return int(exists["id"])
    cur = conn.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
    conn.commit()
    return int(cur.lastrowid)


def list_conversations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM conversations ORDER BY updated_at DESC, id DESC"
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def list_messages(conn: sqlite3.Connection, conversation_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conversation_id,),
    ).fetchall()
    return [decode_message(row_to_dict(row)) for row in rows]


def decode_message(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("structured_payload_json")
    message["structured_payload"] = json.loads(payload) if payload else None
    return message


def add_message(
    conn: sqlite3.Connection,
    conversation_id: int,
    role: str,
    content: str,
    structured_payload: dict[str, Any] | None = None,
) -> int:
    payload_json = json.dumps(structured_payload, ensure_ascii=False) if structured_payload is not None else None
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, role, content, structured_payload_json) VALUES (?, ?, ?, ?)",
        (conversation_id, role, content, payload_json),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (conversation_id,),
    )
    conn.commit()
    return int(cur.lastrowid)


def prior_outfit_sets(conn: sqlite3.Connection, conversation_id: int) -> set[tuple[str, ...]]:
    sets: set[tuple[str, ...]] = set()
    rows = conn.execute(
        "SELECT structured_payload_json FROM messages WHERE conversation_id = ? AND role = 'assistant'",
        (conversation_id,),
    ).fetchall()
    for row in rows:
        if not row["structured_payload_json"]:
            continue
        payload = json.loads(row["structured_payload_json"])
        for outfit in payload.get("outfits", []):
            item_ids = outfit.get("item_ids", [])
            if item_ids:
                sets.add(tuple(sorted(set(item_ids))))
    return sets


def attach_citations(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    for outfit in payload.get("outfits", []):
        cited_items = []
        for item_id in outfit.get("item_ids", []):
            item = item_with_images(conn, item_id)
            if item:
                cited_items.append(item)
        outfit["items"] = cited_items
    return payload


def save_outfit(
    conn: sqlite3.Connection,
    outfit: dict[str, Any],
    source_conversation_id: int | None,
    source_message_id: int | None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO saved_outfits
          (
            title,
            time_of_day,
            occasion,
            stylist_notes,
            why_it_works,
            wearing_notes,
            cautions,
            source_conversation_id,
            source_message_id
          )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            outfit["title"],
            outfit["time_of_day"],
            outfit["occasion"],
            outfit["stylist_notes"],
            outfit.get("why_it_works", ""),
            outfit.get("wearing_notes", ""),
            outfit.get("cautions", ""),
            source_conversation_id,
            source_message_id,
        ),
    )
    saved_id = int(cur.lastrowid)
    roles = outfit.get("item_roles", {})
    for index, item_id in enumerate(outfit["item_ids"]):
        conn.execute(
            "INSERT INTO saved_outfit_items (saved_outfit_id, item_id, role, sort_order) VALUES (?, ?, ?, ?)",
            (saved_id, item_id, roles.get(item_id, ""), index),
        )
    conn.commit()
    return saved_id


def list_saved_outfits(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    outfits = []
    for row in conn.execute("SELECT * FROM saved_outfits ORDER BY created_at DESC, id DESC"):
        outfit = row_to_dict(row)
        outfit["item_ids"] = []
        outfit["item_roles"] = {}
        item_rows = conn.execute(
            """
            SELECT soi.role, soi.sort_order, i.*
            FROM saved_outfit_items soi
            JOIN items i ON i.item_id = soi.item_id
            WHERE soi.saved_outfit_id = ?
            ORDER BY soi.sort_order ASC
            """,
            (outfit["id"],),
        ).fetchall()
        outfit["items"] = []
        for item_row in item_rows:
            item = row_to_dict(item_row)
            outfit["item_ids"].append(item["item_id"])
            outfit["item_roles"][item["item_id"]] = item.pop("role") or ""
            item["images"] = [
                row_to_dict(img)
                for img in conn.execute(
                    "SELECT * FROM item_images WHERE item_id = ? ORDER BY is_representative DESC, id ASC",
                    (item["item_id"],),
                )
            ]
            outfit["items"].append(item)
        outfits.append(outfit)
    return outfits


def delete_saved_outfit(conn: sqlite3.Connection, saved_outfit_id: int) -> bool:
    conn.execute("DELETE FROM saved_outfit_items WHERE saved_outfit_id = ?", (saved_outfit_id,))
    cur = conn.execute("DELETE FROM saved_outfits WHERE id = ?", (saved_outfit_id,))
    conn.commit()
    return cur.rowcount > 0


def image_path_by_id(conn: sqlite3.Connection, image_id: int) -> Path | None:
    row = conn.execute("SELECT path FROM item_images WHERE id = ?", (image_id,)).fetchone()
    if row is None:
        return None
    path = Path(row["path"])
    try:
        path.resolve().relative_to(RAW_IMAGES_DIR.resolve())
    except ValueError:
        return None
    return path
