from typing import Any, Optional, Union
from .utils.validator import Validator
from .utils.base_service import BaseService
from ..net.transport.serializer import Serializer
from ..net.sdk_config import SdkConfig
from ..net.environment.environment import Environment
from ..models.utils.sentinel import SENTINEL
from ..models.utils.cast_models import cast_models
from ..models import (
    ArtistsResponse,
    ChartsResponse,
    HttpValidationError,
    LabelsResponse,
    MultisearchResponse,
    ReleasesResponse,
    TracksResponse,
)


class SearchEndpointsService(BaseService):
    """
    Service class for SearchEndpointsService operations.
    Provides methods to interact with SearchEndpointsService-related API endpoints.
    Inherits common functionality from BaseService including authentication and request handling.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the service and method-level configurations."""
        super().__init__(*args, **kwargs)
        self._tracks_search_search_v1_tracks_get_config: SdkConfig = {}
        self._releases_search_search_v1_releases_get_config: SdkConfig = {}
        self._artists_search_search_v1_artists_get_config: SdkConfig = {}
        self._labels_search_search_v1_labels_get_config: SdkConfig = {}
        self._charts_search_search_v1_charts_get_config: SdkConfig = {}
        self._all_search_search_v1_all_get_config: SdkConfig = {}

    def set_tracks_search_search_v1_tracks_get_config(self, config: SdkConfig):
        """
        Sets method-level configuration for tracks_search_search_v1_tracks_get.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._tracks_search_search_v1_tracks_get_config = config
        return self

    def set_releases_search_search_v1_releases_get_config(self, config: SdkConfig):
        """
        Sets method-level configuration for releases_search_search_v1_releases_get.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._releases_search_search_v1_releases_get_config = config
        return self

    def set_artists_search_search_v1_artists_get_config(self, config: SdkConfig):
        """
        Sets method-level configuration for artists_search_search_v1_artists_get.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._artists_search_search_v1_artists_get_config = config
        return self

    def set_labels_search_search_v1_labels_get_config(self, config: SdkConfig):
        """
        Sets method-level configuration for labels_search_search_v1_labels_get.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._labels_search_search_v1_labels_get_config = config
        return self

    def set_charts_search_search_v1_charts_get_config(self, config: SdkConfig):
        """
        Sets method-level configuration for charts_search_search_v1_charts_get.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._charts_search_search_v1_charts_get_config = config
        return self

    def set_all_search_search_v1_all_get_config(self, config: SdkConfig):
        """
        Sets method-level configuration for all_search_search_v1_all_get.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._all_search_search_v1_all_get_config = config
        return self

    @cast_models
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
    ) -> TracksResponse:
        """Returns a set of track results

        :param q: Search query text
        :type q: str
        :param count: The number of results returned in the response, defaults to None
        :type count: int, optional
        :param preorder: When FALSE, the response will not include tracks in a pre-order status. When TRUE, the response will include tracks that are in a pre-order status, defaults to None
        :type preorder: bool, optional
        :param from_publish_date: The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD, defaults to None
        :type from_publish_date: str, optional
        :param to_publish_date: The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD, defaults to None
        :type to_publish_date: str, optional
        :param from_release_date: The date a track was released to the public. Format: YYYY-MM-DD, defaults to None
        :type from_release_date: str, optional
        :param to_release_date: The date a track was released to the public. Format: YYYY-MM-DD, defaults to None
        :type to_release_date: str, optional
        :param genre_id: Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/, defaults to None
        :type genre_id: str, optional
        :param genre_name: Returns tracks that have a genre which partially matches the value inputed. For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc. For a list of genres and their names, make a GET call to our API route /catalog/genres/, defaults to None
        :type genre_name: str, optional
        :param mix_name: Search for a specific mix name, ex: original, defaults to None
        :type mix_name: str, optional
        :param from_bpm: from_bpm, defaults to None
        :type from_bpm: int, optional
        :param to_bpm: to_bpm, defaults to None
        :type to_bpm: int, optional
        :param key_name: Search for a specific key in the following format: A Major, A Minor, A# Major, A# Minor, Ab Major, Ab Minor, defaults to None
        :type key_name: str, optional
        :param mix_name_weight: This parameter determines how much weight to put on mix_name using the search query text from q. The higher the value the more weight is put on matching q to mix_name, defaults to None
        :type mix_name_weight: int, optional
        :param label_name_weight: This parameter determines how much weight to put on label_name using the search query text from q. The higher the value the more weight is put on matching q to label_name, defaults to None
        :type label_name_weight: int, optional
        :param dj_edits: When FALSE, the response will exclude DJ Edit tracks. When TRUE, the response will return only DJ Edit tracks., defaults to None
        :type dj_edits: bool, optional
        :param ugc_remixes: When FALSE, the response will exclude UGC Remix tracks. When TRUE, the response will return only UGC Remix tracks., defaults to None
        :type ugc_remixes: bool, optional
        :param dj_edits_and_ugc_remixes: When FALSE, the response will exclude DJ Edits and UGC Remix tracks. When TRUE, the response will return only DJ Edits or UGC Remix tracks. When parameter is not included, the response will include DJ edits and UGC remixes amongst other tracks., defaults to None
        :type dj_edits_and_ugc_remixes: bool, optional
        :param is_available_for_streaming: By default the response will return both streamable and non-streamable tracks. **Note**: This is dependent on your app scope, if your scope inherently does not allow non-streamable tracks then only streamable tracks will be returned always. When FALSE, the response will return only tracks that are not available for streaming. When TRUE, the response will return only tracks that are available for streaming., defaults to None
        :type is_available_for_streaming: bool, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: TracksResponse
        """

        Validator(str).validate(q)
        Validator(int).is_optional().validate(count)
        Validator(bool).is_optional().validate(preorder)
        Validator(str).is_optional().is_nullable().validate(from_publish_date)
        Validator(str).is_optional().is_nullable().validate(to_publish_date)
        Validator(str).is_optional().is_nullable().validate(from_release_date)
        Validator(str).is_optional().is_nullable().validate(to_release_date)
        Validator(str).is_optional().is_nullable().validate(genre_id)
        Validator(str).is_optional().is_nullable().validate(genre_name)
        Validator(str).is_optional().is_nullable().validate(mix_name)
        Validator(int).is_optional().is_nullable().validate(from_bpm)
        Validator(int).is_optional().is_nullable().validate(to_bpm)
        Validator(str).is_optional().is_nullable().validate(key_name)
        Validator(int).is_optional().min(0).max(10).validate(mix_name_weight)
        Validator(int).is_optional().min(0).max(10).validate(label_name_weight)
        Validator(bool).is_optional().is_nullable().validate(dj_edits)
        Validator(bool).is_optional().is_nullable().validate(ugc_remixes)
        Validator(bool).is_optional().is_nullable().validate(dj_edits_and_ugc_remixes)
        Validator(bool).is_optional().is_nullable().validate(is_available_for_streaming)

        resolved_config = self._get_resolved_config(
            self._tracks_search_search_v1_tracks_get_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.DEFAULT.url}/search/v1/tracks",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("q", q)
            .add_query("count", count)
            .add_query("preorder", preorder)
            .add_query("from_publish_date", from_publish_date, nullable=True)
            .add_query("to_publish_date", to_publish_date, nullable=True)
            .add_query("from_release_date", from_release_date, nullable=True)
            .add_query("to_release_date", to_release_date, nullable=True)
            .add_query("genre_id", genre_id, nullable=True)
            .add_query("genre_name", genre_name, nullable=True)
            .add_query("mix_name", mix_name, nullable=True)
            .add_query("from_bpm", from_bpm, nullable=True)
            .add_query("to_bpm", to_bpm, nullable=True)
            .add_query("key_name", key_name, nullable=True)
            .add_query("mix_name_weight", mix_name_weight)
            .add_query("label_name_weight", label_name_weight)
            .add_query("dj_edits", dj_edits, nullable=True)
            .add_query("ugc_remixes", ugc_remixes, nullable=True)
            .add_query(
                "dj_edits_and_ugc_remixes", dj_edits_and_ugc_remixes, nullable=True
            )
            .add_query(
                "is_available_for_streaming", is_available_for_streaming, nullable=True
            )
            .add_error(422, HttpValidationError)
            .serialize()
            .set_method("GET")
        )

        response, status, _ = self.send_request(serialized_request)
        return TracksResponse.model_validate(response)

    @cast_models
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
    ) -> ReleasesResponse:
        """Returns a set of release results

        :param q: Search query text
        :type q: str
        :param count: The number of results returned in the response, defaults to None
        :type count: int, optional
        :param preorder: When FALSE, the response will not include tracks in a pre-order status. When TRUE, the response will include tracks that are in a pre-order status, defaults to None
        :type preorder: bool, optional
        :param from_publish_date: The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD, defaults to None
        :type from_publish_date: str, optional
        :param to_publish_date: The date a track was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD, defaults to None
        :type to_publish_date: str, optional
        :param from_release_date: The date a track was released to the public. Format: YYYY-MM-DD, defaults to None
        :type from_release_date: str, optional
        :param to_release_date: The date a track was released to the public. Format: YYYY-MM-DD, defaults to None
        :type to_release_date: str, optional
        :param genre_id: Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/, defaults to None
        :type genre_id: str, optional
        :param genre_name: Returns tracks that have a genre which partially matches the value inputed. For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc. For a list of genres and their names, make a GET call to our API route /catalog/genres/, defaults to None
        :type genre_name: str, optional
        :param release_name_weight: release_name_weight, defaults to None
        :type release_name_weight: int, optional
        :param label_name_weight: This parameter determines how much weight to put on label_name using the search query text from q. The higher the value the more weight is put on matching q to label_name, defaults to None
        :type label_name_weight: int, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: ReleasesResponse
        """

        Validator(str).validate(q)
        Validator(int).is_optional().validate(count)
        Validator(bool).is_optional().validate(preorder)
        Validator(str).is_optional().is_nullable().validate(from_publish_date)
        Validator(str).is_optional().is_nullable().validate(to_publish_date)
        Validator(str).is_optional().is_nullable().validate(from_release_date)
        Validator(str).is_optional().is_nullable().validate(to_release_date)
        Validator(str).is_optional().is_nullable().validate(genre_id)
        Validator(str).is_optional().is_nullable().validate(genre_name)
        Validator(int).is_optional().min(0).max(10).validate(release_name_weight)
        Validator(int).is_optional().min(0).max(10).validate(label_name_weight)

        resolved_config = self._get_resolved_config(
            self._releases_search_search_v1_releases_get_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.DEFAULT.url}/search/v1/releases",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("q", q)
            .add_query("count", count)
            .add_query("preorder", preorder)
            .add_query("from_publish_date", from_publish_date, nullable=True)
            .add_query("to_publish_date", to_publish_date, nullable=True)
            .add_query("from_release_date", from_release_date, nullable=True)
            .add_query("to_release_date", to_release_date, nullable=True)
            .add_query("genre_id", genre_id, nullable=True)
            .add_query("genre_name", genre_name, nullable=True)
            .add_query("release_name_weight", release_name_weight)
            .add_query("label_name_weight", label_name_weight)
            .add_error(422, HttpValidationError)
            .serialize()
            .set_method("GET")
        )

        response, status, _ = self.send_request(serialized_request)
        return ReleasesResponse.model_validate(response)

    @cast_models
    def artists_search_search_v1_artists_get(
        self,
        q: str,
        count: int = SENTINEL,
        genre_id: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> ArtistsResponse:
        """Returns a set of artist results

        :param q: Search query text
        :type q: str
        :param count: The number of results returned in the response, defaults to None
        :type count: int, optional
        :param genre_id: Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/, defaults to None
        :type genre_id: str, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: ArtistsResponse
        """

        Validator(str).validate(q)
        Validator(int).is_optional().validate(count)
        Validator(str).is_optional().is_nullable().validate(genre_id)

        resolved_config = self._get_resolved_config(
            self._artists_search_search_v1_artists_get_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.DEFAULT.url}/search/v1/artists",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("q", q)
            .add_query("count", count)
            .add_query("genre_id", genre_id, nullable=True)
            .add_error(422, HttpValidationError)
            .serialize()
            .set_method("GET")
        )

        response, status, _ = self.send_request(serialized_request)
        return ArtistsResponse.model_validate(response)

    @cast_models
    def labels_search_search_v1_labels_get(
        self,
        q: str,
        count: int = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> LabelsResponse:
        """Returns a set of label results

        :param q: Search query text
        :type q: str
        :param count: The number of results returned in the response, defaults to None
        :type count: int, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: LabelsResponse
        """

        Validator(str).validate(q)
        Validator(int).is_optional().validate(count)

        resolved_config = self._get_resolved_config(
            self._labels_search_search_v1_labels_get_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.DEFAULT.url}/search/v1/labels",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("q", q)
            .add_query("count", count)
            .add_error(422, HttpValidationError)
            .serialize()
            .set_method("GET")
        )

        response, status, _ = self.send_request(serialized_request)
        return LabelsResponse.model_validate(response)

    @cast_models
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
    ) -> ChartsResponse:
        """Returns a set of chart results

        :param q: Search query text
        :type q: str
        :param count: The number of results returned in the response, defaults to None
        :type count: int, optional
        :param genre_id: Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added by separating them with a comma, ex: (89, 6, 14). For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/, defaults to None
        :type genre_id: str, optional
        :param genre_name: Returns tracks that have a genre which partially matches the value inputed. For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc. For a list of genres and their names, make a GET call to our API route /catalog/genres/, defaults to None
        :type genre_name: str, optional
        :param is_approved: When TRUE, the response will only include charts that have been approved. When FALSE, the response will include all charts. It is recommended to leave this set to TRUE, defaults to None
        :type is_approved: bool, optional
        :param from_publish_date: The date a chart was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD, defaults to None
        :type from_publish_date: str, optional
        :param to_publish_date: The date a chart was published on Beatport.com or Beatsource.com. Format: YYYY-MM-DD, defaults to None
        :type to_publish_date: str, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: ChartsResponse
        """

        Validator(str).validate(q)
        Validator(int).is_optional().validate(count)
        Validator(str).is_optional().is_nullable().validate(genre_id)
        Validator(str).is_optional().is_nullable().validate(genre_name)
        Validator(bool).is_optional().is_nullable().validate(is_approved)
        Validator(str).is_optional().is_nullable().validate(from_publish_date)
        Validator(str).is_optional().is_nullable().validate(to_publish_date)

        resolved_config = self._get_resolved_config(
            self._charts_search_search_v1_charts_get_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.DEFAULT.url}/search/v1/charts",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("q", q)
            .add_query("count", count)
            .add_query("genre_id", genre_id, nullable=True)
            .add_query("genre_name", genre_name, nullable=True)
            .add_query("is_approved", is_approved, nullable=True)
            .add_query("from_publish_date", from_publish_date, nullable=True)
            .add_query("to_publish_date", to_publish_date, nullable=True)
            .add_error(422, HttpValidationError)
            .serialize()
            .set_method("GET")
        )

        response, status, _ = self.send_request(serialized_request)
        return ChartsResponse.model_validate(response)

    @cast_models
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
    ) -> MultisearchResponse:
        """Returns a set of results for all search types

        :param q: Search query text
        :type q: str
        :param count: The number of results returned in the response, defaults to None
        :type count: int, optional
        :param preorder: When FALSE, the response will not include tracks or releases in a pre-order status. When TRUE, the response will include tracks and releases that are in a pre-order status, defaults to None
        :type preorder: bool, optional
        :param tracks_from_release_date: The date a track was released to the public. Format: YYYY-MM-DD, defaults to None
        :type tracks_from_release_date: str, optional
        :param tracks_to_release_date: The date a track was released to the public. Format: YYYY-MM-DD, defaults to None
        :type tracks_to_release_date: str, optional
        :param releases_from_release_date: The date a release was released to the public. Format: YYYY-MM-DD, defaults to None
        :type releases_from_release_date: str, optional
        :param releases_to_release_date: The date a release was released to the public. Format: YYYY-MM-DD, defaults to None
        :type releases_to_release_date: str, optional
        :param is_approved: When TRUE, the response will only include charts that have been approved. When FALSE, the response will include all charts. It is recommended to leave this set to TRUE, defaults to None
        :type is_approved: bool, optional
        :param is_available_for_streaming: By default the response will return both streamable and non-streamable tracks. **Note**: This is dependent on your app scope, if your scope inherently does not allow non-streamable tracks then only streamable tracks will be returned always. When FALSE, the response will return only tracks that are not available for streaming. When TRUE, the response will return only tracks that are available for streaming., defaults to None
        :type is_available_for_streaming: bool, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: MultisearchResponse
        """

        Validator(str).validate(q)
        Validator(int).is_optional().validate(count)
        Validator(bool).is_optional().validate(preorder)
        Validator(str).is_optional().is_nullable().validate(tracks_from_release_date)
        Validator(str).is_optional().is_nullable().validate(tracks_to_release_date)
        Validator(str).is_optional().is_nullable().validate(releases_from_release_date)
        Validator(str).is_optional().is_nullable().validate(releases_to_release_date)
        Validator(bool).is_optional().is_nullable().validate(is_approved)
        Validator(bool).is_optional().is_nullable().validate(is_available_for_streaming)

        resolved_config = self._get_resolved_config(
            self._all_search_search_v1_all_get_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.DEFAULT.url}/search/v1/all",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("q", q)
            .add_query("count", count)
            .add_query("preorder", preorder)
            .add_query(
                "tracks_from_release_date", tracks_from_release_date, nullable=True
            )
            .add_query("tracks_to_release_date", tracks_to_release_date, nullable=True)
            .add_query(
                "releases_from_release_date", releases_from_release_date, nullable=True
            )
            .add_query(
                "releases_to_release_date", releases_to_release_date, nullable=True
            )
            .add_query("is_approved", is_approved, nullable=True)
            .add_query(
                "is_available_for_streaming", is_available_for_streaming, nullable=True
            )
            .add_error(422, HttpValidationError)
            .serialize()
            .set_method("GET")
        )

        response, status, _ = self.send_request(serialized_request)
        return MultisearchResponse.model_validate(response)
