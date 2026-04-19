from __future__ import annotations

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.beatport import BeatportProvider
from tagslut.tag.providers.metadata_adapter import MetadataServiceTagProvider


class BeatportTagProvider(MetadataServiceTagProvider):
    def __init__(
        self,
        *,
        token_manager: TokenManager | None = None,
        metadata_provider: BeatportProvider | None = None,
    ) -> None:
        super().__init__(
            name="beatport",
            provider_factory=lambda tm: BeatportProvider(token_manager=tm),
            token_manager=token_manager,
            metadata_provider=metadata_provider,
        )
