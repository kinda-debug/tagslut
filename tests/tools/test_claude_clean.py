from tools.review.claude_clean import parse_text


def test_starred_style_extraction_removes_ui() -> None:
    raw = (
        "New chat\n\n"
        "Search\n\n"
        "User question?\n\n"
        "10:13 AM\n\n"
        "Assistant response line 1.\n"
        "![favicon](https://example.com/favicon.png)\n"
        "Done\n"
    )
    output = parse_text(raw, "StarredClaude.md")
    assert "New chat" not in output
    assert "Search" not in output
    assert "![favicon]" not in output
    assert "Done" not in output
    assert "### User — 10:13 AM" in output
    assert "User question?" in output
    assert "Assistant response line 1." in output


def test_inline_timestamp_becomes_separator() -> None:
    raw = (
        "Lexicon DJ or Rekordbox for BPM? 2:07 PM Weighed feature parity between two platforms.\n"
        "\n"
        "Another question\n"
        "3:00 PM\n"
        "Assistant line.\n"
    )
    output = parse_text(raw, "claude2.md")
    assert "### User — 2:07 PM" in output
    assert "Lexicon DJ or Rekordbox for BPM?" in output
    assert "Weighed feature parity between two platforms." in output
    assert "### User — 3:00 PM" in output
    assert "Another question" in output
    assert "Assistant line." in output


def test_duplicate_lines_collapsed() -> None:
    raw = "USER_DUP\nUSER_DUP\n10:00 AM\nASSIST_DUP\nASSIST_DUP\n"
    output = parse_text(raw, "dup.md")
    assert output.count("USER_DUP") == 1
    assert output.count("ASSIST_DUP") == 1
