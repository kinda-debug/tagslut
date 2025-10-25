# Audio Suite

**Audio Suite** is a forward‑thinking command‑line utility for managing your local FLAC music library, matching playlists to your tracks and fetching new music from streaming services.  It combines the best ideas of the *sluttools* project (interactive fuzzy matching and transparent playlist exports) with the structured, plugin‑oriented architecture of *flaccid*.

## Key features

- **Interactive first‑run wizard** – walks you through configuring your music library, database location and export paths using a simple full‑screen TUI powered by Rich.  Configuration values are persisted via Dynaconf and can be overridden by environment variables.

- **Persistent music database** – scans your local music collection on demand and stores track metadata in a SQLAlchemy‑backed SQLite database.  This allows fast, fuzzy matching against playlists or streaming provider results.

- **Transparent fuzzy matching** – automatically matches playlist entries to your local library with a confidence score and exposes the reasoning behind each match.  Ambiguous matches are surfaced for manual review.

- **Plugin architecture** – providers such as Qobuz or Tidal live under the `get.providers` namespace.  Adding support for a new streaming service is as simple as implementing a few well‑defined functions.  Export formats (M3U, JSON, SongShift) and matching algorithms are likewise pluggable.

- **Secure credentials & secrets** – sensitive values like API keys and passwords are stored via the system keyring.  Secrets are loaded from a `.secrets.toml` file ignored by version control and never printed to console.

- **Modern CLI** – built on [Typer](https://typer.tiangolo.com/), commands are discoverable and well documented.  Each subcommand has its own module, making it easy to maintain and extend.

## Project layout

```
audio_suite/
├── pyproject.toml          # Project metadata & dependencies
├── README.md               # This file
├── LICENSE                 # MIT license
├── settings.toml           # Default configuration values
└── src/
    └── audio_suite/
        ├── __init__.py
        ├── cli.py          # Entry point for the Typer CLI
        ├── core/
        │   ├── config.py   # Dynaconf settings loader & helper
        │   ├── db.py       # Database engine & models
        │   ├── models.py   # SQLAlchemy ORM models
        │   └── utils.py    # Shared helpers
        ├── get/
        │   ├── __init__.py
        │   └── providers/
        │       ├── __init__.py
        │       ├── qobuz.py  # Qobuz provider stub
        │       └── tidal.py  # Tidal provider stub
        ├── plugins/
        │   ├── __init__.py
        │   ├── export/
        │   │   ├── __init__.py
        │   │   └── playlist.py  # Export formats
        │   └── match/
        │       ├── __init__.py
        │       └── engine.py  # Matching logic
        └── tui/
            ├── __init__.py
            └── wizard.py      # Interactive configuration & matching wizard
```

## Licensing

This project is distributed under the terms of the MIT License.  It merges ideas and high‑level workflows from the GPL‑licensed *flaccid* project, but all code herein is written from scratch and may be freely used in proprietary or open source projects.
