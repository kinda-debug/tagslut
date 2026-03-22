from __future__ import annotations
from typing import List
from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel
from .releases_default_model import ReleasesDefaultModel


class ReleasesResponse(BaseModel):
    """Response model for the `releases` endpoint.

    :param debug: debug, defaults to None
    :type debug: dict, optional
    :param explain: explain, defaults to None
    :type explain: dict, optional
    :param data: List of release models.
    :type data: List[ReleasesDefaultModel]
    """

    debug: Optional[dict] = Field(default=None)
    explain: Optional[dict] = Field(default=None)
    data: List[ReleasesDefaultModel] = Field(description="List of release models.")
