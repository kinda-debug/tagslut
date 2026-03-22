from __future__ import annotations
from typing import List
from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel
from .genre_model import GenreModel


class ArtistsDefaultModel(BaseModel):
    """ArtistsDefaultModel

    :param score: score
    :type score: float
    :param enabled: enabled
    :type enabled: int
    :param update_date: update_date, defaults to None
    :type update_date: str, optional
    :param latest_publish_date: latest_publish_date, defaults to None
    :type latest_publish_date: str, optional
    :param available_worldwide: available_worldwide
    :type available_worldwide: int
    :param downloads: downloads, defaults to None
    :type downloads: int, optional
    :param artist_id: artist_id
    :type artist_id: int
    :param artist_name: artist_name
    :type artist_name: str
    :param genre: genre, defaults to None
    :type genre: List[GenreModel], optional
    :param artist_image_uri: artist_image_uri, defaults to None
    :type artist_image_uri: str, optional
    :param artist_image_dynamic_uri: artist_image_dynamic_uri, defaults to None
    :type artist_image_dynamic_uri: str, optional
    """

    score: float
    enabled: int
    update_date: Optional[str] = Field(default=None)
    latest_publish_date: Optional[str] = Field(default=None)
    available_worldwide: int
    downloads: Optional[int] = Field(default=None)
    artist_id: int
    artist_name: str
    genre: Optional[List[GenreModel]] = Field(default=None)
    artist_image_uri: Optional[str] = Field(default=None)
    artist_image_dynamic_uri: Optional[str] = Field(default=None)
