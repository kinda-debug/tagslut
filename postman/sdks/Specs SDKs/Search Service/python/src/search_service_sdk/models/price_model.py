from pydantic import Field
from typing import Optional
from .utils.base_model import BaseModel


class PriceModel(BaseModel):
    """PriceModel

    :param code: code
    :type code: str
    :param symbol: symbol
    :type symbol: str
    :param value: value
    :type value: float
    :param display: display
    :type display: str
    """

    code: str
    symbol: str
    value: float
    display: str
