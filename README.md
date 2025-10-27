# FLAC Deduplication with ScaReD

This project provides a modular workflow for scanning, repairing, and deduplicating FLAC audio files in a music library. It uses fingerprinting, segment hashing, and fuzzy matching to identify duplicates, with options for safe repair of corrupted files before deduplication.

## Scripts Overview

The workflow consists of four main scripts that work together in sequence:

1. **`flac_workflow.py`** - Main orchestrator that runs the complete workflow
2. **`flac_scan.py`** - Scans the music library and builds a database index
3. **`flac_repair.py`** - Repairs corrupted FLAC files (run conditionally)
4. **`flac_dedupe.py`** - Performs deduplication based on the scanned database

## Prerequisites

### System Dependencies
- Python 3.8+
- FFmpeg (for audio processing)
- Chromaprint (fpcalc) for audio fingerprinting
- FLAC tools (flac, metaflac)
- SQLite3

### Python Dependencies
All Python dependencies are standard library modules. No external Python packages required.

## Installation

### Option 1: Using Poetry (Recommended)

1. Install Poetry:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. Install system dependencies:
   ```bash
   brew install ffmpeg chromaprint flac sqlite3
   ```

3. Clone/download the project and install:
   ```bash
   cd flac-dedupe
   poetry install
   ```

4. Use the CLI:
   ```bash
   poetry run dedupe --help
   ```

### Option 2: Manual Installation

1. Install system dependencies:
   ```bash
   brew install ffmpeg chromaprint flac sqlite3
   ```

2. Clone or download the scripts to your local machine.

3. Make scripts executable:
   ```bash
   chmod +x *.py
   ```

## Usage

### Using Poetry CLI (Recommended)

The project provides a unified CLI through Poetry:

```bash
# Show help
poetry run dedupe --help

# Run complete workflow
poetry run dedupe workflow --commit

# Scan only
poetry run dedupe scan --verbose

# Check status
poetry run dedupe status

# Clean up
poetry run dedupe clean
```

### Using Makefile (Convenient)

For easier usage, the project includes a Makefile with common commands:

```bash
# Show available commands
make help

# Install dependencies
make install

# Run the CLI
make run

# Run complete workflow
make workflow

# Check status
make status

# Run tests and linting
make check

# Format code
make format
```

### Using ScaReD (Super Concise Runner for Easy Deduplication)

For the ultimate in convenience, use the `scrd` script with short commands:

```bash
# Make scrd available (add to PATH or run from project directory)
./scrd help

# Run full workflow (default when no command specified)
./scrd --commit        # Run complete scan→repair→dedupe workflow

# Short commands
./scrd sc --verbose    # Scan (instead of "poetry run dedupe scan --verbose")
./scrd r               # Repair (instead of "poetry run dedupe repair")
./scrd d --commit      # Dedupe (instead of "poetry run dedupe dedupe --commit")
./scrd wf --commit     # Workflow (instead of "poetry run dedupe workflow --commit")
./scrd st              # Status (instead of "poetry run dedupe status")
./scrd cl              # Clean (instead of "poetry run dedupe clean")
```

**Requirements:**
- Run from the project directory (`cd /path/to/dedupe`)
- Poetry installed (optional - falls back to direct Python execution)
- `config.toml` file (copy from `config.example.toml`)

**Troubleshooting:**
- If `scrd` is not found, run `./scrd` from the project directory
- The script automatically detects Poetry installation or falls back to Python
- Check `config.toml` for correct paths

**Command abbreviations:**
- `sc`/`scan` - Scan library
- `r`/`repair` - Repair broken files
- `d`/`dedupe` - Find/remove duplicates
- `wf`/`workflow` - Complete workflow (default)
- `st`/`status` - Show status
- `cl`/`clean` - Clean up
- `h`/`help` - Show help

### Configuration

ScaReD supports configuration through `config.toml`. Copy `config.example.toml` to `config.toml` and customize:

```bash
cp config.example.toml config.toml
```

Then edit `config.toml` to customize default settings:

```toml
[paths]
root = "/Volumes/dotad/MUSIC"  # Default FLAC library location

[scan]
workers = 8                   # Number of scan worker threads
verbose = false               # Default verbose setting

[dedupe]
commit = false                # Don't commit by default (safer)
verbose = true                # Show dedupe progress
```

All settings can be overridden with command-line options.

### Individual Scripts

You can also run scripts directly:

#### Complete Workflow
```bash
python3 flac_workflow.py
```

#### Scan Only
```bash
python3 flac_scan.py
```
Scans the default music directory and updates the database. Use `--root /path/to/music` to specify a different directory.

#### Repair Only
```bash
python3 flac_repair.py
```
Repairs corrupted FLAC files listed in the broken files playlist.

#### Dedupe Only
```bash
python3 flac_dedupe.py --commit
```
Performs deduplication on the scanned database. Requires `--commit` to actually move/delete files. Uses default root directory `/Volumes/dotad/MUSIC`.

### Command Line Options

#### flac_scan.py
- `--root PATH`: Root directory to scan (default: /Volumes/dotad/MUSIC)
- `--verbose`: Enable verbose logging (default: disabled)
- `--workers N`: Number of worker threads (default: 8)
- `--recompute`: Force recomputation of fingerprints
- `--no-fp`: Skip fingerprint computation
- `--no-segwin`: Skip segment window hashing

#### flac_repair.py
- `--output DIR`: Output directory for repaired files
- `--file PATH`: Repair a single file
- `--ffmpeg-args ARGS`: Custom FFmpeg arguments

#### flac_dedupe.py
- `--root PATH`: Root directory (default: /Volumes/dotad/MUSIC)
- `--commit`: Actually perform deduplication (move losers to trash)
- `--verbose`: Enable verbose logging (default: enabled)
- `--dry-run`: Force dry-run mode
- `--trash-dir DIR`: Custom trash directory
- `--fp-sim-ratio FLOAT`: Fingerprint similarity threshold (default: 0.62)

## Workflow Details

1. **Scanning**: The scan script analyzes all FLAC files, computing fingerprints, segment hashes, and metadata. Results are stored in `_DEDUP_INDEX.db`.

2. **Repair**: If broken files are detected during scanning, the repair script uses FFmpeg to recreate them from the original corrupted files.

3. **Deduplication**: The dedupe script compares files using multiple methods:
   - Exact MD5 matching
   - Fuzzy filename matching
   - Segment window hashing
   - Chromaprint fingerprint similarity

   Duplicate groups are identified, and the "keeper" file is chosen based on quality/bitrate. Losers are moved to a trash directory.

## Configuration

Default settings are optimized for most use cases, but can be customized:

- Music root: `/Volumes/dotad/MUSIC`
- Database: `_DEDUP_INDEX.db` in the root
- Trash directory: `_DEDUP_TRASH` in the root
- Broken files playlist: `broken_files_unrepaired.m3u`

## Safety Features

- Dry-run mode available for testing
- Broken file detection and repair before deduplication
- Detailed logging and progress reporting
- Database-backed operation with run history

## Troubleshooting

- Ensure all tools are in PATH
- Check file permissions on the music directory
- Use `--verbose` for detailed logging
- Run individual scripts to isolate issues

## License

This project is provided as-is for personal use.