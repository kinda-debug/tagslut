from typing import Any, Optional
from .utils.validator import Validator
from .utils.base_service import BaseService
from ..net.transport.serializer import Serializer
from ..net.sdk_config import SdkConfig
from ..net.environment.environment import Environment
from ..models.utils.cast_models import cast_models
from ..models import GetTokenClientCredentialsRequest


class AuthService(BaseService):
    """
    Service class for AuthService operations.
    Provides methods to interact with AuthService-related API endpoints.
    Inherits common functionality from BaseService including authentication and request handling.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the service and method-level configurations."""
        super().__init__(*args, **kwargs)
        self._get_token_client_credentials_config: SdkConfig = {
            "environment": Environment.BASE_URL
        }
        self._introspect_token_config: SdkConfig = {"environment": Environment.BASE_URL}

    def set_get_token_client_credentials_config(self, config: SdkConfig):
        """
        Sets method-level configuration for get_token_client_credentials.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._get_token_client_credentials_config = config
        return self

    def set_introspect_token_config(self, config: SdkConfig):
        """
        Sets method-level configuration for introspect_token.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._introspect_token_config = config
        return self

    @cast_models
    def get_token_client_credentials(
        self,
        request_body: GetTokenClientCredentialsRequest,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """get_token_client_credentials

        :param request_body: The request body.
        :type request_body: GetTokenClientCredentialsRequest
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(GetTokenClientCredentialsRequest).is_nullable().validate(request_body)

        resolved_config = self._get_resolved_config(
            self._get_token_client_credentials_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL.url or Environment.DEFAULT.url}/v4/auth/o/token",
                [],
                resolved_config,
            )
            .serialize()
            .set_method("POST")
            .set_body(request_body, "application/x-www-form-urlencoded")
        )

        response, _, _ = self.send_request(serialized_request)
        return response

    @cast_models
    def introspect_token(self, *, request_config: Optional[SdkConfig] = None) -> Any:
        """introspect_token

        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        resolved_config = self._get_resolved_config(
            self._introspect_token_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL.url or Environment.DEFAULT.url}/v4/auth/o/introspect",
                [self.get_access_token(resolved_config)],
                resolved_config,
            )
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response
