"""Small OpenAI-compatible client for vLLM."""

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()


class LLMServiceError(RuntimeError):
    pass


def _base_url() -> str:
    return os.getenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def _model_name(client: httpx.AsyncClient) -> str:
    configured = os.getenv("LLM_MODEL", "").strip()
    if configured:
        return configured
    try:
        response = await client.get(f"{_base_url()}/models", headers=_headers())
        response.raise_for_status()
        models = response.json().get("data", [])
        if models and models[0].get("id"):
            return str(models[0]["id"])
    except Exception as exc:
        raise LLMServiceError(
            "Could not discover a model from the vLLM /v1/models endpoint. Set LLM_MODEL explicitly."
        ) from exc
    raise LLMServiceError("No model was returned by the vLLM /v1/models endpoint.")


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.0,
    max_tokens: int = 900,
) -> str:
    """Call vLLM's OpenAI-compatible chat-completions endpoint."""
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            model = await _model_name(client)
            response = await client.post(
                f"{_base_url()}/chat/completions",
                headers=_headers(),
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            content = payload["choices"][0]["message"].get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    str(part.get("text", "")) for part in content if isinstance(part, dict)
                )
            if not isinstance(content, str) or not content.strip():
                raise LLMServiceError("The model returned an empty response.")
            return content.strip()
    except LLMServiceError:
        raise
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise LLMServiceError(
            f"vLLM returned HTTP {exc.response.status_code}: {detail}"
        ) from exc
    except Exception as exc:
        raise LLMServiceError(f"Could not connect to the vLLM API: {exc}") from exc
