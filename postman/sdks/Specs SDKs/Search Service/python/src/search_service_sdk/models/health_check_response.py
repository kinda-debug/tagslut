from pydantic import Field
from typing import Optional
from .utils.base_model import BaseModel


class HealthCheckResponse(BaseModel):
    """Response model for the `health-check` endpoint.

    :param remote_addr: The origin of the request.
    :type remote_addr: str
    :param commit_hash: The current docker image used by the service.
    :type commit_hash: str
    :param service_es_connected: Bool that indicates if the service is connected to elasticsearch or not.
    :type service_es_connected: bool
    """

    remote_addr: str = Field(description="The origin of the request.")
    commit_hash: str = Field(
        description="The current docker image used by the service."
    )
    service_es_connected: bool = Field(
        description="Bool that indicates if the service is connected to elasticsearch or not."
    )
