from __future__ import annotations
from typing import List
from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel
from .genre_model import GenreModel


class ChartsDefaultModel(BaseModel):
    """ChartsDefaultModel

    :param score: score
    :type score: float
    :param chart_id: chart_id
    :type chart_id: int
    :param chart_name: chart_name
    :type chart_name: str
    :param artist_id: artist_id, defaults to None
    :type artist_id: int, optional
    :param artist_name: artist_name, defaults to None
    :type artist_name: str, optional
    :param create_date: create_date
    :type create_date: str
    :param is_approved: is_approved
    :type is_approved: int
    :param update_date: update_date
    :type update_date: str
    :param enabled: enabled
    :type enabled: int
    :param is_indexed: is_indexed
    :type is_indexed: int
    :param person_id: person_id, defaults to None
    :type person_id: int, optional
    :param publish_date: publish_date, defaults to None
    :type publish_date: str, optional
    :param item_type_id: item_type_id, defaults to None
    :type item_type_id: int, optional
    :param person_username: person_username, defaults to None
    :type person_username: str, optional
    :param is_published: is_published
    :type is_published: int
    :param track_count: track_count, defaults to None
    :type track_count: int, optional
    :param chart_image_uri: chart_image_uri, defaults to None
    :type chart_image_uri: str, optional
    :param chart_image_dynamic_uri: chart_image_dynamic_uri, defaults to None
    :type chart_image_dynamic_uri: str, optional
    :param genres: genres, defaults to None
    :type genres: List[GenreModel], optional
    """

    score: float
    chart_id: int
    chart_name: str
    artist_id: Optional[int] = Field(default=None)
    artist_name: Optional[str] = Field(default=None)
    create_date: str
    is_approved: int
    update_date: str
    enabled: int
    is_indexed: int
    person_id: Optional[int] = Field(default=None)
    publish_date: Optional[str] = Field(default=None)
    item_type_id: Optional[int] = Field(default=None)
    person_username: Optional[str] = Field(default=None)
    is_published: int
    track_count: Optional[int] = Field(default=None)
    chart_image_uri: Optional[str] = Field(default=None)
    chart_image_dynamic_uri: Optional[str] = Field(default=None)
    genres: Optional[List[GenreModel]] = Field(default=None)
