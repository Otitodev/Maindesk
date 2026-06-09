"""Qwen / DashScope client wrapper (TRD §11).

Uses the OpenAI-compatible DashScope endpoint so we can lean on the
`openai` SDK rather than maintain a bespoke HTTP client.
"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from app.config import get_settings


@lru_cache
def qwen_client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(api_key=s.qwen_api_key, base_url=s.qwen_api_base)


async def complete(
    model: str,
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> str:
    resp = await qwen_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


async def embed(text: str) -> list[float]:
    """Generate a vector embedding via DashScope's OpenAI-compatible API.

    DashScope accepts the OpenAI `dimensions` parameter through
    `/compatible-mode/v1/embeddings`. Allowed values per model:

      * text-embedding-v3: {1024 (default), 768, 512}  — FIXED set only
      * text-embedding-v4: {2048, 1536, 1024, 768, 512, 256, 128, 64}

    If you need a non-standard dimension (e.g. 256), pin
    `QWEN_EMBED_MODEL=text-embedding-v4` in your .env. Passing an
    unsupported value to v3 will raise InvalidParameter from DashScope.
    """
    s = get_settings()
    resp = await qwen_client().embeddings.create(
        model=s.qwen_embed_model,
        input=text,
        dimensions=s.qwen_embed_dim,
    )
    return resp.data[0].embedding
