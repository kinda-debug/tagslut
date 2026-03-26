from typing import Any, Optional, Union
from .utils.validator import Validator
from .utils.base_service import BaseService
from ..net.transport.serializer import Serializer
from ..net.sdk_config import SdkConfig
from ..net.environment.environment import Environment
from ..models.utils.sentinel import SENTINEL
from ..models.utils.cast_models import cast_models


class IdentityVerificationService(BaseService):
    """
    Service class for IdentityVerificationService operations.
    Provides methods to interact with IdentityVerificationService-related API endpoints.
    Inherits common functionality from BaseService including authentication and request handling.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the service and method-level configurations."""
        super().__init__(*args, **kwargs)
        self._v_5a_beatport_isrc_lookup_config: SdkConfig = {
            "environment": Environment.BASE_URL_1
        }
        self._v_5b_tidal_isrc_cross_check_config: SdkConfig = {
            "environment": Environment.API
        }
        self._v_5c_spotify_isrc_cross_check_config: SdkConfig = {
            "environment": Environment.API_1
        }

    def set_v_5a_beatport_isrc_lookup_config(self, config: SdkConfig):
        """
        Sets method-level configuration for v_5a_beatport_isrc_lookup.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._v_5a_beatport_isrc_lookup_config = config
        return self

    def set_v_5b_tidal_isrc_cross_check_config(self, config: SdkConfig):
        """
        Sets method-level configuration for v_5b_tidal_isrc_cross_check.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._v_5b_tidal_isrc_cross_check_config = config
        return self

    def set_v_5c_spotify_isrc_cross_check_config(self, config: SdkConfig):
        """
        Sets method-level configuration for v_5c_spotify_isrc_cross_check.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._v_5c_spotify_isrc_cross_check_config = config
        return self

    @cast_models
    def v_5a_beatport_isrc_lookup(
        self,
        isrc: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """v_5a_beatport_isrc_lookup

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
            self._v_5a_beatport_isrc_lookup_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL_1.url or Environment.DEFAULT.url}/v4/catalog/tracks",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("isrc", isrc, nullable=True)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response

    @cast_models
    def v_5b_tidal_isrc_cross_check(
        self,
        isrc: Union[str, None] = SENTINEL,
        country_code: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """v_5b_tidal_isrc_cross_check

        :param isrc: isrc, defaults to None
        :type isrc: str, optional
        :param country_code: country_code, defaults to None
        :type country_code: str, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).is_optional().is_nullable().validate(isrc)
        Validator(str).is_optional().is_nullable().validate(country_code)

        resolved_config = self._get_resolved_config(
            self._v_5b_tidal_isrc_cross_check_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.API.url or Environment.DEFAULT.url}/v1/tracks",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("isrc", isrc, nullable=True)
            .add_query("countryCode", country_code, nullable=True)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response

    @cast_models
    def v_5c_spotify_isrc_cross_check(
        self,
        q: Union[str, None] = SENTINEL,
        type_: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """v_5c_spotify_isrc_cross_check

        :param q: q, defaults to None
        :type q: str, optional
        :param type_: type_, defaults to None
        :type type_: str, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).is_optional().is_nullable().validate(q)
        Validator(str).is_optional().is_nullable().validate(type_)

        resolved_config = self._get_resolved_config(
            self._v_5c_spotify_isrc_cross_check_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.API_1.url or Environment.DEFAULT.url}/v1/search",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .add_query("q", q, nullable=True)
            .add_query("type", type_, nullable=True)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response
