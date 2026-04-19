from __future__ import annotations

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.qobuz import QobuzProvider
from tagslut.tag.providers.metadata_adapter import MetadataServiceTagProvider


class QobuzTagProvider(MetadataServiceTagProvider):
    def __init__(
        self,
        *,
        token_manager: TokenManager | None = None,
        metadata_provider: QobuzProvider | None = None,
    ) -> None:
        super().__init__(
            name="qobuz",
            provider_factory=lambda tm: QobuzProvider(token_manager=tm),
            token_manager=token_manager,
            metadata_provider=metadata_provider,
            require_credentials=True,
        )
