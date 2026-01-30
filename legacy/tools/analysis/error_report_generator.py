"""Generate CSV error reports from logs."""

import csv
import json
from typing import List, Dict, Optional
from pathlib import Path


class ErrorReportGenerator:
    """Generate error reports in CSV format."""
    
    @staticmethod
    def extract_errors_from_log(log_file: str) -> List[Dict]:
        """Extract errors from JSON log file."""
        errors = []
        try:
            with open(log_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        entry = json.loads(line)
                        ctx = entry.get('context', {})
                        if ctx.get('status') == 'error':
                            errors.append({
                                'line': line_num,
                                'timestamp': entry.get('timestamp'),
                                'file_path': ctx.get('file_path'),
                                'error_type': ctx.get('error_type'),
                                'error_message': ctx.get('error_message'),
                                'volume': ctx.get('volume'),
                            })
                    except json.JSONDecodeError:
                        pass
        except IOError as e:
            print(f"Failed to read log: {e}")
        return errors
    
    @staticmethod
    def write_csv_report(errors: List[Dict], output_file: str) -> None:
        """Write errors to CSV file."""
        if not errors:
            print("No errors to report.")
            return
        
        fieldnames = ['line', 'timestamp', 'file_path', 'error_type', 'error_message', 'volume']
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(errors)
        
        print(f"Report written to {output_file} ({len(errors)} errors)")
    
    @staticmethod
    def generate_report(log_file: str, output_file: str) -> None:
        """Generate complete error report."""
        errors = ErrorReportGenerator.extract_errors_from_log(log_file)
        ErrorReportGenerator.write_csv_report(errors, output_file)
