"""
An enum class containing all the possible environments for the SDK
"""

from enum import Enum
from urllib.parse import urlparse


class Environment(Enum):
    """The environments available for the SDK"""

    DEFAULT = "https://{{base_url}}"
    BASE_URL = "https://{{base_url}}"
    BASE_URL_1 = "://{{base_url}}"
    API = "https://api.tidal.com"
    API_1 = "https://api.spotify.com"
    EXAMPLE = "https://example.com"

    def __new__(cls, url):
        parsed_url = urlparse(url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            raise ValueError(
                f"Environment url [{url}] is not valid. Please use the following format https://api.example.com"
            )

        obj = object.__new__(cls)
        obj._value_ = url
        obj._url = url
        return obj

    @property
    def url(self):
        """Get the base URL for this environment"""
        return self._url
