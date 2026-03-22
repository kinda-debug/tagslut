from __future__ import annotations
from typing import List
from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel
from .tracks_default_model import TracksDefaultModel


class TracksResponse(BaseModel):
    """Response model for the `tracks` endpoint.

    :param debug: debug, defaults to None
    :type debug: dict, optional
    :param explain: explain, defaults to None
    :type explain: dict, optional
    :param data: List of track models.
    :type data: List[TracksDefaultModel]
    """

    debug: Optional[dict] = Field(default=None)
    explain: Optional[dict] = Field(default=None)
    data: List[TracksDefaultModel] = Field(description="List of track models.")
