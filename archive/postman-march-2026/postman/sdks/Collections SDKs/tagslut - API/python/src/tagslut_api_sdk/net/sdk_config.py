from typing import TypedDict, Optional

from ..net.environment import Environment


class RetryConfig(TypedDict, total=False):
    """
    Configuration for retry behavior.

    :ivar int attempts: Maximum number of retry attempts.
    :ivar int delay_ms: Delay in milliseconds between retries.
    :ivar int max_delay_ms: Maximum delay in milliseconds between retries (caps exponential backoff).
    :ivar float backoff_factor: Multiplier for exponential backoff (e.g., 2.0 for doubling delay each retry).
    :ivar int jitter_ms: Maximum random jitter in milliseconds to add to retry delays.
    :ivar list[int] status_codes_to_retry: Specific HTTP status codes to retry (overrides default 5xx + 408, 429).
    :ivar list[str] http_methods_to_retry: HTTP methods to retry (e.g., ['GET', 'POST']).
    """

    attempts: int
    delay_ms: int
    max_delay_ms: int
    backoff_factor: float
    jitter_ms: int
    status_codes_to_retry: list[int]
    http_methods_to_retry: list[str]


class ValidationConfig(TypedDict, total=False):
    """
    Configuration for response validation.

    :ivar bool response_validation: Whether to validate responses against schemas.
    """

    response_validation: bool


class SdkConfig(TypedDict, total=False):
    """
    Configuration dictionary for SDK, service, method, and request-level overrides.

    Hierarchy (highest to lowest priority):
    - Request config (passed directly to method call)
    - Method config (set via set_<method_name>_config())
    - Service config (set via set_config())
    - SDK config (set at initialization)

    :ivar str base_url: Base URL for API requests. Can be a string URL or Environment enum.
    :ivar Environment environment: Environment enum value for base URL.
    :ivar int timeout: Request timeout in milliseconds.
    :ivar str token: Bearer token for authentication.
    :ivar str access_token: Access token for authentication (alias for token).
    :ivar str username: Username for basic authentication.
    :ivar str password: Password for basic authentication.
    :ivar RetryConfig retry: Retry configuration.
    :ivar ValidationConfig validation: Validation configuration.
    """

    base_url: str
    environment: Environment
    timeout: int
    token: str
    access_token: str
    username: str
    password: str
    retry: RetryConfig
    validation: ValidationConfig
