from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from db import load_dotenv

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_CATALOG_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_CATALOG_IMAGE_BYTES = 20 * 1024 * 1024
MAX_CATALOG_IMAGE_BATCH_BYTES = 50 * 1024 * 1024

CATALOG_DRAFT_ITEM_PROPERTIES = {
    "source_image_ids": {"type": "array", "items": {"type": "integer"}},
    "representative_source_image_id": {"type": ["integer", "null"]},
    "proposed_item_id": {"type": "string"},
    "category": {"type": "string"},
    "sub_category": {"type": "string"},
    "brand": {"type": "string"},
    "color_primary": {"type": "string"},
    "color_secondary": {"type": "string"},
    "pattern": {"type": "string"},
    "fit": {"type": "string"},
    "rise": {"type": "string"},
    "length": {"type": "string"},
    "silhouette": {"type": "string"},
    "neckline": {"type": "string"},
    "drape_notes": {"type": "string"},
    "fit_source": {"type": "string"},
    "fabric": {"type": "string"},
    "weight": {"type": "string"},
    "stretch": {"type": "string"},
    "breathability": {"type": "string"},
    "surface_texture": {"type": "string"},
    "formality": {"type": ["integer", "null"]},
    "vibe_tags": {"type": "string"},
    "occasion_tags": {"type": "string"},
    "layering_position": {"type": "string"},
    "season": {"type": "string"},
    "max_comfortable_temp_c": {"type": "string"},
    "condition": {"type": "string"},
    "wear_frequency_estimate": {"type": "string"},
    "color_temperature": {"type": "string"},
    "skin_tone_interaction": {"type": "string"},
    "skin_tone_caution_flag": {"type": "string"},
    "contrast_level": {"type": "string"},
    "versatility_score": {"type": ["integer", "null"]},
    "role_in_outfit": {"type": "string"},
    "volume_visual_weight": {"type": "string"},
    "shoe_type": {"type": "string"},
    "sole_profile": {"type": "string"},
    "aesthetic_range": {"type": "string"},
    "top_compatibility_note": {"type": "string"},
    "client_notes": {"type": "string"},
    "image_reference": {"type": "string"},
    "generation_notes": {"type": "string"},
    "validation_warnings": {"type": "array", "items": {"type": "string"}},
}

CATALOG_OBSERVATION_PROPERTIES = {
    "draft_index": {"type": ["integer", "null"]},
    "category": {"type": "string"},
    "observation_type": {"type": "string"},
    "detail": {"type": "string"},
    "action_needed": {"type": "string"},
}

CATALOG_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["draft_items", "observations"],
    "properties": {
        "draft_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(CATALOG_DRAFT_ITEM_PROPERTIES),
                "properties": CATALOG_DRAFT_ITEM_PROPERTIES,
            },
        },
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(CATALOG_OBSERVATION_PROPERTIES),
                "properties": CATALOG_OBSERVATION_PROPERTIES,
            },
        },
    },
}

CATALOG_SYSTEM_PROMPT = """You are cataloging Varun's wardrobe for review drafts.
Create one draft item per unique garment, merging duplicate angles only when the same garment is clear.
Use worn photos as fit ground truth when available; otherwise say the draft is based on flat lay only.
Be precise about color, fabric, silhouette, condition, and visible construction details.
Do not guess brands; use Unidentified and add an observation when a label needs manual verification.
Flag warm-skin-tone risks for beige, sand, tan, khaki, nude, and pastel yellow.
Do not inflate versatility or say anything pairs with everything.
Every import image id must appear in source_image_ids for at least one draft item.
Return JSON only in the requested schema."""


class LLMError(RuntimeError):
    pass


class OutfitProvider(Protocol):
    def generate(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any]:
        ...


class OpenAIProvider:
    def __init__(self) -> None:
        load_dotenv()
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.model = normalize_openai_model(os.environ.get("OPENAI_MODEL", ""))
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is not configured.")
        if not self.model:
            raise LLMError("OPENAI_MODEL is not configured.")

    def generate(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "input": messages,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "wardrobe_outfit_recommendations",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
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
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 400 and "model_not_found" in detail:
                detail = (
                    f"{detail}\n\nConfigured OPENAI_MODEL was sent as '{self.model}'. "
                    "For direct OpenAI API calls, use model IDs like 'gpt-5.5' or 'gpt-5.4-mini', "
                    "not provider-prefixed values unless the app normalizes that prefix."
                )
            raise LLMError(f"OpenAI request failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"OpenAI request failed: {exc.reason}") from exc

        text = extract_response_text(payload)
        if not text:
            raise LLMError("OpenAI response did not include structured text output.")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"OpenAI response was not valid JSON: {exc}") from exc


def strip_image_bytes(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": image.get("id"),
            "canonical_filename": image.get("canonical_filename"),
            "original_filename": image.get("original_filename"),
            "status": image.get("status"),
        }
        for image in images
    ]


