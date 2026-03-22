from __future__ import annotations
from typing import List
from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel
from .labels_default_model import LabelsDefaultModel


class LabelsResponse(BaseModel):
    """LabelsResponse

    :param debug: debug, defaults to None
    :type debug: dict, optional
    :param explain: explain, defaults to None
    :type explain: dict, optional
    :param data: List of label models.
    :type data: List[LabelsDefaultModel]
    """

    debug: Optional[dict] = Field(default=None)
    explain: Optional[dict] = Field(default=None)
    data: List[LabelsDefaultModel] = Field(description="List of label models.")
