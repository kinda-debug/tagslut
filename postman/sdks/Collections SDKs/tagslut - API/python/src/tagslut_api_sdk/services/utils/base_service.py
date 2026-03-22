from typing import Any, Dict, Tuple, Generator, TYPE_CHECKING
from enum import Enum

from .default_headers import DefaultHeaders, DefaultHeadersKeys

from ...net.headers.base_header import BaseHeader

from ...net.transport.request import Request
from ...net.request_chain.request_chain import RequestChain
from ...net.request_chain.handlers.hook_handler import HookHandler
from ...net.request_chain.handlers.http_handler import HttpHandler
from ...net.headers.access_token_auth import AccessTokenAuth
from ...net.headers.basic_auth import BasicAuth
from ...net.request_chain.handlers.retry_handler import RetryHandler

if TYPE_CHECKING:
    from ...net.sdk_config import SdkConfig


class BaseService:
    """
    A base class for services providing common functionality.

    :ivar str base_url: The base URL for the service.
    :ivar dict _default_headers: A dictionary of default headers.
    """

    def __init__(self, base_url: str) -> None:
        """
        Initializes a BaseService instance.

        :param str base_url: The base URL for the service. Defaults to None.
        """
        self.base_url = base_url
        self._default_headers = DefaultHeaders()
        self._timeout = 60000
        self._service_config: "SdkConfig" = {}

        self._update_request_handler()

    def set_access_token(self, access_token: str):
        """
        Sets the access token for the service.
        """
        self._default_headers.set_header(
            DefaultHeadersKeys.ACCESS_AUTH, AccessTokenAuth(access_token)
        )

        return self

    def get_access_token(self, resolved_config: "SdkConfig" = None) -> BaseHeader:
        """
        Get the access auth header, with optional config overrides.

        :param SdkConfig resolved_config: Optional resolved configuration for overrides.
        :return: The access auth header.
        :rtype: BaseHeader
        """
        if resolved_config and (
            "token" in resolved_config or "access_token" in resolved_config
        ):
            token = resolved_config.get("token") or resolved_config.get("access_token")
            return AccessTokenAuth(token)
        return self._default_headers.get_header(DefaultHeadersKeys.ACCESS_AUTH)

    def set_basic_auth(self, username: str, password: str):
        """
        Sets the username and password for the service.
        """
        self._default_headers.set_header(
            DefaultHeadersKeys.BASIC_AUTH, BasicAuth(username, password)
        )

        return self

    def get_basic_auth(self, resolved_config: "SdkConfig" = None) -> BaseHeader:
        """
        Get the basic auth header, with optional config overrides.

        :param SdkConfig resolved_config: Optional resolved configuration for overrides.
        :return: The basic auth header.
        :rtype: BaseHeader
        """
        default_header = self._default_headers.get_header(DefaultHeadersKeys.BASIC_AUTH)

        if resolved_config and (
            "username" in resolved_config or "password" in resolved_config
        ):
            username = resolved_config.get(
                "username", getattr(default_header, "_username", None)
            )
            password = resolved_config.get(
                "password", getattr(default_header, "_password", None)
            )

            if username is not None and password is not None:
                return BasicAuth(username, password)

        return default_header

    def set_timeout(self, timeout: int):
        """
        Sets the timeout for the service.

        :param int timeout: The timeout (ms) to be set.
        :return: The service instance.
        """
        self._timeout = timeout
        self._update_request_handler()

        return self

    def set_base_url(self, base_url: str):
        """
        Sets the base URL for the service.

        :param str base_url: The base URL to be set.
        """
        self.base_url = base_url

        return self

    def set_config(self, config: "SdkConfig"):
        """
        Sets service-level configuration that applies to all methods in this service.

        :param SdkConfig config: Configuration dictionary to override SDK-level defaults.
        :return: The service instance for method chaining.
        """
        self._service_config = config
        return self

    def _get_resolved_config(
        self, method_config: "SdkConfig" = None, request_config: "SdkConfig" = None
    ) -> "SdkConfig":
        """
        Resolves configuration overrides from the hierarchy: request_config > method_config > service_config.
        Merges override configs into a single dictionary. SDK defaults are used as fallbacks where these overrides are not provided.

        :param SdkConfig method_config: Method-level configuration override.
        :param SdkConfig request_config: Request-level configuration override.
        :return: Merged configuration with all overrides applied.
        :rtype: SdkConfig
        """
        resolved: "SdkConfig" = {}

        # Apply service config
        if self._service_config:
            resolved.update(self._service_config)

        # Apply method config
        if method_config:
            resolved.update(method_config)

        # Apply request config
        if request_config:
            resolved.update(request_config)

        return resolved

    def send_request(self, request: Request) -> Tuple[Dict, int, str]:
        """
        Sends the given request.

        :param Request request: The request to be sent.
        :return: The response data.
        :rtype: Tuple[Dict, int, str]
        """
        response = self._request_handler.send(request)
        self._last_response = response
        return (
            response.body,
            response.status,
            response.headers.get("Content-Type", "").lower(),
        )

    def stream_request(self, request: Request) -> Generator[Dict, None, None]:
        """
        Streams the given request.

        :param Request request: The request to be streamed.
        :return: A generator of the response data.
        :rtype: Generator[Dict, None, None]
        """
        for response in self._request_handler.stream(request):
            yield (
                response.body,
                response.status,
                response.headers.get("Content-Type", "").lower(),
            )

    def get_default_headers(self) -> list:
        """
        Get the default headers.

        :return: A list of the default headers.
        :rtype: list
        """
        return self._default_headers.get_headers()

    def _get_request_handler(self) -> RequestChain:
        """
        Get the request chain.

        :return: The request chain.
        :rtype: RequestChain
        """
        return (
            RequestChain()
            .add_handler(HookHandler())
            .add_handler(RetryHandler())
            .add_handler(HttpHandler(self._timeout))
        )

    def _update_request_handler(self) -> None:
        """
        Update the request handler.
        """
        self._request_handler = self._get_request_handler()
