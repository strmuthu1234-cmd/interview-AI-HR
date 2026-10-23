"""Provider-agnostic LLM client (OpenAI or Anthropic) returning structured JSON.

* API keys come from environment variables only.
* If no provider is configured a clear AIConfigurationError is raised – results
  are never silently faked. A clearly labelled mock mode must be selected
  explicitly (AI_PROVIDER=mock or Settings -> AI provider = mock).
"""
import json
import logging
import re

import httpx
from django.conf import settings

from apps.core.defaults import get_org_settings

from .errors import AIConfigurationError, AIProviderError

log = logging.getLogger(__name__)

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4.1"}
ANTHROPIC_VERSION = "2023-06-01"


def extract_json(text: str):
    """Parse a JSON object from model output (tolerates code fences / prose)."""
    if not isinstance(text, str):
        raise ValueError("empty model output")
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


class BaseClient:
    provider = ""
    model = ""
    is_mock = False

    def label(self):
        return "mock" if self.is_mock else f"{self.provider}:{self.model}"

    def complete_json(self, system: str, user: str, max_tokens: int = 4000) -> dict:
        last_err = None
        for attempt in range(2):
            prompt = user if attempt == 0 else user + "\n\nYour previous reply was not valid JSON. Reply with ONE valid JSON object only."
            raw = self._complete(system, prompt, max_tokens)
            try:
                data = extract_json(raw)
                if not isinstance(data, dict):
                    raise ValueError("expected a JSON object")
                return data
            except (ValueError, json.JSONDecodeError) as exc:
                last_err = exc
                log.warning("AI returned invalid JSON (attempt %s): %s", attempt + 1, exc)
        raise AIProviderError(f"The AI provider returned invalid JSON: {last_err}")

    def _complete(self, system, user, max_tokens):  # pragma: no cover - interface
        raise NotImplementedError


class MockClient(BaseClient):
    """Marker client. Services branch on `is_mock` and use their own labelled
    deterministic test implementations; this client never calls a network."""

    provider = "mock"
    model = "mock-testing-mode"
    is_mock = True

    def _complete(self, system, user, max_tokens):
        raise AIProviderError("Mock mode does not call an LLM.")


class AnthropicClient(BaseClient):
    provider = "anthropic"

    def __init__(self, model):
        self.model = model

    def _complete(self, system, user, max_tokens):
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=settings.AI_REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Could not reach Anthropic: {exc.__class__.__name__}") from exc
        if r.status_code != 200:
            raise AIProviderError(f"Anthropic API error {r.status_code}: {r.text[:300]}")
        parts = r.json().get("content", [])
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


class OpenAIClient(BaseClient):
    provider = "openai"

    def __init__(self, model):
        self.model = model

    def _complete(self, system, user, max_tokens):
        try:
            r = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": self.model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=settings.AI_REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Could not reach OpenAI: {exc.__class__.__name__}") from exc
        if r.status_code != 200:
            raise AIProviderError(f"OpenAI API error {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]


def _resolve(org):
    cfg = get_org_settings(org)["ai"]
    provider = (cfg.get("provider") or settings.AI_PROVIDER or "").lower()
    model = cfg.get("model") or settings.AI_MODEL or DEFAULT_MODELS.get(provider, "")
    return provider, model, cfg


def get_client(org) -> BaseClient:
    """Return a ready client or raise AIConfigurationError with a clear message."""
    provider, model, _ = _resolve(org)
    if provider == "mock":
        return MockClient()
    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise AIConfigurationError("AI provider 'anthropic' is selected but ANTHROPIC_API_KEY is not set on the server.")
        return AnthropicClient(model)
    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise AIConfigurationError("AI provider 'openai' is selected but OPENAI_API_KEY is not set on the server.")
        return OpenAIClient(model)
    raise AIConfigurationError(
        "No AI provider is configured. Set AI_PROVIDER (openai or anthropic) and the matching API key in the "
        "server environment, or explicitly choose the clearly-labelled 'mock' testing mode in Settings."
    )


def resume_ai_allowed(org) -> bool:
    """Real AI may read resume-derived content only if HR enabled sharing."""
    return bool(get_org_settings(org)["ai"].get("allow_resume_sharing"))


def get_resume_client(org):
    """Client for tasks that send (de-identified) resume content to the provider.

    Returns None when a real provider is configured but sharing is NOT allowed
    (callers then use deterministic local processing). Mock client is returned
    as-is (no data leaves the server). Raises AIConfigurationError if nothing is
    configured at all and `strict` semantic is handled by callers.
    """
    try:
        client = get_client(org)
    except AIConfigurationError:
        return None
    if client.is_mock:
        return client
    return client if resume_ai_allowed(org) else None


def ai_status(org):
    provider, model, cfg = _resolve(org)
    configured, message = True, "ready"
    try:
        get_client(org)
    except AIConfigurationError as exc:
        configured, message = False, str(exc)
    return {
        "provider": provider or None,
        "model": model or None,
        "configured": configured,
        "is_mock": provider == "mock",
        "message": message,
        "allow_resume_sharing": bool(cfg.get("allow_resume_sharing")),
        "server_stt_available": bool(settings.OPENAI_API_KEY),
        "keys_present": {"openai": bool(settings.OPENAI_API_KEY), "anthropic": bool(settings.ANTHROPIC_API_KEY)},
    }
