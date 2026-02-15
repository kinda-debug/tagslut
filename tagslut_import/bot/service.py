"""Entrypoint for running the Tagslut Telegram bot."""

from __future__ import annotations

import asyncio

from tagslut.core import load_settings
from tagslut.core.logging import configure_logging
from tagslut.core.paths import PathManager
from tagslut.metadata import ArtworkFetcher, MetadataEnricher, StaticLyricsFetcher
from tagslut.providers import MusicBrainzProvider

from .n8n_bridge import N8NBridge
from .openai_bridge import OpenAIChat
from .telegram import TagslutBot


def run() -> None:
    """Entry point used by ``python -m tagslut.bot.service``."""

    settings = load_settings()
    configure_logging(settings.log_level)
    if not settings.telegram_bot_token:
        raise RuntimeError("TAGSLUT_TELEGRAM_BOT_TOKEN must be configured")

    user_agent = f"{settings.musicbrainz_app_name}/{settings.musicbrainz_app_version}"
    if settings.musicbrainz_contact:
        user_agent += f" ({settings.musicbrainz_contact})"

    provider = MusicBrainzProvider(user_agent=user_agent)
    path_manager = PathManager(settings.data_root)
    artwork_fetcher = ArtworkFetcher(path_manager)
    lyrics_fetcher = StaticLyricsFetcher()
    enricher = MetadataEnricher(artwork_fetcher=artwork_fetcher, lyrics_fetcher=lyrics_fetcher)
    openai_chat = OpenAIChat(settings.openai_api_key) if settings.openai_api_key else None
    n8n_bridge = N8NBridge(settings.n8n_webhook_url) if settings.n8n_webhook_url else None

    bot = TagslutBot(
        settings.telegram_bot_token,
        provider,
        enricher,
        openai_chat=openai_chat,
        n8n_bridge=n8n_bridge,
    )
    application = bot.build_application()

    try:
        application.run_polling()
    finally:
        asyncio.run(provider.close())
        asyncio.run(artwork_fetcher.close())
        if n8n_bridge:
            asyncio.run(n8n_bridge.close())


if __name__ == "__main__":
    run()
