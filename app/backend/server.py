from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from db import (
    CatalogValidationError,
    add_message,
    apply_schema,
    attach_citations,
    connect,
    delete_catalog_item,
    get_catalog_item,
    get_or_create_conversation,
    image_path_by_id,
    delete_saved_outfit,
    list_catalog_items,
    list_conversations,
    list_items,
    list_messages,
    list_saved_outfits,
    load_dotenv,
    save_outfit,
    update_catalog_item,
)
from recommender import RecommendationError, generate_recommendations
from urllib.parse import parse_qs, unquote


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "WardrobeStylist/0.1"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/health":
                self.json_response({"ok": True, "service": "wardrobe-stylist"})
            elif path == "/api/catalog/summary":
                self.catalog_summary()
            elif path == "/api/items":
                item_type = parse_qs(parsed.query).get("type", ["all"])[0]
                with connect() as conn:
                    apply_schema(conn)
                    self.json_response({"items": list_catalog_items(conn, item_type)})
            elif path.startswith("/api/items/"):
                item_id = unquote(path.split("/api/items/", 1)[1])
                with connect() as conn:
                    apply_schema(conn)
                    item = get_catalog_item(conn, item_id)
                if item is None:
                    self.error_response(404, "Item not found")
                else:
                    self.json_response({"item": item})
            elif path == "/api/conversations":
                with connect() as conn:
                    apply_schema(conn)
                    self.json_response({"conversations": list_conversations(conn)})
            elif path.startswith("/api/conversations/") and path.endswith("/messages"):
                conversation_id = int(path.split("/")[3])
                with connect() as conn:
                    apply_schema(conn)
                    self.json_response({"messages": list_messages(conn, conversation_id)})
            elif path == "/api/saved-outfits":
                with connect() as conn:
                    apply_schema(conn)
                    self.json_response({"saved_outfits": attach_saved_citations(conn)})
            elif path.startswith("/api/item-images/"):
                image_id = int(path.rsplit("/", 1)[1])
                self.stream_image(image_id)
            else:
                self.error_response(404, "Not found")
        except Exception as exc:
            self.error_response(500, str(exc))

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            body = self.read_json()
            if path == "/api/conversations":
                title = (body.get("title") or "New chat").strip() or "New chat"
                with connect() as conn:
                    apply_schema(conn)
                    conversation_id = get_or_create_conversation(conn, None, title)
                    self.json_response({"conversation_id": conversation_id})
            elif path.startswith("/api/conversations/") and path.endswith("/messages"):
                conversation_id = int(path.split("/")[3])
                user_message = (body.get("content") or "").strip()
                if not user_message:
                    self.error_response(400, "Message content is required.")
                    return
                self.create_recommendation(conversation_id, user_message)
            elif path == "/api/saved-outfits":
                self.save_outfit_route(body)
            else:
                self.error_response(404, "Not found")
        except RecommendationError as exc:
            self.error_response(422, str(exc))
        except Exception as exc:
            self.error_response(500, str(exc))

    def do_PATCH(self) -> None:
        try:
            path = urlparse(self.path).path
            if path.startswith("/api/items/"):
                item_id = unquote(path.split("/api/items/", 1)[1])
                body = self.read_json()
                if not isinstance(body, dict):
                    self.error_response(400, "Request body must be a JSON object.")
                    return
                with connect() as conn:
                    apply_schema(conn)
                    item = update_catalog_item(conn, item_id, body)
                if item is None:
                    self.error_response(404, "Item not found")
                else:
                    self.json_response({"item": item})
            else:
                self.error_response(404, "Not found")
        except json.JSONDecodeError:
            self.error_response(400, "Invalid JSON.")
        except CatalogValidationError as exc:
            self.error_response(400, str(exc))
        except Exception as exc:
            self.error_response(500, str(exc))

    def do_DELETE(self) -> None:
        try:
            path = urlparse(self.path).path
            if path.startswith("/api/items/"):
                item_id = unquote(path.split("/api/items/", 1)[1])
                with connect() as conn:
                    apply_schema(conn)
                    deleted = delete_catalog_item(conn, item_id)
                if not deleted:
                    self.error_response(404, "Item not found")
                else:
                    self.json_response({"deleted": True, "item_id": item_id})
            elif path.startswith("/api/saved-outfits/"):
                saved_outfit_id = int(path.rsplit("/", 1)[1])
                with connect() as conn:
                    apply_schema(conn)
                    deleted = delete_saved_outfit(conn, saved_outfit_id)
                if not deleted:
                    self.error_response(404, "Saved outfit not found")
                else:
                    self.json_response({"deleted": True, "saved_outfit_id": saved_outfit_id})
            else:
                self.error_response(404, "Not found")
        except Exception as exc:
            self.error_response(500, str(exc))

    def create_recommendation(self, conversation_id: int, user_message: str) -> None:
        with connect() as conn:
            apply_schema(conn)
            conversation_id = get_or_create_conversation(conn, conversation_id)
            try:
                payload = generate_recommendations(conn, conversation_id, user_message)
            except RecommendationError as exc:
                add_message(conn, conversation_id, "user", user_message)
                add_message(conn, conversation_id, "error", str(exc))
                raise
            add_message(conn, conversation_id, "user", user_message)
            assistant_content = payload.get("assistant_summary") or "Here are outfit options from your wardrobe."
            assistant_id = add_message(conn, conversation_id, "assistant", assistant_content, payload)
            payload["message_id"] = assistant_id
            conn.execute(
                "UPDATE messages SET structured_payload_json = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), assistant_id),
            )
            conn.commit()
            self.json_response(
                {
                    "conversation_id": conversation_id,
                    "message": {
                        "id": assistant_id,
                        "role": "assistant",
                        "content": assistant_content,
                        "structured_payload": payload,
                    },
                }
            )

    def save_outfit_route(self, body: dict) -> None:
        outfit = body.get("outfit") or {}
        source_conversation_id = body.get("source_conversation_id")
        source_message_id = body.get("source_message_id")
        required = ["title", "time_of_day", "occasion", "stylist_notes", "item_ids"]
        missing = [field for field in required if not outfit.get(field)]
        if missing:
            self.error_response(400, f"Missing outfit fields: {', '.join(missing)}")
            return
        with connect() as conn:
            apply_schema(conn)
            saved_id = save_outfit(conn, outfit, source_conversation_id, source_message_id)
            self.json_response({"saved_outfit_id": saved_id})

    def catalog_summary(self) -> None:
        with connect() as conn:
            apply_schema(conn)
            items = list_items(conn)
            images = conn.execute("SELECT COUNT(*) AS count FROM item_images").fetchone()["count"]
            self.json_response({"items": len(items), "images": images})

    def stream_image(self, image_id: int) -> None:
        with connect() as conn:
            apply_schema(conn)
            path = image_path_by_id(conn, image_id)
        if path is None or not path.exists():
            self.error_response(404, "Image not found")
            return
        mime_type, _ = mimetypes.guess_type(str(path))
        data = path.read_bytes()
        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def json_response(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def error_response(self, status: int, message: str) -> None:
        self.json_response({"error": message}, status)

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def attach_saved_citations(conn) -> list[dict]:
    saved = list_saved_outfits(conn)
    for outfit in saved:
        payload = {"outfits": [outfit]}
        attach_citations(conn, payload)
    return saved


def main() -> None:
    load_dotenv()
    host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("BACKEND_PORT", "8765"))
    with connect() as conn:
        apply_schema(conn)
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"Wardrobe stylist backend listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
