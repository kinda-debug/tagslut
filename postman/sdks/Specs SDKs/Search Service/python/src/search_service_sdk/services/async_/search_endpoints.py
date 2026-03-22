from typing import Awaitable, Optional, Union
from .utils.to_async import to_async
from ..search_endpoints import SearchEndpointsService
from ...net.sdk_config import SdkConfig
from ...models.utils.sentinel import SENTINEL
from ...models import (
    TracksResponse,
    ReleasesResponse,
    ArtistsResponse,
    LabelsResponse,
    ChartsResponse,
    MultisearchResponse,
)


class SearchEndpointsServiceAsync(SearchEndpointsService):
    """
    Async Wrapper for SearchEndpointsServiceAsync
    """

    def tracks_search_search_v1_tracks_get(
        self,
        q: str,
        count: int = SENTINEL,
        preorder: bool = SENTINEL,
        from_publish_date: Union[str, None] = SENTINEL,
        to_publish_date: Union[str, None] = SENTINEL,
        from_release_date: Union[str, None] = SENTINEL,
        to_release_date: Union[str, None] = SENTINEL,
        genre_id: Union[str, None] = SENTINEL,
        genre_name: Union[str, None] = SENTINEL,
        mix_name: Union[str, None] = SENTINEL,
        from_bpm: Union[int, None] = SENTINEL,
        to_bpm: Union[int, None] = SENTINEL,
        key_name: Union[str, None] = SENTINEL,
        mix_name_weight: int = SENTINEL,
        label_name_weight: int = SENTINEL,
        dj_edits: Union[bool, None] = SENTINEL,
        ugc_remixes: Union[bool, None] = SENTINEL,
        dj_edits_and_ugc_remixes: Union[bool, None] = SENTINEL,
        is_available_for_streaming: Union[bool, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[TracksResponse]:
        return to_async(super().tracks_search_search_v1_tracks_get)(
            q,
            count,
            preorder,
            from_publish_date,
            to_publish_date,
            from_release_date,
            to_release_date,
            genre_id,
            genre_name,
            mix_name,
            from_bpm,
            to_bpm,
            key_name,
            mix_name_weight,
            label_name_weight,
            dj_edits,
            ugc_remixes,
            dj_edits_and_ugc_remixes,
            is_available_for_streaming,
            request_config=request_config,
        )

    def releases_search_search_v1_releases_get(
        self,
        q: str,
        count: int = SENTINEL,
        preorder: bool = SENTINEL,
        from_publish_date: Union[str, None] = SENTINEL,
        to_publish_date: Union[str, None] = SENTINEL,
        from_release_date: Union[str, None] = SENTINEL,
        to_release_date: Union[str, None] = SENTINEL,
        genre_id: Union[str, None] = SENTINEL,
        genre_name: Union[str, None] = SENTINEL,
        release_name_weight: int = SENTINEL,
        label_name_weight: int = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[ReleasesResponse]:
        return to_async(super().releases_search_search_v1_releases_get)(
            q,
            count,
            preorder,
            from_publish_date,
            to_publish_date,
            from_release_date,
            to_release_date,
            genre_id,
            genre_name,
            release_name_weight,
            label_name_weight,
            request_config=request_config,
        )

    def artists_search_search_v1_artists_get(
        self,
        q: str,
        count: int = SENTINEL,
        genre_id: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[ArtistsResponse]:
        return to_async(super().artists_search_search_v1_artists_get)(
            q, count, genre_id, request_config=request_config
        )

    def labels_search_search_v1_labels_get(
        self,
        q: str,
        count: int = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[LabelsResponse]:
        return to_async(super().labels_search_search_v1_labels_get)(
            q, count, request_config=request_config
        )

    def charts_search_search_v1_charts_get(
        self,
        q: str,
        count: int = SENTINEL,
        genre_id: Union[str, None] = SENTINEL,
        genre_name: Union[str, None] = SENTINEL,
        is_approved: Union[bool, None] = SENTINEL,
        from_publish_date: Union[str, None] = SENTINEL,
        to_publish_date: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[ChartsResponse]:
        return to_async(super().charts_search_search_v1_charts_get)(
            q,
            count,
            genre_id,
            genre_name,
            is_approved,
            from_publish_date,
            to_publish_date,
            request_config=request_config,
        )

    def all_search_search_v1_all_get(
        self,
        q: str,
        count: int = SENTINEL,
        preorder: bool = SENTINEL,
        tracks_from_release_date: Union[str, None] = SENTINEL,
        tracks_to_release_date: Union[str, None] = SENTINEL,
        releases_from_release_date: Union[str, None] = SENTINEL,
        releases_to_release_date: Union[str, None] = SENTINEL,
        is_approved: Union[bool, None] = SENTINEL,
        is_available_for_streaming: Union[bool, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[MultisearchResponse]:
        return to_async(super().all_search_search_v1_all_get)(
            q,
            count,
            preorder,
            tracks_from_release_date,
            tracks_to_release_date,
            releases_from_release_date,
            releases_to_release_date,
            is_approved,
            is_available_for_streaming,
            request_config=request_config,
        )
