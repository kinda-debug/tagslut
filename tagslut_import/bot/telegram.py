"""Telegram bot implementation."""

from __future__ import annotations

from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from tagslut.core.models import Track
from tagslut.metadata.enrichment import MetadataEnricher
from tagslut.providers.base import MusicProvider

from .n8n_bridge import N8NBridge
from .openai_bridge import OpenAIChat


class TagslutBot:
    """Telegram bot that surfaces Tagslut provider capabilities."""

    def __init__(
        self,
        token: str,
        provider: MusicProvider,
        enricher: MetadataEnricher,
        *,
        openai_chat: Optional[OpenAIChat] = None,
        n8n_bridge: Optional[N8NBridge] = None,
    ) -> None:
        if not token:
            raise ValueError("Telegram bot token must be provided")
        self._token = token
        self._provider = provider
        self._enricher = enricher
        self._openai_chat = openai_chat
        self._n8n_bridge = n8n_bridge

    def build_application(self) -> Application:
        """Create the telegram application with registered handlers."""

        application = ApplicationBuilder().token(self._token).build()
        application.add_handler(CommandHandler("track", self._handle_track_command))
        application.add_handler(CommandHandler("search", self._handle_search_command))
        application.add_handler(CommandHandler("lyrics", self._handle_lyrics_command))
        application.add_handler(CommandHandler("health", self._handle_health_command))
        application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_message,
            )
        )
        return application

    async def _handle_track_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = " ".join(context.args) if context.args else ""
        if not query:
            await _reply(update, "Usage: /track <query>")
            return
        tracks = await self._provider.search_track(query, limit=1)
        if not tracks:
            await _reply(update, "No tracks found.")
            return
        enriched = await self._enricher.enrich_track(
            tracks[0], fetch_artwork=False, fetch_lyrics=False
        )
        message = _format_track(enriched.track)
        await _reply(update, message)
        await self._emit_event("track", query, enriched.track)

    async def _handle_search_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = " ".join(context.args) if context.args else ""
        if not query:
            await _reply(update, "Usage: /search <query>")
            return
        tracks = await self._provider.search_track(query, limit=5)
        if not tracks:
            await _reply(update, "No tracks found.")
            return
        lines = [f"{idx + 1}. {_format_track(track)}" for idx, track in enumerate(tracks)]
        await _reply(update, "\n".join(lines))
        await self._emit_event("search", query, *tracks)

    async def _handle_lyrics_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = " ".join(context.args) if context.args else ""
        if not query:
            await _reply(update, "Usage: /lyrics <query>")
            return
        tracks = await self._provider.search_track(query, limit=1)
        if not tracks:
            await _reply(update, "Track not found.")
            return
        enriched = await self._enricher.enrich_track(
            tracks[0], fetch_artwork=False, fetch_lyrics=True
        )
        lyrics = enriched.lyrics or "Lyrics not available."
        await _reply(update, lyrics)
        await self._emit_event("lyrics", query, enriched.track)

    async def _handle_health_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply(update, "Tagslut bot is operational.")

    async def _handle_message(
        self,
        update: Update,
        _: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._openai_chat:
            await _reply(update, "No AI responder configured.")
            return
        prompt = update.message.text if update.message else ""
        reply = await self._openai_chat.generate_reply(
            prompt, system_prompt="You are the Tagslut helper bot."
        )
        await _reply(update, reply)
        if prompt:
            await self._emit_event("message", prompt)

    async def _emit_event(self, event_type: str, query: str, *tracks: Track) -> None:
        if not self._n8n_bridge:
            return
        payload = {
            "event": event_type,
            "query": query,
            "tracks": [track.model_dump() for track in tracks],
        }
        await self._n8n_bridge.send_event(payload)


async def _reply(update: Update, message: str) -> None:
    if update.message:
        await update.message.reply_text(message)


def _format_track(track: Track) -> str:
    artists = ", ".join(artist.name for artist in track.artists) or "Unknown artist"
    return f"{artists} - {track.title}"


__all__ = ["TagslutBot"]
