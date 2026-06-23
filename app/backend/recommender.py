from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from db import ROOT, attach_citations, item_ids_by_category, list_items_for_prompt, list_messages, prior_outfit_sets
from llm import LLMError, provider_from_env

PROMPT_PATH = ROOT / "app" / "prompts" / "stylist.md"

TIME_LABELS = {"morning", "afternoon", "evening", "night", "all-day"}
OCCASION_LABELS = {
    "office",
    "date night",
    "party",
    "restaurant",
    "casual hangout",
    "boys night",
    "travel day",
    "beach/Goa",
    "concert",
    "brunch",
}

OUTFIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assistant_summary", "outfits"],
    "properties": {
        "assistant_summary": {"type": "string"},
        "outfits": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "time_of_day",
                    "occasion",
                    "item_ids",
                    "item_roles",
                    "stylist_notes",
                    "why_it_works",
                    "wearing_notes",
                    "cautions",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "time_of_day": {"type": "string", "enum": sorted(TIME_LABELS)},
                    "occasion": {"type": "string", "enum": sorted(OCCASION_LABELS)},
                    "item_ids": {
                        "type": "array",
                        "minItems": 3,
                        "items": {"type": "string"},
                    },
                    "item_roles": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["item_id", "role"],
                            "properties": {
                                "item_id": {"type": "string"},
                                "role": {"type": "string"},
                            },
                        },
                    },
                    "stylist_notes": {"type": "string"},
                    "why_it_works": {"type": "string"},
                    "wearing_notes": {"type": "string"},
                    "cautions": {"type": "string"},
                },
            },
        },
    },
}


class RecommendationError(RuntimeError):
    pass


def generate_recommendations(conn, conversation_id: int, user_message: str, max_retries: int = 1) -> dict[str, Any]:
    provider = provider_from_env()
    catalog = list_items_for_prompt(conn)
    existing_sets = prior_outfit_sets(conn, conversation_id)
    correction = ""
    last_error = ""

    for attempt in range(max_retries + 1):
        messages = build_messages(conn, conversation_id, user_message, catalog, existing_sets, correction)
        try:
            payload = provider.generate(messages, OUTFIT_SCHEMA)
            validate_payload(conn, payload, existing_sets)
            payload = attach_citations(conn, payload)
            return payload
        except (LLMError, RecommendationError) as exc:
            last_error = str(exc)
            correction = (
                "Your previous response failed validation. Regenerate the full JSON response. "
                f"Validation error: {last_error}"
            )
            if attempt >= max_retries:
                raise RecommendationError(last_error) from exc
    raise RecommendationError(last_error or "Recommendation failed.")


def build_messages(
    conn,
    conversation_id: int,
    user_message: str,
    catalog: list[dict[str, Any]],
    existing_sets: set[tuple[str, ...]],
    correction: str,
) -> list[dict[str, str]]:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    catalog_json = json.dumps(catalog, ensure_ascii=False)
    existing_json = json.dumps([list(item_set) for item_set in sorted(existing_sets)], ensure_ascii=False)
    system = (
        f"{prompt}\n\n"
        "Return only data that conforms to the provided JSON schema.\n"
        "Default to 3 outfit options unless the user explicitly asks for a different count.\n"
        "Use only exact item_id values from CATALOG_JSON.\n"
        "Do not repeat any exact item set from PRIOR_OUTFIT_SETS_JSON.\n\n"
        f"CATALOG_JSON:\n{catalog_json}\n\n"
        f"PRIOR_OUTFIT_SETS_JSON:\n{existing_json}"
    )
    history = []
    for message in list_messages(conn, conversation_id)[-8:]:
        if message["role"] == "error":
            continue
        history.append({"role": message["role"], "content": message["content"]})
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_message}]
    if correction:
        messages.append({"role": "user", "content": correction})
    return messages


def validate_payload(conn, payload: dict[str, Any], existing_sets: set[tuple[str, ...]]) -> None:
    if not isinstance(payload, dict):
        raise RecommendationError("Response payload must be an object.")
    outfits = payload.get("outfits")
    if not isinstance(outfits, list) or not outfits:
        raise RecommendationError("Response must include at least one outfit.")

    valid_ids = {row["item_id"] for row in conn.execute("SELECT item_id FROM items WHERE deleted_at IS NULL")}
    categories = item_ids_by_category(conn)
    seen_sets: set[tuple[str, ...]] = set()

    for index, outfit in enumerate(outfits, start=1):
        if not isinstance(outfit, dict):
            raise RecommendationError(f"Outfit {index} must be an object.")
        title = (outfit.get("title") or "").strip()
        notes = (outfit.get("stylist_notes") or "").strip()
        if not title:
            raise RecommendationError(f"Outfit {index} is missing a title.")
        if len(notes) < 80:
            raise RecommendationError(f"Outfit {index} needs richer stylist_notes.")
        if outfit.get("time_of_day") not in TIME_LABELS:
            raise RecommendationError(f"Outfit {index} has invalid time_of_day.")
        if outfit.get("occasion") not in OCCASION_LABELS:
            raise RecommendationError(f"Outfit {index} has invalid occasion.")

        item_ids = outfit.get("item_ids")
        if not isinstance(item_ids, list) or len(item_ids) < 3:
            raise RecommendationError(f"Outfit {index} must include at least 3 item_ids.")
        normalized = []
        for item_id in item_ids:
            if item_id not in valid_ids:
                raise RecommendationError(f"Outfit {index} references unknown item_id '{item_id}'.")
            normalized.append(item_id)
        outfit_set = tuple(sorted(set(normalized)))
        if outfit_set in existing_sets or outfit_set in seen_sets:
            raise RecommendationError(f"Outfit {index} repeats an exact item set already used in this conversation.")
        seen_sets.add(outfit_set)

        if not categories["tops"].intersection(normalized):
            raise RecommendationError(f"Outfit {index} is missing a top.")
        if not categories["bottoms"].intersection(normalized):
            raise RecommendationError(f"Outfit {index} is missing a bottom.")
        if not categories["shoes"].intersection(normalized):
            raise RecommendationError(f"Outfit {index} is missing shoes.")

        role_entries = outfit.get("item_roles")
        if not isinstance(role_entries, list):
            raise RecommendationError(f"Outfit {index} must include item_roles.")
        roles = {}
        for entry in role_entries:
            if isinstance(entry, dict) and entry.get("item_id") in normalized:
                roles[entry["item_id"]] = str(entry.get("role") or infer_role(entry["item_id"]))
        for item_id in normalized:
            roles.setdefault(item_id, infer_role(item_id))
        outfit["item_ids"] = normalized
        outfit["item_roles"] = roles


def infer_role(item_id: str) -> str:
    if item_id.startswith("TOP-"):
        return "top"
    if item_id.startswith("BOT-"):
        return "bottom"
    if item_id.startswith("SHOE-"):
        return "shoes"
    return "extra"
