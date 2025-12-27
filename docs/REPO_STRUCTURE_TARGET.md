# Target Repository Structure

## Source Code (`dedupe/`)

### Core Logic (`dedupe/core/`)
Pure business logic. No database connections or CLI args here.
- `hashing.py`: SHA-256 calculation logic.
- `metadata.py`: Mutagen/FLAC interaction logic.
- `integrity.py`: `flac -t` wrapper.
- `matching.py`: Logic to group duplicates.
- `decisions.py`: Deterministic KEEP/DROP ranking engine.
- `actions.py`: Safe `delete` and `move` functions.

### Storage Layer (`dedupe/storage/`)
Persistence and data models.
- `models.py`: `AudioFile`, `Decision`, `DuplicateGroup` dataclasses.
- `schema.py`: `init_db` and migration logic.
- `queries.py`: `upsert_file`, `get_duplicates`, etc.

### Utilities (`dedupe/utils/`)
Shared helpers.
- `config.py`: TOML loader singleton.
- `logging.py`: Standardized logger setup.
- `parallel.py`: `process_map` wrapper.
- `paths.py`: File discovery (`list_files`).
- `cli_helper.py`: Common Click decorators.

## Tools (`tools/`)
The entry points for the user.
- `integrity/scan.py`: The main scanner CLI.
- `decide/recommend.py`: Generates the JSON plan.
- `decide/apply.py`: Executes the JSON plan.
- `review/export.py`: (Future) Export to CSV for manual review.

## Tests (`tests/`)
Mirrors the source structure.
- `core/test_*.py`
- `storage/test_*.py`
- `utils/test_*.py`
- `tools/test_*.py`
