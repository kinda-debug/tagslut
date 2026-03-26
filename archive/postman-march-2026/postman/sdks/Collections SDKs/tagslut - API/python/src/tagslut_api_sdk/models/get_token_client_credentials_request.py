from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel


class GetTokenClientCredentialsRequest(BaseModel):
    """GetTokenClientCredentialsRequest

    :param grant_type: grant_type, defaults to None
    :type grant_type: str, optional
    :param client_id: client_id, defaults to None
    :type client_id: str, optional
    :param client_secret: client_secret, defaults to None
    :type client_secret: str, optional
    """

    grant_type: Optional[str] = Field(default=None)
    client_id: Optional[str] = Field(default=None)
    client_secret: Optional[str] = Field(default=None)
