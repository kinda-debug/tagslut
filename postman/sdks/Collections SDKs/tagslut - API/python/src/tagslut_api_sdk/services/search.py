from typing import Any, Optional, Union
from .utils.validator import Validator
from .utils.base_service import BaseService
from ..net.transport.serializer import Serializer
from ..net.sdk_config import SdkConfig
from ..net.environment.environment import Environment
from ..models.utils.sentinel import SENTINEL
from ..models.utils.cast_models import cast_models


class SearchService(BaseService):
    """
    Service class for SearchService operations.
    Provides methods to interact with SearchService-related API endpoints.
    Inherits common functionality from BaseService including authentication and request handling.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the service and method-level configurations."""
        super().__init__(*args, **kwargs)
        self._search_tracks_by_text_config: SdkConfig = {
            "environment": Environment.BASE_URL_1
        }

    def set_search_tracks_by_text_config(self, config: SdkConfig):
        """
        Sets method-level configuration for search_tracks_by_text.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._search_tracks_by_text_config = config
        return self

    @cast_models
    def search_tracks_by_text(
        self,
        q: Union[str, None] = SENTINEL,
        count: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Any:
        """search_tracks_by_text

        :param q: q, defaults to None
        :type q: str, optional
        :param count: count, defaults to None
        :type count: str, optional
        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: Any
        """

        Validator(str).is_optional().is_nullable().validate(q)
        Validator(str).is_optional().is_nullable().validate(count)

        resolved_config = self._get_resolved_config(
            self._search_tracks_by_text_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.BASE_URL_1.url or Environment.DEFAULT.url}/search/v1/tracks",
                [],
                resolved_config,
            )
            .add_query("q", q, nullable=True)
            .add_query("count", count, nullable=True)
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return response
