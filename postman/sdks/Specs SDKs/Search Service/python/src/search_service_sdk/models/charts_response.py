from __future__ import annotations
from typing import List
from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel
from .charts_default_model import ChartsDefaultModel


class ChartsResponse(BaseModel):
    """ChartsResponse

    :param debug: debug, defaults to None
    :type debug: dict, optional
    :param explain: explain, defaults to None
    :type explain: dict, optional
    :param data: List of chart models.
    :type data: List[ChartsDefaultModel]
    """

    debug: Optional[dict] = Field(default=None)
    explain: Optional[dict] = Field(default=None)
    data: List[ChartsDefaultModel] = Field(description="List of chart models.")
