from typing import Any, Optional, Union
from .utils.validator import Validator
from .utils.base_service import BaseService
from ..net.transport.serializer import Serializer
from ..net.sdk_config import SdkConfig
from ..net.environment.environment import Environment
from ..models.utils.sentinel import SENTINEL
from ..models.utils.cast_models import cast_models


class MyLibraryService(BaseService):
    """
    Service class for MyLibraryService operations.
    Provides methods to interact with MyLibraryService-related API endpoints.
    Inherits common functionality from BaseService including authentication and request handling.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the service and method-level configurations."""
        super().__init__(*args, **kwargs)
        self._my_beatport_tracks_config: SdkConfig = {
            "environment": Environment.BASE_URL_1
        }
        self._my_account_config: SdkConfig = {"environment": Environment.BASE_URL}

    def set_my_beatport_tracks_config(self, config: SdkConfig):
        """
        Sets method-level configuration for my_beatport_tracks.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._my_beatport_tracks_config = config
        return self

    def set_my_account_config(self, config: SdkConfig):
        """
        Sets method-level configuration for my_account.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._my_account_config = config
        return self

    @cast_models
    def my_beatport_tracks(
        self,
        page: Union[str, None] = SENTINEL,
        per_page: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """my_beatport_tracks

        :param page: page, defaults to None
        :type page: str, optional
        :param per_page: per_page, defaults to None
        :type per_page: str, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).is_optional().is_nullable().validate(page)
        Validator(str).is_optional().is_nullable().validate(per_page)

        resolved_config = self._get_resolved_config(
            self._my_beatport_tracks_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL_1.url or Environment.DEFAULT.url}/v4/my/beatport/tracks",
                [],
                resolved_config,
            )
            .add_query("page", page, nullable=True)
            .add_query("per_page", per_page, nullable=True)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response

    @cast_models
    def my_account(self, *, request_config: Optional[SdkConfig] = None) -> Any:
        """my_account

        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        resolved_config = self._get_resolved_config(
            self._my_account_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL.url or Environment.DEFAULT.url}/v4/my/account",
                [],
                resolved_config,
            )
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response
