from pathlib import Path

from tagslut.metadata.enricher import Enricher


def test_default_provider_list_excludes_itunes() -> None:
    enricher = Enricher(db_path=Path(":memory:"))
    assert "itunes" not in enricher.provider_names


def test_itunes_provider_is_disabled_by_policy() -> None:
    enricher = Enricher(db_path=Path(":memory:"), providers=["itunes"])

    provider = enricher._get_provider("itunes")

    assert provider is None
