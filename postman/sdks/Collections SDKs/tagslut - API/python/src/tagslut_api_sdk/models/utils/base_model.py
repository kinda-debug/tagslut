from pydantic import BaseModel as PydanticBaseModel, ConfigDict, ValidationError
from typing import Any, Dict


class BaseModel(PydanticBaseModel):
    """
    Pydantic-based model for SDK objects with custom configuration.

    This class extends Pydantic's BaseModel to provide:
    - Automatic validation on instantiation
    - Type-safe attribute access
    - JSON serialization with API field name mapping
    - Support for additional properties (extra fields)
    """

    model_config = ConfigDict(
        # Allow extra fields beyond defined properties (replaces **kwargs behavior)
        extra="allow",
        # Validate field values when they are assigned after initialization
        validate_assignment=True,
        # Use enum values instead of enum objects in serialization
        use_enum_values=True,
        # Allow models to be populated using either field name or alias
        populate_by_name=True,
        # Arbitrary types allowed (for flexibility with custom types)
        arbitrary_types_allowed=False,
    )

    def model_dump_original(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Serialize model using original field names from OpenAPI spec.

        This ensures JSON output matches the API contract by using field aliases
        (typically camelCase) instead of Python field names (snake_case).

        By default, unset fields are excluded from the output.
        To include them, pass exclude_unset=False explicitly.

        :param kwargs: Additional arguments passed to model_dump()
        :return: Dictionary with original API field names
        :rtype: Dict[str, Any]

        Example:
            >>> cat = Cat(body_fat_percentage=15.5, age=None)
            >>> cat.model_dump_original()
            {'bodyFatPercentage': 15.5, 'age': None}
            >>> cat.model_dump_original(exclude_unset=False)
            {'bodyFatPercentage': 15.5, 'age': None}
        """
        # Set exclude_unset=True by default to exclude fields that were not explicitly set
        # Note: We do NOT exclude None values by default, because if a field is explicitly
        # set to None, it should be sent as null in the JSON to the API
        if "exclude_unset" not in kwargs:
            kwargs["exclude_unset"] = True

        # Exclude extra fields by default (additional properties not in schema)
        # This matches the expected behavior where undefined fields are not sent to APIs
        result = self.model_dump(by_alias=True, **kwargs)

        # Remove extra fields from the result
        extra_fields = getattr(self, "__pydantic_extra__", {})
        if extra_fields:
            for extra_field_name in extra_fields.keys():
                result.pop(extra_field_name, None)

        return result

    @classmethod
    def model_validate_original(cls, obj: Any) -> "BaseModel":
        """
        Parse and validate object using original field names from OpenAPI spec.

        This method accepts data with API field names (aliases) and creates
        a validated model instance.

        :param obj: Dictionary or object to validate
        :return: Validated model instance
        :rtype: BaseModel

        Example:
            >>> data = {'bodyFatPercentage': 15.5}
            >>> cat = Cat.model_validate_original(data)
            >>> cat.body_fat_percentage
            15.5
        """
        return cls.model_validate(obj)

    def _map(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Legacy alias for model_dump_original() for backward compatibility.

        :param kwargs: Additional arguments passed to model_dump_original()
        :return: Dictionary with original API field names
        :rtype: Dict[str, Any]
        """
        return self.model_dump_original(**kwargs)

    @classmethod
    def _unmap(cls, obj: Any) -> "BaseModel":
        """
        Legacy alias for model_validate_original() for backward compatibility.

        :param obj: Dictionary or object to validate
        :return: Validated model instance
        :rtype: BaseModel
        """
        return cls.model_validate_original(obj)

    @property
    def _kwargs(self) -> Dict[str, Any]:
        """
        Access extra fields (additional properties beyond defined schema).

        In Pydantic v2, extra fields are stored in __pydantic_extra__.
        This property provides backward compatibility with v1's **kwargs pattern.

        :return: Dictionary of extra fields
        :rtype: Dict[str, Any]
        """
        return getattr(self, "__pydantic_extra__", {})