def build_catalog_request_body(
    model: str,
    images: list[dict[str, Any]],
    published_items: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = "\n\n".join(
        [
            CATALOG_SYSTEM_PROMPT,
            "PUBLISHED_CATALOG_JSON:",
            json.dumps(published_items, ensure_ascii=False, indent=2),
            "IMPORT_IMAGES_JSON:",
            json.dumps(strip_image_bytes(images), ensure_ascii=False, indent=2),
        ]
    )
    content = [{"type": "input_text", "text": prompt}]
    content.extend(
        {"type": "input_image", "image_url": image["data_url"]}
        for image in images
        if image.get("data_url")
    )
    return {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "wardrobe_catalog_drafts",
                "strict": True,
                "schema": CATALOG_DRAFT_SCHEMA,
            }
        },
    }


def image_data_url(path: Path, mime_type: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class OpenAICatalogProvider:
    def __init__(self) -> None:
        load_dotenv()
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.model = normalize_openai_model(os.environ.get("OPENAI_MODEL", ""))
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is not configured.")
        if not self.model:
            raise LLMError("OPENAI_MODEL is not configured.")

    def generate_drafts(
        self,
        images: list[dict[str, Any]],
        published_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        filename: str | Path = "unknown image"
        try:
            hydrated_images = []
            total_image_bytes = 0
            for image in images:
                canonical_path = Path(str(image.get("canonical_path") or ""))
                filename = image.get("canonical_filename") or image.get("original_filename") or canonical_path
                content_type = str(image.get("content_type") or "").split(";", 1)[0].strip().lower()
                if not content_type:
                    content_type = (
                        mimetypes.guess_type(str(canonical_path))[0]
                        or mimetypes.guess_type(str(image.get("canonical_filename") or ""))[0]
                        or "image/jpeg"
                    )
                if content_type not in OPENAI_CATALOG_IMAGE_MIME_TYPES:
                    raise LLMError(f"Unsupported OpenAI image MIME type for {filename}: {content_type}")
                image_size = canonical_path.stat().st_size
                if image_size > MAX_CATALOG_IMAGE_BYTES:
                    raise LLMError(
                        f"Import image {filename} is too large: "
                        f"{image_size} bytes exceeds {MAX_CATALOG_IMAGE_BYTES} bytes."
                    )
                total_image_bytes += image_size
                if total_image_bytes > MAX_CATALOG_IMAGE_BATCH_BYTES:
                    raise LLMError(
                        f"Import image batch is too large: "
                        f"{total_image_bytes} bytes exceeds {MAX_CATALOG_IMAGE_BATCH_BYTES} bytes."
                    )
                hydrated = dict(image)
                hydrated["content_type"] = content_type
                hydrated["data_url"] = image_data_url(canonical_path, content_type)
                hydrated_images.append(hydrated)
        except OSError as exc:
            raise LLMError(f"Could not read import image {filename}: {exc}") from exc

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
        except json.JSONDecodeError as exc:
            raise LLMError(f"OpenAI catalog response envelope was not valid JSON: {exc}") from exc

        text = extract_response_text(payload)
        if not text:
            raise LLMError("OpenAI catalog response did not include structured text output.")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"OpenAI catalog response was not valid JSON: {exc}") from exc


def extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    pieces: list[str] = []
    for output in payload.get("output", []):
        for content in output.get("content", []):
            if isinstance(content.get("text"), str):
                pieces.append(content["text"])
    return "".join(pieces)


def normalize_openai_model(model: str) -> str:
    cleaned = model.strip()
    if cleaned.startswith("openai/"):
        return cleaned.split("/", 1)[1]
    return cleaned


def provider_from_env() -> OutfitProvider:
    load_dotenv()
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "openai":
        return OpenAIProvider()
    raise LLMError(f"Unsupported LLM_PROVIDER '{provider}'.")
