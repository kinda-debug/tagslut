from typing import Union
from .net.environment import Environment
from .sdk import SearchServiceSdk
from .services.async_.service_endpoints import ServiceEndpointsServiceAsync
from .services.async_.search_endpoints import SearchEndpointsServiceAsync


class SearchServiceSdkAsync(SearchServiceSdk):
    """
    SearchServiceSdkAsync is the asynchronous version of the SearchServiceSdk SDK Client.
    """

    def __init__(
        self,
        access_token: str = None,
        base_url: Union[Environment, str, None] = None,
        timeout: int = 60000,
    ):
        super().__init__(access_token=access_token, base_url=base_url, timeout=timeout)

        self.service_endpoints = ServiceEndpointsServiceAsync(base_url=self._base_url)
        self.search_endpoints = SearchEndpointsServiceAsync(base_url=self._base_url)
