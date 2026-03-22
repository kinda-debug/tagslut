from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class ReleaseTrackModel(BaseModel):
    """ReleaseTrackModel

    :param track_id: track_id, defaults to None
    :type track_id: int, optional
    :param track_name: track_name, defaults to None
    :type track_name: str, optional
    """

    track_id: Optional[int] = Field(default=None)
    track_name: Optional[str] = Field(default=None)
