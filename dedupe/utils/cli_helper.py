import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional

# Attempt to import click, handle if missing
try:
    import click
except ImportError:
    print("Error: 'click' is required. Please install it via pip.", file=sys.stderr)
    sys.exit(1)

from dedupe.utils.logging import setup_logger
from dedupe.utils.config import get_config

def common_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to add common CLI options (verbose, config, etc)."""
    func = click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")(func)
    func = click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file")(func)
    return func

def configure_execution(verbose: bool, config_path: Optional[str] = None) -> None:
    """Sets up logging and config based on CLI args."""
    level = logging.DEBUG if verbose else logging.INFO
    setup_logger(level=level)
    
    if config_path:
        logging.info(f"Custom config path provided: {config_path}")
        get_config(Path(config_path))
