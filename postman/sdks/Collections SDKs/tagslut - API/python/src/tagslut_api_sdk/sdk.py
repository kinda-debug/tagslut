from typing import Union
from .services.auth import AuthService
from .services.catalog import CatalogService
from .services.search import SearchService
from .services.my_library import MyLibraryService
from .services.identity_verification import IdentityVerificationService
from .services.validation_run import ValidationRunService
from .net.environment import Environment


class TagslutApiSdk:
    """
    Main SDK client class for TagslutApiSdk.
    Provides centralized configuration and access to all service endpoints.
    Supports authentication, environment management, and global timeout settings.
    """

    def __init__(
        self,
        access_token: str = None,
        username: str = None,
        password: str = None,
        base_url: Union[Environment, str, None] = None,
        timeout: int = 60000,
    ):
        """
        Initializes TagslutApiSdk the SDK class.
        """

        self._base_url = (
            base_url.value if isinstance(base_url, Environment) else base_url
        )
        self.auth = AuthService(base_url=self._base_url)
        self.catalog = CatalogService(base_url=self._base_url)
        self.search = SearchService(base_url=self._base_url)
        self.my_library = MyLibraryService(base_url=self._base_url)
        self.identity_verification = IdentityVerificationService(
            base_url=self._base_url
        )
        self.validation_run = ValidationRunService(base_url=self._base_url)
        self.set_access_token(access_token)
        self.set_basic_auth(username=username, password=password)
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

        self.auth.set_base_url(self._base_url)
        self.catalog.set_base_url(self._base_url)
        self.search.set_base_url(self._base_url)
        self.my_library.set_base_url(self._base_url)
        self.identity_verification.set_base_url(self._base_url)
        self.validation_run.set_base_url(self._base_url)

        return self

    def set_access_token(self, access_token: str):
        """
        Sets the access token for the entire SDK.
        """
        self.auth.set_access_token(access_token)
        self.catalog.set_access_token(access_token)
        self.search.set_access_token(access_token)
        self.my_library.set_access_token(access_token)
        self.identity_verification.set_access_token(access_token)
        self.validation_run.set_access_token(access_token)

        return self

    def set_basic_auth(self, username: str, password: str):
        """
        Sets the username and password for the entire SDK.
        """
        self.auth.set_basic_auth(username=username, password=password)
        self.catalog.set_basic_auth(username=username, password=password)
        self.search.set_basic_auth(username=username, password=password)
        self.my_library.set_basic_auth(username=username, password=password)
        self.identity_verification.set_basic_auth(username=username, password=password)
        self.validation_run.set_basic_auth(username=username, password=password)

        return self

    def set_timeout(self, timeout: int):
        """
        Sets the timeout for the entire SDK.

        :param int timeout: The timeout (ms) to be set.
        :return: The SDK instance.
        """
        self.auth.set_timeout(timeout)
        self.catalog.set_timeout(timeout)
        self.search.set_timeout(timeout)
        self.my_library.set_timeout(timeout)
        self.identity_verification.set_timeout(timeout)
        self.validation_run.set_timeout(timeout)

        return self


# c029837e0e474b76bc487506e8799df5e3335891efe4fb02bda7a1441840310c
