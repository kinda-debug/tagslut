from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class ReleaseKeyModel(BaseModel):
    """ReleaseKeyModel

    :param key_id: key_id, defaults to None
    :type key_id: int, optional
    :param key_name: key_name, defaults to None
    :type key_name: str, optional
    """

    key_id: Optional[int] = Field(default=None)
    key_name: Optional[str] = Field(default=None)
