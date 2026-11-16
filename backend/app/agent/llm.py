"""Thin OpenAI wrapper: structured outputs, embeddings, and cost accounting.

Every call goes through a ``Meter`` so each run (and each Q&A answer) knows
exactly what it spent. Prices are USD per 1M tokens.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

from ..config import get_settings

log = logging.getLogger("tellwind.llm")

# (input, cached input, output) per 1M tokens
PRICES: dict[str, tuple[float, float, float]] = {
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.5": (1.25, 0.125, 10.00),
    "gpt-5.1": (1.25, 0.125, 10.00),
    "gpt-4.1": (2.00, 0.50, 8.00),
    "text-embedding-3-small": (0.02, 0.02, 0.0),
}
WEB_SEARCH_CALL_USD = 0.01  # per web_search tool call


@dataclass
class Meter:
    usage: dict[str, dict[str, int]] = field(default_factory=dict)
    extra_usd: float = 0.0
    calls: int = 0

    def add(self, model: str, inp: int, cached: int, out: int) -> None:
        u = self.usage.setdefault(model, {"input": 0, "cached": 0, "output": 0, "calls": 0})
        u["input"] += inp
        u["cached"] += cached
        u["output"] += out
        u["calls"] += 1
        self.calls += 1

    @property
    def cost_usd(self) -> float:
        total = self.extra_usd
        for model, u in self.usage.items():
            p_in, p_cached, p_out = PRICES.get(model, (2.0, 0.2, 12.0))
            total += (u["input"] - u["cached"]) * p_in / 1e6
            total += u["cached"] * p_cached / 1e6
            total += u["output"] * p_out / 1e6
        return round(total, 6)

    def as_dict(self) -> dict:
        return {"models": self.usage, "extra_usd": self.extra_usd, "cost_usd": self.cost_usd}


class LLMError(RuntimeError):
    pass


_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        key = get_settings().openai_api_key
        if not key:
            raise LLMError("OPENAI_API_KEY is not set")
        _client = AsyncOpenAI(api_key=key, max_retries=0, timeout=120)
    return _client


async def _retry(fn, attempts: int = 4):
    delay = 2.0
    for i in range(attempts):
        try:
            return await fn()
        except (RateLimitError, APIConnectionError) as e:
            if i == attempts - 1:
                raise LLMError(str(e)) from e
        except APIStatusError as e:
            if e.status_code < 500 or i == attempts - 1:
                raise LLMError(f"{e.status_code}: {e.message}") from e
        await asyncio.sleep(delay)
        delay *= 2


def _record(meter: Meter, model: str, usage: Any) -> None:
    if usage is None:
        return
    cached = 0
    details = getattr(usage, "input_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", 0) or 0
    meter.add(model, usage.input_tokens or 0, cached, usage.output_tokens or 0)


async def structured(
    meter: Meter,
    *,
    model: str,
    system: str,
    user: str,
    schema: dict,
    name: str,
    effort: str = "low",
    max_output_tokens: int = 16000,
) -> dict:
    """Call the Responses API with a strict JSON schema and return the parsed object."""

    async def call():
        return await client().responses.create(
            model=model,
            instructions=system,
            input=user,
            reasoning={"effort": effort},
            max_output_tokens=max_output_tokens,
            text={"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
        )

    resp = await _retry(call)
    _record(meter, model, resp.usage)
    text = resp.output_text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as e:
        raise LLMError(f"{name}: model returned invalid JSON ({resp.status})") from e


async def with_web_search(
    meter: Meter, *, model: str, system: str, user: str, effort: str = "low"
) -> tuple[str, list[dict]]:
    """Free-text answer that may use OpenAI's web search tool. Returns text + url citations."""

    async def call():
        return await client().responses.create(
            model=model,
            instructions=system,
            input=user,
            reasoning={"effort": effort},
            tools=[{"type": "web_search"}],
            max_output_tokens=6000,
        )

    resp = await _retry(call)
    _record(meter, model, resp.usage)
    citations: list[dict] = []
    for out in resp.output or []:
        if out.type == "web_search_call":
            meter.extra_usd += WEB_SEARCH_CALL_USD
        if out.type != "message":
            continue
        for c in out.content or []:
            for a in getattr(c, "annotations", None) or []:
                if getattr(a, "type", "") == "url_citation":
                    citations.append(
                        {
                            "url": a.url,
                            "title": getattr(a, "title", "") or a.url,
                            "start": a.start_index,
                            "end": a.end_index,
                        }
                    )
    return resp.output_text or "", citations


async def embed(meter: Meter, texts: list[str], batch: int = 256) -> np.ndarray:
    """Return L2-normalised float32 embeddings, one row per text."""
    model = get_settings().model_embed
    rows: list[np.ndarray] = []
    for i in range(0, len(texts), batch):
        chunk = [t[:6000] or " " for t in texts[i : i + batch]]

        async def call(chunk=chunk):
            return await client().embeddings.create(model=model, input=chunk)

        resp = await _retry(call)
        meter.add(model, resp.usage.prompt_tokens, 0, 0)
        rows.extend(np.asarray(d.embedding, dtype=np.float32) for d in resp.data)
    if not rows:
        return np.zeros((0, 1536), dtype=np.float32)
    m = np.vstack(rows)
    m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
    return m


def to_bytes(v: np.ndarray) -> bytes:
    return v.astype(np.float32).tobytes()


def from_bytes(b: bytes | None) -> np.ndarray | None:
    if not b:
        return None
    return np.frombuffer(b, dtype=np.float32)
