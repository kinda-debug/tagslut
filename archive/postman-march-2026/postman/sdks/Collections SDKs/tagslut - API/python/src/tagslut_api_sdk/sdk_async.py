from typing import Union
from .net.environment import Environment
from .sdk import TagslutApiSdk
from .services.async_.auth import AuthServiceAsync
from .services.async_.catalog import CatalogServiceAsync
from .services.async_.search import SearchServiceAsync
from .services.async_.my_library import MyLibraryServiceAsync
from .services.async_.identity_verification import IdentityVerificationServiceAsync
from .services.async_.validation_run import ValidationRunServiceAsync


class TagslutApiSdkAsync(TagslutApiSdk):
    """
    TagslutApiSdkAsync is the asynchronous version of the TagslutApiSdk SDK Client.
    """

    def __init__(
        self,
        access_token: str = None,
        username: str = None,
        password: str = None,
        base_url: Union[Environment, str, None] = None,
        timeout: int = 60000,
    ):
        super().__init__(
            access_token=access_token,
            username=username,
            password=password,
            base_url=base_url,
            timeout=timeout,
        )

        self.auth = AuthServiceAsync(base_url=self._base_url)
        self.catalog = CatalogServiceAsync(base_url=self._base_url)
        self.search = SearchServiceAsync(base_url=self._base_url)
        self.my_library = MyLibraryServiceAsync(base_url=self._base_url)
        self.identity_verification = IdentityVerificationServiceAsync(
            base_url=self._base_url
        )
        self.validation_run = ValidationRunServiceAsync(base_url=self._base_url)
