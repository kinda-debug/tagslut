from pathlib import Path

import pytest

from tagslut.metadata.enricher import Enricher


def test_default_provider_list_excludes_itunes() -> None:
    enricher = Enricher(db_path=Path(":memory:"))
    assert "itunes" not in enricher.provider_names


def test_unknown_provider_fails_deterministically() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        Enricher(db_path=Path(":memory:"), providers=["itunes"])
