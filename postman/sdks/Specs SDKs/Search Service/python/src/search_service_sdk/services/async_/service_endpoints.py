from typing import Awaitable, Optional
from .utils.to_async import to_async
from ..service_endpoints import ServiceEndpointsService
from ...net.sdk_config import SdkConfig
from ...models import HealthCheckResponse


class ServiceEndpointsServiceAsync(ServiceEndpointsService):
    """
    Async Wrapper for ServiceEndpointsServiceAsync
    """

    def health_check_search_health_check_get(
        self, *, request_config: Optional[SdkConfig] = None
    ) -> Awaitable[HealthCheckResponse]:
        return to_async(super().health_check_search_health_check_get)(
            request_config=request_config
        )
