from __future__ import annotations
from typing import List
from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel
from .artists_default_model import ArtistsDefaultModel


class ArtistsResponse(BaseModel):
    """ArtistsResponse

    :param debug: debug, defaults to None
    :type debug: dict, optional
    :param explain: explain, defaults to None
    :type explain: dict, optional
    :param data: List of artist models.
    :type data: List[ArtistsDefaultModel]
    """

    debug: Optional[dict] = Field(default=None)
    explain: Optional[dict] = Field(default=None)
    data: List[ArtistsDefaultModel] = Field(description="List of artist models.")
