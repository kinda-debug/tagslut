"""Metadata type validation and schema enforcement."""

from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validate metadata types and coerce as needed."""

    # Known int/bytes problematic fields from mutagen
    MUTAGEN_PROBLEM_FIELDS = {
        'md5signature',
        'streaminfo_md5',
        'track_number',
        'disc_number',
        'date',
        'copyright',
    }

    @staticmethod
    def coerce_to_string(value: Any) -> str:
        """Coerce value to string, handling bytes/int cases."""
        if isinstance(value, str):
            return value
        elif isinstance(value, bytes):
            return value.hex()
        elif isinstance(value, (int, float)):
            return str(value)
        else:
            return str(value)

    @staticmethod
    def coerce_to_int(value: Any) -> int:
        """Coerce value to int."""
        if isinstance(value, int):
            return value
        elif isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Cannot coerce '{value}' to int")
                return 0
        else:
            return int(value)

    @staticmethod
    def validate_metadata_field(field_name: str, value: Any) -> Any:
        """Validate and coerce metadata field."""
        if value is None:
            return None

        if field_name in SchemaValidator.MUTAGEN_PROBLEM_FIELDS:
            if isinstance(value, bytes):
                return value.hex()
            elif isinstance(value, int):
                return str(value)

        return value

    @staticmethod
    def validate_record(record: Dict[str, Any]) -> Dict[str, Any]:
        """Validate entire record for type issues."""
        validated = {}
        for field, value in record.items():
            validated[field] = SchemaValidator.validate_metadata_field(field, value)
        return validated
