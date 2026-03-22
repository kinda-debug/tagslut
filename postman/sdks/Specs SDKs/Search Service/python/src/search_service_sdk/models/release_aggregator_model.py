from pydantic import Field
from typing import Optional
from .utils.base_model import BaseModel


class ReleaseAggregatorModel(BaseModel):
    """ReleaseAggregatorModel

    :param aggregator_id: aggregator_id
    :type aggregator_id: int
    :param aggregator_name: aggregator_name
    :type aggregator_name: str
    """

    aggregator_id: int
    aggregator_name: str
