"""Type checking utilities with mypy integration.

Implements Item 5: All mypy errors resolved - provides tools for checking
and validating type hints across the codebase.
"""

import subprocess
import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from enum import Enum
import tempfile
import logging

logger = logging.getLogger(__name__)


class MypySeverity(Enum):
    """Mypy error severity levels."""
    ERROR = "error"
    NOTE = "note"
    WARNING = "warning"


@dataclass
class MypyError:
    """Represents a mypy type checking error."""
    file_path: str
    line_number: int
    column: int
    severity: str
    message: str
    error_code: Optional[str] = None
    
    def __str__(self) -> str:
        code_str = f" [{self.error_code}]" if self.error_code else ""
        return f"{self.file_path}:{self.line_number}:{self.column}: {self.severity}: {self.message}{code_str}"


class MypyChecker:
    """Run mypy checks and collect results."""
    
    def __init__(self, python_version: str = "3.10"):
        self.python_version = python_version
        self.errors: List[MypyError] = []
        self.warnings: List[MypyError] = []
        self.notes: List[MypyError] = []
    
    def run_check(self, target_path: str, strict_mode: bool = False, 
                  ignore_missing_imports: bool = True) -> Tuple[bool, List[MypyError]]:
        """Run mypy on target path and collect errors.
        
        Args:
            target_path: Path to file or directory to check
            strict_mode: Whether to use mypy strict mode
            ignore_missing_imports: Whether to ignore missing imports
        
        Returns:
            Tuple of (success, errors)
        """
        cmd = ["mypy", target_path, f"--python-version={self.python_version}"]
        
        if strict_mode:
            cmd.append("--strict")
        
        if ignore_missing_imports:
            cmd.append("--ignore-missing-imports")
        
        cmd.extend(["--show-error-codes", "--show-column-numbers"])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            self._parse_output(result.stdout, result.stderr)
            
            # Success if only notes or warnings, error if any errors
            success = len(self.errors) == 0
            
            all_issues = self.errors + self.warnings + self.notes
            return success, all_issues
        
        except subprocess.TimeoutExpired:
            logger.error(f"Mypy check timed out for {target_path}")
            return False, []
        except FileNotFoundError:
            logger.error("mypy not found. Install with: pip install mypy")
            return False, []
    
    def _parse_output(self, stdout: str, stderr: str) -> None:
        """Parse mypy output and extract errors."""
        output = stdout + stderr
        
        for line in output.splitlines():
            if not line.strip():
                continue
            
            # Parse line format: path/file.py:line:col: severity: message [code]
            parts = line.split(":")
            if len(parts) < 4:
                continue
            
            try:
                file_path = parts[0]
                line_num = int(parts[1])
                column = int(parts[2])
                
                # Parse severity and message
                rest = ":".join(parts[3:]).strip()
                
                severity = "error"
                if " error: " in rest:
                    severity = "error"
                    message_part = rest.split(" error: ", 1)[1]
                elif " warning: " in rest:
                    severity = "warning"
                    message_part = rest.split(" warning: ", 1)[1]
                elif " note: " in rest:
                    severity = "note"
                    message_part = rest.split(" note: ", 1)[1]
                else:
                    message_part = rest
                
                # Extract error code if present
                error_code = None
                if "[" in message_part and "]" in message_part:
                    start = message_part.rfind("[")
                    end = message_part.rfind("]")
                    if start < end:
                        error_code = message_part[start+1:end]
                        message_part = message_part[:start].strip()
                
                error = MypyError(
                    file_path=file_path,
                    line_number=line_num,
                    column=column,
                    severity=severity,
                    message=message_part,
                    error_code=error_code
                )
                
                if severity == "error":
                    self.errors.append(error)
                elif severity == "warning":
                    self.warnings.append(error)
                else:
                    self.notes.append(error)
            
            except (ValueError, IndexError) as e:
                logger.debug(f"Could not parse mypy line: {line} ({e})")
                continue
    
    def get_summary(self) -> Dict[str, int]:
        """Get summary of type checking results."""
        return {
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "notes": len(self.notes),
            "total_issues": len(self.errors) + len(self.warnings) + len(self.notes)
        }
    
    def validate_all_typed(self) -> bool:
        """Validate that there are zero errors."""
        return len(self.errors) == 0


class TypeHintEnforcer:
    """Enforce type hints across modules."""
    
    def __init__(self):
        self.untyped_functions: List[str] = []
        self.partially_typed: List[str] = []
    
    def check_file(self, file_path: str) -> Dict[str, int]:
        """Check type hint coverage in a file."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Simple heuristic: look for 'def ' without type hints
            # This is a basic check - production code should use AST analysis
            untyped_count = 0
            total_funcs = 0
            
            import ast
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        total_funcs += 1
                        # Check if function has return annotation and all params are typed
                        has_return = node.returns is not None
                        all_args_typed = all(
                            arg.annotation is not None 
                            for arg in node.args.args
                        )
                        
                        if not (has_return and all_args_typed):
                            untyped_count += 1
            except SyntaxError:
                logger.warning(f"Could not parse {file_path}")
            
            return {
                "total_functions": total_funcs,
                "typed_functions": total_funcs - untyped_count,
                "coverage_percent": int((total_funcs - untyped_count) / total_funcs * 100) if total_funcs > 0 else 0
            }
        
        except Exception as e:
            logger.error(f"Error checking {file_path}: {e}")
            return {}
