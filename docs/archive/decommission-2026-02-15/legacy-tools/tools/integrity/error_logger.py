"""Error logging with clean parsing and structured output.

Implements Item 4: Error logs parse cleanly - ensures all errors are
properly formatted, parseable, and don't break on unexpected input.
"""

import logging
import json
import traceback
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime


class ErrorLevel(Enum):
    """Standardized error severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ErrorRecord:
    """Structured error record for clean parsing."""
    timestamp: str
    level: str
    module: str
    function: str
    line_number: int
    message: str
    error_type: Optional[str] = None
    error_code: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    stack_trace: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def __str__(self) -> str:
        """Human-readable string representation."""
        context_str = f" | Context: {self.context}" if self.context else ""
        error_info = f" | {self.error_type}" if self.error_type else ""
        return f"[{self.timestamp}] {self.level} | {self.module}.{self.function}:{self.line_number} | {self.message}{error_info}{context_str}"


class CleanErrorFormatter(logging.Formatter):
    """Custom formatter that ensures error logs parse cleanly."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with guaranteed parseable structure."""
        try:
            # Extract safe fields
            timestamp = datetime.fromtimestamp(record.created).isoformat()
            module = record.module or "unknown"
            function = record.funcName or "<module>"
            line_num = record.lineno or 0
            level = record.levelname or "UNKNOWN"
            message = record.getMessage()
            
            # Safely extract exception info
            error_type = None
            stack_trace = None
            
            if record.exc_info and record.exc_info[0] is not None:
                exc_type, exc_value, exc_tb = record.exc_info
                error_type = exc_type.__name__
                stack_trace = "".join(traceback.format_exception(*record.exc_info))
            
            # Create structured record
            error_record = ErrorRecord(
                timestamp=timestamp,
                level=level,
                module=module,
                function=function,
                line_number=line_num,
                message=message,
                error_type=error_type,
                error_code=getattr(record, 'error_code', None),
                context=getattr(record, 'context', None),
                stack_trace=stack_trace
            )
            
            return str(error_record)
        
        except Exception as format_error:
            # Fallback formatter if custom formatting fails
            return f"[FORMATTING_ERROR] {record.getMessage()} | Original error: {str(format_error)}"


class CleanErrorLogger:
    """Logger that ensures error messages parse cleanly."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.error_records: List[ErrorRecord] = []
        self._setup_handler()
    
    def _setup_handler(self) -> None:
        """Setup clean formatter for all handlers."""
        formatter = CleanErrorFormatter()
        for handler in self.logger.handlers:
            handler.setFormatter(formatter)
    
    def log_error(self, level: ErrorLevel, message: str, 
                  error_type: Optional[str] = None,
                  error_code: Optional[str] = None,
                  context: Optional[Dict[str, Any]] = None,
                  exc_info: bool = False) -> ErrorRecord:
        """Log error with structured information."""
        import inspect
        frame = inspect.currentframe().f_back
        
        record = ErrorRecord(
            timestamp=datetime.now().isoformat(),
            level=level.value,
            module=frame.f_globals.get('__name__', 'unknown'),
            function=frame.f_code.co_name,
            line_number=frame.f_lineno,
            message=message,
            error_type=error_type,
            error_code=error_code,
            context=context,
            stack_trace=traceback.format_stack() if exc_info else None
        )
        
        self.error_records.append(record)
        
        # Log via standard logger
        log_func = getattr(self.logger, level.value.lower())
        log_func(message)
        
        return record
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of all logged errors."""
        by_type = {}
        by_level = {}
        
        for record in self.error_records:
            # Group by type
            error_type = record.error_type or "unknown"
            by_type[error_type] = by_type.get(error_type, 0) + 1
            
            # Group by level
            level = record.level
            by_level[level] = by_level.get(level, 0) + 1
        
        return {
            "total_errors": len(self.error_records),
            "by_type": by_type,
            "by_level": by_level
        }
    
    def export_errors(self) -> str:
        """Export all errors as JSON for analysis."""
        return json.dumps([r.to_dict() for r in self.error_records], indent=2)
    
    def validate_parsing(self) -> bool:
        """Validate that all error records parse cleanly."""
        for record in self.error_records:
            try:
                # Try converting to dict and back
                d = record.to_dict()
                json.dumps(d)  # Ensure JSON serializable
            except Exception:
                return False
        return True
