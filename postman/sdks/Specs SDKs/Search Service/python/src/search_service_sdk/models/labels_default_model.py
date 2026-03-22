from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class LabelsDefaultModel(BaseModel):
    """LabelsDefaultModel

    :param score: score
    :type score: float
    :param label_id: label_id
    :type label_id: int
    :param label_name: label_name
    :type label_name: str
    :param update_date: update_date
    :type update_date: str
    :param create_date: create_date
    :type create_date: str
    :param is_included_in_rightsflow: is_included_in_rightsflow
    :type is_included_in_rightsflow: int
    :param enabled: enabled
    :type enabled: int
    :param is_available_for_hype: is_available_for_hype
    :type is_available_for_hype: int
    :param is_available_for_streaming: is_available_for_streaming
    :type is_available_for_streaming: int
    :param plays: plays, defaults to None
    :type plays: int, optional
    :param downloads: downloads, defaults to None
    :type downloads: int, optional
    :param label_image_uri: label_image_uri, defaults to None
    :type label_image_uri: str, optional
    :param label_image_dynamic_uri: label_image_dynamic_uri, defaults to None
    :type label_image_dynamic_uri: str, optional
    """

    score: float
    label_id: int
    label_name: str
    update_date: str
    create_date: str
    is_included_in_rightsflow: int
    enabled: int
    is_available_for_hype: int
    is_available_for_streaming: int
    plays: Optional[int] = Field(default=None)
    downloads: Optional[int] = Field(default=None)
    label_image_uri: Optional[str] = Field(default=None)
    label_image_dynamic_uri: Optional[str] = Field(default=None)
