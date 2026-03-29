from typing import Any, Optional, Union
from .utils.validator import Validator
from .utils.base_service import BaseService
from ..net.transport.serializer import Serializer
from ..net.sdk_config import SdkConfig
from ..net.environment.environment import Environment
from ..models.utils.sentinel import SENTINEL
from ..models.utils.cast_models import cast_models


class ValidationRunService(BaseService):
    """
    Service class for ValidationRunService operations.
    Provides methods to interact with ValidationRunService-related API endpoints.
    Inherits common functionality from BaseService including authentication and request handling.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the service and method-level configurations."""
        super().__init__(*args, **kwargs)
        self._v_6a_resolve_tidal_album_to_isrc_config: SdkConfig = {
            "environment": Environment.API
        }
        self._v_6b_track_by_id_validation_config: SdkConfig = {
            "environment": Environment.BASE_URL
        }
        self._v_6c_run_notes_config: SdkConfig = {"environment": Environment.EXAMPLE}

    def set_v_6a_resolve_tidal_album_to_isrc_config(self, config: SdkConfig):
        """
        Sets method-level configuration for v_6a_resolve_tidal_album_to_isrc.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._v_6a_resolve_tidal_album_to_isrc_config = config
        return self

    def set_v_6b_track_by_id_validation_config(self, config: SdkConfig):
        """
        Sets method-level configuration for v_6b_track_by_id_validation.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._v_6b_track_by_id_validation_config = config
        return self

    def set_v_6c_run_notes_config(self, config: SdkConfig):
        """
        Sets method-level configuration for v_6c_run_notes.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._v_6c_run_notes_config = config
        return self

    @cast_models
    def v_6a_resolve_tidal_album_to_isrc(
        self,
        country_code: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """v_6a_resolve_tidal_album_to_isrc

        :param country_code: country_code, defaults to None
        :type country_code: str, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).is_optional().is_nullable().validate(country_code)

        resolved_config = self._get_resolved_config(
            self._v_6a_resolve_tidal_album_to_isrc_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.API.url or Environment.DEFAULT.url}/v1/albums/507881809/tracks",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("countryCode", country_code, nullable=True)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response

    @cast_models
    def v_6b_track_by_id_validation(
        self, beatport_test_track_id: str, *, request_config: Optional[SdkConfig] = None
    ) -> Any:
        """v_6b_track_by_id_validation

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
            self._v_6b_track_by_id_validation_config, request_config
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
    def v_6c_run_notes(self, *, request_config: Optional[SdkConfig] = None) -> Any:
        """v_6c_run_notes

        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        resolved_config = self._get_resolved_config(
            self._v_6c_run_notes_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.EXAMPLE.url or Environment.DEFAULT.url}/",
                [],
                resolved_config,
            )
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response
