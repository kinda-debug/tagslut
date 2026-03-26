from typing import Awaitable, Optional, Any
from .utils.to_async import to_async
from ..auth import AuthService
from ...net.sdk_config import SdkConfig
from ...models import GetTokenClientCredentialsRequest


class AuthServiceAsync(AuthService):
    """
    Async Wrapper for AuthServiceAsync
    """

    def get_token_client_credentials(
        self,
        request_body: GetTokenClientCredentialsRequest,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().get_token_client_credentials)(
            request_body, request_config=request_config
        )

    def introspect_token(
        self, *, request_config: Optional[SdkConfig] = None
    ) -> Awaitable[Any]:
        return to_async(super().introspect_token)(request_config=request_config)
