from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class SubGenreModel(BaseModel):
    """SubGenreModel

    :param sub_genre_id: sub_genre_id, defaults to None
    :type sub_genre_id: int, optional
    :param sub_genre_name: sub_genre_name, defaults to None
    :type sub_genre_name: str, optional
    """

    sub_genre_id: Optional[int] = Field(default=None)
    sub_genre_name: Optional[str] = Field(default=None)
