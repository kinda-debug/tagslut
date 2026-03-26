from typing import Any, Optional, Union
from .utils.validator import Validator
from .utils.base_service import BaseService
from ..net.transport.serializer import Serializer
from ..net.sdk_config import SdkConfig
from ..net.environment.environment import Environment
from ..models.utils.sentinel import SENTINEL
from ..models.utils.cast_models import cast_models


class CatalogService(BaseService):
    """
    Service class for CatalogService operations.
    Provides methods to interact with CatalogService-related API endpoints.
    Inherits common functionality from BaseService including authentication and request handling.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the service and method-level configurations."""
        super().__init__(*args, **kwargs)
        self._track_by_id_config: SdkConfig = {"environment": Environment.BASE_URL}
        self._tracks_by_isrc_query_param_config: SdkConfig = {
            "environment": Environment.BASE_URL_1
        }
        self._isrc_store_lookup_path_based_phase_3d_config: SdkConfig = {
            "environment": Environment.BASE_URL
        }
        self._release_by_id_config: SdkConfig = {"environment": Environment.BASE_URL}
        self._release_tracks_config: SdkConfig = {"environment": Environment.BASE_URL_1}

    def set_track_by_id_config(self, config: SdkConfig):
        """
        Sets method-level configuration for track_by_id.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._track_by_id_config = config
        return self

    def set_tracks_by_isrc_query_param_config(self, config: SdkConfig):
        """
        Sets method-level configuration for tracks_by_isrc_query_param.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._tracks_by_isrc_query_param_config = config
        return self

    def set_isrc_store_lookup_path_based_phase_3d_config(self, config: SdkConfig):
        """
        Sets method-level configuration for isrc_store_lookup_path_based_phase_3d.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._isrc_store_lookup_path_based_phase_3d_config = config
        return self

    def set_release_by_id_config(self, config: SdkConfig):
        """
        Sets method-level configuration for release_by_id.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._release_by_id_config = config
        return self

    def set_release_tracks_config(self, config: SdkConfig):
        """
        Sets method-level configuration for release_tracks.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._release_tracks_config = config
        return self

    @cast_models
    def track_by_id(
        self, beatport_test_track_id: str, *, request_config: Optional[SdkConfig] = None
    ) -> Any:
        """track_by_id

        :param beatport_test_track_id: beatport_test_track_id
        :type beatport_test_track_id: str
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).validate(beatport_test_track_id)

        resolved_config = self._get_resolved_config(
            self._track_by_id_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL.url or Environment.DEFAULT.url}/v4/catalog/tracks/{{beatport_test_track_id}}",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_path("beatport_test_track_id", beatport_test_track_id)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response

    @cast_models
    def tracks_by_isrc_query_param(
        self,
        isrc: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """tracks_by_isrc_query_param

        :param isrc: isrc, defaults to None
        :type isrc: str, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).is_optional().is_nullable().validate(isrc)

        resolved_config = self._get_resolved_config(
            self._tracks_by_isrc_query_param_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL_1.url or Environment.DEFAULT.url}/v4/catalog/tracks",
                [],
                resolved_config,
            )
            .add_query("isrc", isrc, nullable=True)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response

    @cast_models
    def isrc_store_lookup_path_based_phase_3d(
        self, beatport_test_isrc: str, *, request_config: Optional[SdkConfig] = None
    ) -> Any:
        """isrc_store_lookup_path_based_phase_3d

        :param beatport_test_isrc: beatport_test_isrc
        :type beatport_test_isrc: str
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).validate(beatport_test_isrc)

        resolved_config = self._get_resolved_config(
            self._isrc_store_lookup_path_based_phase_3d_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL.url or Environment.DEFAULT.url}/v4/catalog/tracks/store/{{beatport_test_isrc}}",
                [self.get_basic_auth(resolved_config)],
                resolved_config,
            )
            .add_path("beatport_test_isrc", beatport_test_isrc)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response

    @cast_models
    def release_by_id(
        self,
        beatport_test_release_id: str,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """release_by_id

        :param beatport_test_release_id: beatport_test_release_id
        :type beatport_test_release_id: str
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).validate(beatport_test_release_id)

        resolved_config = self._get_resolved_config(
            self._release_by_id_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL.url or Environment.DEFAULT.url}/v4/catalog/releases/{{beatport_test_release_id}}",
                [],
                resolved_config,
            )
            .add_path("beatport_test_release_id", beatport_test_release_id)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response

    @cast_models
    def release_tracks(
        self,
        beatport_test_release_id: str,
        per_page: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """release_tracks

        :param beatport_test_release_id: beatport_test_release_id
        :type beatport_test_release_id: str
        :param per_page: per_page, defaults to None
        :type per_page: str, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).validate(beatport_test_release_id)
        Validator(str).is_optional().is_nullable().validate(per_page)

        resolved_config = self._get_resolved_config(
            self._release_tracks_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL_1.url or Environment.DEFAULT.url}/v4/catalog/releases/{{beatport_test_release_id}}/tracks",
                [],
                resolved_config,
            )
            .add_path("beatport_test_release_id", beatport_test_release_id)
            .add_query("per_page", per_page, nullable=True)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response
