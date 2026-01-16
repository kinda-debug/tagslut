# FLAC Dedupe Project Guidelines

## Build & Configuration

### Dependencies
This project uses **Poetry** for dependency management. Python 3.11+ is required.

```bash
# Install dependencies
poetry install

# Update dependencies
poetry update
```

### Configuration
The project uses TOML configuration files. Set the `DEDUPE_CONFIG` environment variable to specify a custom config path, or place `config.toml` in the project root (see `config.example.toml` for reference).

## Testing

### Running Tests
```bash
# Run all tests
poetry run pytest

# Run tests with verbose output
poetry run pytest -v

# Run a specific test file
poetry run pytest tests/test_config.py -v

# Run a specific test function
poetry run pytest tests/test_config.py::test_get_config_reads_env_path -v
```

### Test Structure
- Tests are located in the `tests/` directory
- Test files follow the naming convention `test_*.py`
- Shared fixtures are defined in `tests/conftest.py`
- Test data fixtures are stored in `tests/data/`

### Available Fixtures (from conftest.py)
- `fixture_dir` - Path to test data directory
- `healthy_flac_path`, `corrupt_flac_path`, `truncated_flac_path` - FLAC test files
- `mock_file_record` - Mock file record dictionary
- `mock_duplicate_pair` - Pair of duplicate file records
- `mock_database` - In-memory SQLite database
- `populated_database` - Pre-populated test database
- `tmp_path` - pytest built-in for temporary directories

### Custom Markers
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow-running tests

### Adding New Tests
1. Create a test file in `tests/` with the `test_` prefix
2. Use type hints for all function signatures
3. Import fixtures from conftest.py as needed
4. Follow the existing pattern:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest


def test_example_function(tmp_path: Path) -> None:
    """Docstring describing what the test verifies."""
    # Arrange
    test_file = tmp_path / "test.flac"

    # Act
    result = some_function(test_file)

    # Assert
    assert result is not None
```

## Code Quality

### Linting & Type Checking
```bash
# Run flake8 linting
poetry run flake8 dedupe tools tests

# Run mypy type checking
poetry run mypy dedupe

# Run all checks (lint, type-check, test)
make check
```

### Code Style
- **Max line length**: 100 characters (configured in `.flake8`)
- **Type hints**: Required for all function signatures (mypy strict mode enabled)
- **Imports**: Use `from __future__ import annotations` at the top of files
- **Docstrings**: Use triple-quoted docstrings for modules, classes, and functions

### Project Structure
```
dedupe/
├── core/          # Core deduplication logic (decisions, matching, metadata)
├── filters/       # File filtering utilities
├── migrations/    # Database migrations
├── storage/       # Database schema and storage operations
└── utils/         # Utility functions (config, hashing, etc.)
tools/             # CLI tools and scripts
tests/             # Test suite
```

## Makefile Commands
```bash
make help          # Show all available commands
make install       # Install dependencies
make test          # Run tests
make lint          # Run flake8
make type-check    # Run mypy
make check         # Run all checks (lint, type-check, test)
make clean         # Clean Python cache files
```

## Known Issues
- Some test files (`test_manifest.py`, `test_metadata.py`, `test_picard_reconcile.py`) have import errors due to missing modules - these are skipped during normal test runs
