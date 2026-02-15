"""Configuration loader for Tagslut."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", env_prefix="TAGSLUT_")

    environment: str = Field(
        default="development",
        description="Active environment name (development, staging, production).",
    )
    data_root: Path = Field(
        default=Path("./data"),
        description="Root directory for storing downloaded media and caches.",
    )

    spotify_client_id: Optional[str] = Field(
        default=None,
        description="Spotify API client identifier used for authentication.",
    )
    spotify_client_secret: Optional[str] = Field(
        default=None,
        description="Spotify API client secret used for authentication.",
    )
    spotify_access_token: Optional[str] = Field(
        default=None,
        description="Pre-generated Spotify access token for API calls.",
    )
    qobuz_app_id: Optional[str] = Field(
        default=None,
        description="Qobuz application identifier.",
    )
    qobuz_app_secret: Optional[str] = Field(
        default=None,
        description="Qobuz application secret.",
    )
    tidal_client_id: Optional[str] = Field(
        default=None,
        description="Tidal client identifier.",
    )
    tidal_client_secret: Optional[str] = Field(
        default=None,
        description="Tidal client secret.",
    )
    tidal_token: Optional[str] = Field(
        default=None,
        description="Tidal API token for metadata access.",
    )
    tidal_session_id: Optional[str] = Field(
        default=None,
        description="Tidal session identifier required for metadata calls.",
    )
    apple_music_key: Optional[str] = Field(
        default=None,
        description="Apple Music JWT signing key.",
    )
    apple_music_team_id: Optional[str] = Field(
        default=None,
        description="Apple developer team identifier.",
    )
    apple_music_key_id: Optional[str] = Field(
        default=None,
        description="Apple Music key identifier.",
    )
    musicbrainz_app_name: str = Field(
        default="tagslut",
        description="MusicBrainz application name used for User-Agent construction.",
    )
    musicbrainz_app_version: str = Field(
        default="0.1.0",
        description="MusicBrainz application version included in the User-Agent header.",
    )
    musicbrainz_contact: Optional[str] = Field(
        default=None,
        description="Contact information for MusicBrainz API calls.",
    )

    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Telegram bot token.",
    )
    telegram_webhook_url: Optional[HttpUrl] = Field(
        default=None, description="Public webhook URL for the Telegram bot."
    )
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key for text generation.",
    )
    n8n_webhook_url: Optional[HttpUrl] = Field(
        default=None, description="n8n workflow URL for bridging automations."
    )

    log_level: str = Field(
        default="INFO",
        description="Default log level for the application.",
    )

    def as_dict(self) -> Dict[str, Any]:
        """Return the configuration values as a dictionary."""

        return self.model_dump()


@lru_cache(maxsize=1)
def load_settings(env_file: str | Path | None = ".env") -> Settings:
    """Load settings from the environment, optionally reading an ``.env`` file."""

    if env_file:
        load_dotenv(Path(env_file))
    return Settings()


__all__ = ["Settings", "load_settings"]
