from __future__ import annotations
import sys

class ConsoleUI:
    """
    A centralized class for handling all console output and user interaction.
    """

    def __init__(self, quiet: bool = False):
        self.quiet = quiet

    def print(self, message: str):
        """Prints a standard message to stdout."""
        if not self.quiet:
            print(message)

    def warning(self, message: str):
        """Prints a warning message to stderr."""
        print(f"WARNING: {message}", file=sys.stderr)

    def error(self, message: str, exit_code: int | None = None):
        """Prints an error message to stderr and optionally exits."""
        print(f"ERROR: {message}", file=sys.stderr)
        if exit_code is not None:
            sys.exit(exit_code)

    def confirm(self, prompt: str, required_phrase: str) -> bool:
        """
        Requires the user to type a specific phrase to confirm an action.

        Args:
            prompt: The warning message to display to the user.
            required_phrase: The exact phrase the user must type.

        Returns:
            True if the user confirms, False otherwise.
        """
        self.warning(prompt)
        print(f"To confirm, you must type the following phrase exactly: '{required_phrase}'")
        response = input("> ").strip()
        return response == required_phrase

