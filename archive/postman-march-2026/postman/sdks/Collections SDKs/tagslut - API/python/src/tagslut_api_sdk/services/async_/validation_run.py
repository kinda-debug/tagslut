from typing import Awaitable, Optional, Any, Union
from .utils.to_async import to_async
from ..validation_run import ValidationRunService
from ...net.sdk_config import SdkConfig
from ...models.utils.sentinel import SENTINEL


class ValidationRunServiceAsync(ValidationRunService):
    """
    Async Wrapper for ValidationRunServiceAsync
    """

    def v_6a_resolve_tidal_album_to_isrc(
        self,
        country_code: Union[str, None] = SENTINEL,
        *,
        request_config: Optional[SdkConfig] = None,
    ) -> Awaitable[Any]:
        return to_async(super().v_6a_resolve_tidal_album_to_isrc)(
            country_code, request_config=request_config
        )

    def v_6b_track_by_id_validation(
        self, beatport_test_track_id: str, *, request_config: Optional[SdkConfig] = None
    ) -> Awaitable[Any]:
        return to_async(super().v_6b_track_by_id_validation)(
            beatport_test_track_id, request_config=request_config
        )

    def v_6c_run_notes(
        self, *, request_config: Optional[SdkConfig] = None
    ) -> Awaitable[Any]:
        return to_async(super().v_6c_run_notes)(request_config=request_config)
