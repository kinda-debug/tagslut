from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class TrackReleaseModel(BaseModel):
    """TrackReleaseModel

    :param release_id: release_id
    :type release_id: int
    :param release_name: release_name
    :type release_name: str
    :param release_image_uri: release_image_uri, defaults to None
    :type release_image_uri: str, optional
    :param release_image_dynamic_uri: release_image_dynamic_uri, defaults to None
    :type release_image_dynamic_uri: str, optional
    """

    release_id: int
    release_name: str
    release_image_uri: Optional[str] = Field(default=None)
    release_image_dynamic_uri: Optional[str] = Field(default=None)
