"""OpenAI integration helpers."""

from __future__ import annotations

from typing import List

from openai import AsyncOpenAI


class OpenAIChat:
    """Wrapper around the OpenAI chat completion API."""

    def __init__(self, api_key: str, *, model: str = "gpt-4o-mini") -> None:
        if not api_key:
            raise ValueError("OpenAI API key must be provided")
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate_reply(self, prompt: str, *, system_prompt: str | None = None) -> str:
        """Generate a reply to ``prompt`` using the configured OpenAI model."""

        messages: List[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = await self._client.chat.completions.create(model=self._model, messages=messages)
        choice = response.choices[0]
        return choice.message.content or ""


__all__ = ["OpenAIChat"]
