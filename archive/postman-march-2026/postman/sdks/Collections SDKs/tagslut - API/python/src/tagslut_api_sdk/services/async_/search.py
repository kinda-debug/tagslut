from typing import Awaitable, Optional, Any, Union
from .utils.to_async import to_async
from ..search import SearchService
from ...net.sdk_config import SdkConfig
from ...models.utils.sentinel import SENTINEL


class SearchServiceAsync(SearchService):
    """
    Async Wrapper for SearchServiceAsync
    """

    def search_tracks_by_text(
        self,
        q: Union[str, None] = SENTINEL,
        count: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().search_tracks_by_text)(
            q, count, request_config=request_config
        )
