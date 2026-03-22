from __future__ import annotations
from typing import List
from pydantic import Field
from typing import Optional
from .utils.base_error import BaseError
from .utils.base_model import BaseModel
from .validation_error import ValidationError


# Pydantic validation model for HttpValidationError
class HttpValidationErrorData(BaseModel):
    """HttpValidationError

    :param detail: detail, defaults to None
    :type detail: List[ValidationError], optional
    """

    detail: Optional[List[ValidationError]] = Field(default=None)


# Error exception class
class HttpValidationError(BaseError):
    """HttpValidationError

    :param detail: detail, defaults to None
    :type detail: List[ValidationError], optional
    """

    _model_class = HttpValidationErrorData
