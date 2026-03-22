from typing import Any, Optional
from .utils.validator import Validator
from .utils.base_service import BaseService
from ..net.transport.serializer import Serializer
from ..net.sdk_config import SdkConfig
from ..net.environment.environment import Environment
from ..models.utils.cast_models import cast_models
from ..models import HealthCheckResponse


class ServiceEndpointsService(BaseService):
    """
    Service class for ServiceEndpointsService operations.
    Provides methods to interact with ServiceEndpointsService-related API endpoints.
    Inherits common functionality from BaseService including authentication and request handling.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the service and method-level configurations."""
        super().__init__(*args, **kwargs)
        self._health_check_search_health_check_get_config: SdkConfig = {}

    def set_health_check_search_health_check_get_config(self, config: SdkConfig):
        """
        Sets method-level configuration for health_check_search_health_check_get.

        :param SdkConfig config: Configuration dictionary to override service-level defaults.
        :return: The service instance for method chaining.
        """
        self._health_check_search_health_check_get_config = config
        return self

    @cast_models
    def health_check_search_health_check_get(
        self, *, request_config: Optional[SdkConfig] = None
    ) -> HealthCheckResponse:
        """Endpoint used for health checking the service and the ES connectivity status.

        ...
        :raises RequestError: Raised when a request fails, with optional HTTP status code and details.
        ...
        :return: The parsed response data.
        :rtype: HealthCheckResponse
        """

        resolved_config = self._get_resolved_config(
            self._health_check_search_health_check_get_config, request_config
        )

        serialized_request = (
            Serializer(
                f"{resolved_config.get('base_url') or self.base_url or Environment.DEFAULT.url}/search/health-check",
                [],
                resolved_config,
            )
            .serialize()
            .set_method("GET")
        )

        response, _, _ = self.send_request(serialized_request)
        return HealthCheckResponse.model_validate(response)
