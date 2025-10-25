"""Interactive configuration wizard for Audio Suite.

The full‑screen wizard from the original **sluttools** project used Textual
and provided rich UI elements.  Here we implement a simple command‑line
dialogue using prompts, suitable for initial setup.  Future versions
could integrate Textual once available in the environment.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from rich.console import Console
from rich.prompt import Prompt

from ..core import config as core_config


def run_wizard() -> None:
    """Run the configuration wizard interactively."""
    console = Console()
    console.print("[bold blue]Audio Suite Setup Wizard[/bold blue]")
    settings = core_config.get_settings()
    # Prompt for library roots
    default_roots = settings.get("library_roots") or ""
    root_input = Prompt.ask(
        "Enter one or more paths to your music library (comma‑separated)",
        default=default_roots,
    )
    # Prompt for database path
    default_db = settings.get("db_path")
    db_input = Prompt.ask(
        "Enter path for the music database",
        default=str(default_db),
    )
    # Prompt for M3U export path template
    default_m3u = settings.get("match_output_path_m3u")
    m3u_input = Prompt.ask(
        "Enter template for M3U output path (use {playlist_name})",
        default=str(default_m3u),
    )
    # Prompt for JSON export path template
    default_json = settings.get("match_output_path_json")
    json_input = Prompt.ask(
        "Enter template for JSON output path (use {playlist_name})",
        default=str(default_json),
    )
    # Save settings
    core_config.save_user_settings(
        {
            "library_roots": root_input,
            "db_path": db_input,
            "match_output_path_m3u": m3u_input,
            "match_output_path_json": json_input,
        }
    )
    console.print("Configuration saved. You can now run `audio-suite scan` to index your library.")