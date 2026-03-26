from typing import Awaitable, Optional, Any, Union
from .utils.to_async import to_async
from ..my_library import MyLibraryService
from ...net.sdk_config import SdkConfig
from ...models.utils.sentinel import SENTINEL


class MyLibraryServiceAsync(MyLibraryService):
    """
    Async Wrapper for MyLibraryServiceAsync
    """

    def my_beatport_tracks(
        self,
        page: Union[str, None] = SENTINEL,
        per_page: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().my_beatport_tracks)(
            page, per_page, request_config=request_config
        )

    def my_account(
        self, *, request_config: Optional[SdkConfig] = None
    ) -> Awaitable[Any]:
        return to_async(super().my_account)(request_config=request_config)
