from pydantic import Field
from typing import Optional
from .utils.base_model import BaseModel


class TrackOrReleaseLabelModel(BaseModel):
    """TrackOrReleaseLabelModel

    :param enabled: enabled
    :type enabled: int
    :param label_id: label_id
    :type label_id: int
    :param label_name: label_name
    :type label_name: str
    """

    enabled: int
    label_id: int
    label_name: str
