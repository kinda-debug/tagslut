from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class GenreModel(BaseModel):
    """GenreModel

    :param genre_id: genre_id, defaults to None
    :type genre_id: int, optional
    :param genre_name: genre_name, defaults to None
    :type genre_name: str, optional
    """

    genre_id: Optional[int] = Field(default=None)
    genre_name: Optional[str] = Field(default=None)
