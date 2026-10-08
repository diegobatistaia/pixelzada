"""Single entry point for every Claude call the pipeline makes.

Keeping the call shape in one place means model, effort, thinking and fallback
policy are decided once (in site.config.yaml) instead of drifting across
modules. Every caller gets a validated Pydantic object back, never loose text.
"""
from __future__ import annotations

import os
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from .config import Config

T = TypeVar("T", bound=BaseModel)

# Server-side refusal fallback: if the model declines, the API re-runs the same
# request on a fallback model within the same call instead of returning nothing.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def client() -> anthropic.Anthropic:
    # Resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or an `ant auth login`
    # profile, in that order.
    return anthropic.Anthropic(max_retries=3, timeout=600.0)


def parse(
    cfg: Config,
    *,
    system: str,
    user: str,
    schema: type[T],
    effort: str | None = None,
    max_tokens: int | None = None,
) -> T:
    """One structured request. Raises LLMError on refusal or truncation."""
    model = cfg.get("model.id", "claude-opus-5")
    try:
        response = client().beta.messages.parse(
            model=model,
            max_tokens=max_tokens or cfg.get("model.max_tokens", 16000),
            betas=[FALLBACK_BETA],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": effort or cfg.get("model.effort", "high")},
            # The system prompt is stable across a run; cache it.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
    except anthropic.BadRequestError as exc:
        raise LLMError(f"requisição inválida: {exc.message}") from exc
    except anthropic.AuthenticationError as exc:
        raise LLMError("ANTHROPIC_API_KEY ausente ou inválida") from exc
    except anthropic.RateLimitError as exc:
        retry = exc.response.headers.get("retry-after", "60")
        raise LLMError(f"rate limit; tentar de novo em {retry}s") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"erro da API ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("falha de conexão com a API") from exc

    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "category", "sem categoria")
        raise LLMError(f"modelo recusou a requisição ({detail})")
    if response.stop_reason == "max_tokens":
        raise LLMError("resposta truncada por max_tokens — aumentar model.max_tokens")
    if response.parsed_output is None:
        raise LLMError("resposta sem saída estruturada válida")
    return response.parsed_output
