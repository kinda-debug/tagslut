from __future__ import annotations
from tagslut.utils.console_ui import ConsoleUI

class SafetyGates:
    """
    A centralized class for handling safety checks, such as user confirmations.
    """

    def __init__(self, ui: ConsoleUI):
        self.ui = ui

    def confirm_destructive_operation(self, operation_name: str, required_phrase: str) -> bool:
        """
        Asks for user confirmation for a destructive operation.

        Args:
            operation_name: A description of the destructive operation (e.g., "file deletion").
            required_phrase: The exact phrase the user must type.

        Returns:
            True if the user confirms, False otherwise.
        """
        prompt = f"This operation involves {operation_name}. This is a destructive action."
        return self.ui.confirm(prompt, required_phrase)
