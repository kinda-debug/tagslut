from typing import Awaitable, Optional, Any, Union
from .utils.to_async import to_async
from ..identity_verification import IdentityVerificationService
from ...net.sdk_config import SdkConfig
from ...models.utils.sentinel import SENTINEL


class IdentityVerificationServiceAsync(IdentityVerificationService):
    """
    Async Wrapper for IdentityVerificationServiceAsync
    """

    def v_5a_beatport_isrc_lookup(
        self,
        isrc: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().v_5a_beatport_isrc_lookup)(
            isrc, request_config=request_config
        )

    def v_5b_tidal_isrc_cross_check(
        self,
        isrc: Union[str, None] = SENTINEL,
        country_code: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().v_5b_tidal_isrc_cross_check)(
            isrc, country_code, request_config=request_config
        )

    def v_5c_spotify_isrc_cross_check(
        self,
        q: Union[str, None] = SENTINEL,
        type_: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().v_5c_spotify_isrc_cross_check)(
            q, type_, request_config=request_config
        )
