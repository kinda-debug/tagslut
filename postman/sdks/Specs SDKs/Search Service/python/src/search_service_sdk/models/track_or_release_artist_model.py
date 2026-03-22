from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class TrackOrReleaseArtistModel(BaseModel):
    """TrackOrReleaseArtistModel

    :param artist_id: artist_id, defaults to None
    :type artist_id: int, optional
    :param artist_name: artist_name, defaults to None
    :type artist_name: str, optional
    :param artist_type_name: artist_type_name, defaults to None
    :type artist_type_name: str, optional
    """

    artist_id: Optional[int] = Field(default=None)
    artist_name: Optional[str] = Field(default=None)
    artist_type_name: Optional[str] = Field(default=None)
