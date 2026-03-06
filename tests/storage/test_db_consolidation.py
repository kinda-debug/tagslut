import importlib

import pytest


def test_canonical_db_importable() -> None:
    storage = importlib.import_module("tagslut.storage")
    assert hasattr(storage, "schema")
    v3 = importlib.import_module("tagslut.storage.v3")
    assert hasattr(v3, "open_db_v3")


def test_deprecated_db_raises() -> None:
    with pytest.raises(ImportError):
        importlib.import_module("tagslut.db")
