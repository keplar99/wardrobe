from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

from db import load_dotenv

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


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
