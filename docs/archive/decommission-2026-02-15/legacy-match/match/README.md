# Playlist Magic Box

This tool helps you match and fix playlists by searching for FLAC files in your music library and generating new M3U playlists with correct paths. It supports input playlists in M3U, JSON, CSV, or XLSX formats.

## Features
- Fuzzy matching of tracks to your FLAC files
- Manual review and matching for unmatched tracks
- Creates new M3U playlists compatible with BluOS
- Supports multiple encodings and playlist formats

## Usage
1. Run the script: `uv run main.py`
2. Enter the path to your playlist file or directory when prompted.
3. Review and confirm matches, then save the fixed playlists.

## Requirements
- Python 3.8+
- See `pyproject.toml` for dependencies

## Notes
- Update the search and save directories in `main.py` as needed.
- Your FLAC files should be organized as described in the script for best results.
