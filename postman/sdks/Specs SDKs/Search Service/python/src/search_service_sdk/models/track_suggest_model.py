from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class TrackSuggestModel(BaseModel):
    """TrackSuggestModel

    :param input: input
    :type input: str
    :param weight: weight, defaults to None
    :type weight: int, optional
    """

    input: str
    weight: Optional[int] = Field(default=None)
