from typing import Union
from .services.service_endpoints import ServiceEndpointsService
from .services.search_endpoints import SearchEndpointsService
from .net.environment import Environment


class SearchServiceSdk:
    """
    Main SDK client class for SearchServiceSdk.
    Provides centralized configuration and access to all service endpoints.
    Supports authentication, environment management, and global timeout settings.
    """

    def __init__(
        self,
        access_token: str = None,
        base_url: Union[Environment, str, None] = None,
        timeout: int = 60000,
    ):
        """
        Initializes SearchServiceSdk the SDK class.
        """

        self._base_url = (
            base_url.value if isinstance(base_url, Environment) else base_url
        )
        self.service_endpoints = ServiceEndpointsService(base_url=self._base_url)
        self.search_endpoints = SearchEndpointsService(base_url=self._base_url)
        self.set_access_token(access_token)
        self.set_timeout(timeout)

    def set_base_url(self, base_url: Union[Environment, str]):
        """
        Sets the base URL for the entire SDK.

        :param Union[Environment, str] base_url: The base URL to be set.
        :return: The SDK instance.
        """
        self._base_url = (
            base_url.value if isinstance(base_url, Environment) else base_url
        )

        self.service_endpoints.set_base_url(self._base_url)
        self.search_endpoints.set_base_url(self._base_url)

        return self

    def set_access_token(self, access_token: str):
        """
        Sets the access token for the entire SDK.
        """
        self.service_endpoints.set_access_token(access_token)
        self.search_endpoints.set_access_token(access_token)

        return self

    def set_timeout(self, timeout: int):
        """
        Sets the timeout for the entire SDK.

        :param int timeout: The timeout (ms) to be set.
        :return: The SDK instance.
        """
        self.service_endpoints.set_timeout(timeout)
        self.search_endpoints.set_timeout(timeout)

        return self


# c029837e0e474b76bc487506e8799df5e3335891efe4fb02bda7a1441840310c
