from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class CurrentStatusModel(BaseModel):
    """CurrentStatusModel

    :param current_status_id: current_status_id, defaults to None
    :type current_status_id: int, optional
    :param current_status_name: current_status_name, defaults to None
    :type current_status_name: str, optional
    """

    current_status_id: Optional[int] = Field(default=None)
    current_status_name: Optional[str] = Field(default=None)
