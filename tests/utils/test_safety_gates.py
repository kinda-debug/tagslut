from tagslut.utils.safety_gates import SafetyGates


class StubUI:
    def __init__(self, response: bool) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def confirm(self, prompt: str, required_phrase: str) -> bool:
        self.calls.append((prompt, required_phrase))
        return self.response


def test_confirm_destructive_operation_returns_true_on_confirmation() -> None:
    ui = StubUI(response=True)
    gates = SafetyGates(ui)  # type: ignore[arg-type]

    ok = gates.confirm_destructive_operation("file deletion", "TYPE THIS")

    assert ok is True
    assert len(ui.calls) == 1
    assert "file deletion" in ui.calls[0][0]
    assert ui.calls[0][1] == "TYPE THIS"


def test_confirm_destructive_operation_returns_false_on_rejection() -> None:
    ui = StubUI(response=False)
    gates = SafetyGates(ui)  # type: ignore[arg-type]

    ok = gates.confirm_destructive_operation("quarantine purge", "CONFIRM")

    assert ok is False


def test_confirm_destructive_operation_uses_exact_required_phrase() -> None:
    ui = StubUI(response=True)
    gates = SafetyGates(ui)  # type: ignore[arg-type]

    gates.confirm_destructive_operation("move", "I understand this is a move operation.")

    assert ui.calls[0][1] == "I understand this is a move operation."
