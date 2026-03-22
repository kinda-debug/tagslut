from typing import Union
from typing import List
from pydantic import Field
from typing import Optional
from typing import Annotated
from pydantic import TypeAdapter
from .utils.base_model import BaseModel

# Union type for Loc
# Pydantic will attempt to validate against each type in order
Loc = Union[str, int]
# TypeAdapter for runtime validation of Loc
# This allows validation of Union types which are not directly instantiable
from pydantic import TypeAdapter

Loc_adapter = TypeAdapter(Loc)


class ValidationError(BaseModel):
    """ValidationError

    :param loc: loc
    :type loc: List[Loc]
    :param msg: msg
    :type msg: str
    :param type_: type_
    :type type_: str
    """

    loc: List[Loc]
    msg: str
    type_: str = Field(alias="type", serialization_alias="type")
