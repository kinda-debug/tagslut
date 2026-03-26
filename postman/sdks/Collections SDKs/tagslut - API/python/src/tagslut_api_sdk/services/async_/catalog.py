from typing import Awaitable, Optional, Any, Union
from .utils.to_async import to_async
from ..catalog import CatalogService
from ...net.sdk_config import SdkConfig
from ...models.utils.sentinel import SENTINEL


class CatalogServiceAsync(CatalogService):
    """
    Async Wrapper for CatalogServiceAsync
    """

    def track_by_id(
        self, beatport_test_track_id: str, *, request_config: Optional[SdkConfig] = None
    ) -> Awaitable[Any]:
        return to_async(super().track_by_id)(
            beatport_test_track_id, request_config=request_config
        )

    def tracks_by_isrc_query_param(
        self,
        isrc: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().tracks_by_isrc_query_param)(
            isrc, request_config=request_config
        )

    def isrc_store_lookup_path_based_phase_3d(
        self, beatport_test_isrc: str, *, request_config: Optional[SdkConfig] = None
    ) -> Awaitable[Any]:
        return to_async(super().isrc_store_lookup_path_based_phase_3d)(
            beatport_test_isrc, request_config=request_config
        )

    def release_by_id(
        self,
        beatport_test_release_id: str,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().release_by_id)(
            beatport_test_release_id, request_config=request_config
        )

    def release_tracks(
        self,
        beatport_test_release_id: str,
        per_page: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().release_tracks)(
            beatport_test_release_id, per_page, request_config=request_config
        )
