from tagslut.dj.curation import DjCurationConfig, calculate_dj_score


def test_calculate_dj_score_safe() -> None:
    config = DjCurationConfig()
    track = {
        "title": "Test Track (Remix)",
        "bpm": 124,
        "duration_sec": 360,
        "genre": "Tech House",
        "remixer": "trusted",
    }
    score = calculate_dj_score(track, config, {"trusted"})
    assert score.decision == "safe"


def test_calculate_dj_score_block() -> None:
    config = DjCurationConfig()
    track = {
        "title": "Symphony No. 1",
        "bpm": 70,
        "duration_sec": 90,
        "genre": "Classical",
    }
    score = calculate_dj_score(track, config, set())
    assert score.decision == "block"


def test_calculate_dj_score_review() -> None:
    config = DjCurationConfig()
    track = {
        "title": "Electronic Sketch",
        "bpm": 110,
        "duration_sec": 300,
        "genre": "Electronic",
    }
    score = calculate_dj_score(track, config, set())
    assert score.decision == "review"
