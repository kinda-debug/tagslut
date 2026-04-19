from __future__ import annotations

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.tidal import TidalProvider
from tagslut.tag.providers.metadata_adapter import MetadataServiceTagProvider


class TidalTagProvider(MetadataServiceTagProvider):
    def __init__(
        self,
        *,
        token_manager: TokenManager | None = None,
        metadata_provider: TidalProvider | None = None,
    ) -> None:
        super().__init__(
            name="tidal",
            provider_factory=lambda tm: TidalProvider(token_manager=tm),
            token_manager=token_manager,
            metadata_provider=metadata_provider,
        )
