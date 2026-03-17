from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Optional, Sequence

from tagslut.metadata.models.types import ProviderTrack


_MIX_PAREN_SUFFIX_RE = re.compile(r"^(?P<title>.+?)\s*\((?P<mix>[^()]+)\)\s*$")

_NEUTRAL_MIX_NAMES = {
    "original mix",
    "main mix",
    "original",
    "main",
}


def _norm_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    if not text:
        return ""
    # Keep alnum only, collapse whitespace.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _primary_artist(artist: str | None) -> str:
    value = (artist or "").strip()
    if not value:
        return ""
    # Beatport rows are usually "A, B" (extract script uses join with ", ").
    # Keep first as primary for strict matching.
    first = value.split(",")[0].strip()
    # Also handle "A & B" / "A feat. B" best-effort without fuzzy behavior.
    for sep in (" feat. ", " ft. ", " featuring ", " & ", " x "):
        if sep in first.lower():
            first = first.lower().split(sep, 1)[0].strip()
            break
    return _norm_text(first)


def split_title_and_mix(title: str | None) -> tuple[str, str]:
    """Return (core_title, mix_name) where mix_name may be empty."""
    raw = (title or "").strip()
    if not raw:
        return "", ""
    match = _MIX_PAREN_SUFFIX_RE.match(raw)
    if not match:
        return raw, ""
    core = (match.group("title") or "").strip()
    mix = (match.group("mix") or "").strip()
    return core or raw, mix


def _norm_mix_name(value: str | None) -> str:
    return _norm_text(value)


def _is_neutral_mix(mix_name: str | None) -> bool:
    norm = _norm_mix_name(mix_name)
    return bool(norm) and norm in _NEUTRAL_MIX_NAMES


def _duration_diff_ms(a_ms: int | None, b_ms: int | None) -> int | None:
    if a_ms is None or b_ms is None:
        return None
    return abs(int(a_ms) - int(b_ms))


def tidal_audio_quality_rank(audio_quality: str | None) -> int:
    """Higher is better. Unknown defaults to 0 (treat as not better than Beatport)."""
    value = (audio_quality or "").strip().upper()
    if not value:
        return 0
    # TIDAL mediaTags mapping in provider: HIRES_LOSSLESS, LOSSLESS, etc.
    if "HIRES_LOSSLESS" in value:
        return 3
    if "LOSSLESS" in value:
        return 2
    # Treat everything else (including DOLBY_ATMOS, SONY_360RA, AAC) as not-better for downloads.
    return 1


def beatport_quality_rank() -> int:
    # For this tool's policy: Beatport is treated as lossless-oriented baseline.
    return 1


@dataclass(frozen=True)
class VerifiedTidalMatch:
    tidal_track: ProviderTrack
    match_method: str  # "isrc" | "title_artist_mix_duration"
    duration_diff_ms: int | None
    verified: bool
    reason: str


@dataclass(frozen=True)
class SourceSelectionDecision:
    attempted: bool
    winner: str  # "beatport" | "tidal"
    winner_reason: str
    tidal_match: VerifiedTidalMatch | None
    ambiguous: bool

    def selected_download_url(self, *, beatport_track_id: str) -> str:
        if self.winner == "tidal" and self.tidal_match is not None:
            if self.tidal_match.tidal_track.url:
                return self.tidal_match.tidal_track.url
            return f"https://tidal.com/browse/track/{self.tidal_match.tidal_track.service_track_id}"
        return f"https://www.beatport.com/track/-/{beatport_track_id}"


def _candidate_passes_isrc(
    *,
    beatport_isrc: str,
    tidal_track: ProviderTrack,
    beatport_duration_ms: int | None,
    duration_tolerance_ms: int,
) -> tuple[bool, int | None, str]:
    tidal_isrc = (tidal_track.isrc or "").strip().upper()
    if not tidal_isrc or tidal_isrc != beatport_isrc.strip().upper():
        return False, None, "isrc_mismatch"

    diff = _duration_diff_ms(beatport_duration_ms, tidal_track.duration_ms)
    if diff is not None and diff > duration_tolerance_ms:
        return False, diff, "duration_out_of_tolerance_for_isrc"
    return True, diff, "verified_isrc"


def _candidate_passes_strict_text_identity(
    *,
    beatport_title: str,
    beatport_artist: str,
    beatport_duration_ms: int | None,
    tidal_track: ProviderTrack,
    duration_tolerance_ms: int,
) -> tuple[bool, int | None, str]:
    bp_core, bp_mix = split_title_and_mix(beatport_title)
    td_title = (tidal_track.title or "").strip()
    td_core, td_mix = split_title_and_mix(td_title)

    if _norm_text(bp_core) != _norm_text(td_core):
        return False, None, "title_mismatch"

    if _primary_artist(beatport_artist) != _primary_artist(tidal_track.artist or ""):
        return False, None, "primary_artist_mismatch"

    bp_mix_norm = _norm_mix_name(bp_mix)
    td_mix_norm = _norm_mix_name(td_mix)

    # If Beatport mix is explicitly non-neutral, require exact mix match.
    if bp_mix_norm and not _is_neutral_mix(bp_mix):
        if bp_mix_norm != td_mix_norm:
            return False, None, "mix_mismatch"
    # If Beatport mix is neutral (or absent), block TIDAL having a non-neutral mix.
    # This prevents "Extended Mix" replacing "Original Mix".
    else:
        if td_mix_norm and not _is_neutral_mix(td_mix):
            return False, None, "tidal_non_neutral_mix_blocks_neutral_beatport"

    diff = _duration_diff_ms(beatport_duration_ms, tidal_track.duration_ms)
    if diff is None:
        return False, None, "duration_missing_blocks_text_verification"
    if diff > duration_tolerance_ms:
        return False, diff, "duration_out_of_tolerance"
    return True, diff, "verified_title_artist_mix_duration"


def _choose_deterministic_best_candidate(
    *,
    verified: Sequence[VerifiedTidalMatch],
    beatport_album: str | None,
) -> tuple[VerifiedTidalMatch | None, bool]:
    if not verified:
        return None, False
    if len(verified) == 1:
        return verified[0], False

    beatport_album_norm = _norm_text(beatport_album)

    def _album_match_score(track: ProviderTrack) -> int:
        if not beatport_album_norm:
            return 0
        return 1 if _norm_text(track.album) == beatport_album_norm else 0

    # Higher is better; final tie-break is stable on numeric track id (lowest wins).
    ordered = sorted(
        verified,
        key=lambda m: (
            -tidal_audio_quality_rank(m.tidal_track.audio_quality),
            m.duration_diff_ms is None,
            m.duration_diff_ms if m.duration_diff_ms is not None else 10**9,
            -_album_match_score(m.tidal_track),
            int(m.tidal_track.service_track_id) if str(m.tidal_track.service_track_id).isdigit() else 10**12,
        ),
    )

    best = ordered[0]
    runner_up = ordered[1]

    best_key = (
        tidal_audio_quality_rank(best.tidal_track.audio_quality),
        best.duration_diff_ms,
        _album_match_score(best.tidal_track),
    )
    runner_key = (
        tidal_audio_quality_rank(runner_up.tidal_track.audio_quality),
        runner_up.duration_diff_ms,
        _album_match_score(runner_up.tidal_track),
    )

    if best_key == runner_key:
        return None, True
    return best, False


def select_download_source_for_beatport_track(
    *,
    beatport_track_id: str,
    beatport_isrc: str | None,
    beatport_title: str,
    beatport_artist: str,
    beatport_album: str | None,
    beatport_duration_ms: int | None,
    tidal_candidates: Iterable[ProviderTrack],
    duration_tolerance_ms: int = 2000,
) -> SourceSelectionDecision:
    candidates = [c for c in tidal_candidates if isinstance(c, ProviderTrack)]
    if not candidates:
        return SourceSelectionDecision(
            attempted=True,
            winner="beatport",
            winner_reason="no_tidal_candidates",
            tidal_match=None,
            ambiguous=False,
        )

    verified: list[VerifiedTidalMatch] = []
    bp_isrc = (beatport_isrc or "").strip()
    if bp_isrc:
        for track in candidates:
            ok, diff, reason = _candidate_passes_isrc(
                beatport_isrc=bp_isrc,
                tidal_track=track,
                beatport_duration_ms=beatport_duration_ms,
                duration_tolerance_ms=duration_tolerance_ms,
            )
            if ok:
                verified.append(
                    VerifiedTidalMatch(
                        tidal_track=track,
                        match_method="isrc",
                        duration_diff_ms=diff,
                        verified=True,
                        reason=reason,
                    )
                )
    else:
        for track in candidates:
            ok, diff, reason = _candidate_passes_strict_text_identity(
                beatport_title=beatport_title,
                beatport_artist=beatport_artist,
                beatport_duration_ms=beatport_duration_ms,
                tidal_track=track,
                duration_tolerance_ms=duration_tolerance_ms,
            )
            if ok:
                verified.append(
                    VerifiedTidalMatch(
                        tidal_track=track,
                        match_method="title_artist_mix_duration",
                        duration_diff_ms=diff,
                        verified=True,
                        reason=reason,
                    )
                )

    if not verified:
        return SourceSelectionDecision(
            attempted=True,
            winner="beatport",
            winner_reason="tidal_unverified",
            tidal_match=None,
            ambiguous=False,
        )

    best, ambiguous = _choose_deterministic_best_candidate(
        verified=verified,
        beatport_album=beatport_album,
    )
    if ambiguous or best is None:
        return SourceSelectionDecision(
            attempted=True,
            winner="beatport",
            winner_reason="tidal_ambiguous_verified_candidates",
            tidal_match=None,
            ambiguous=True,
        )

    td_rank = tidal_audio_quality_rank(best.tidal_track.audio_quality)
    bp_rank = beatport_quality_rank()
    if td_rank <= bp_rank:
        return SourceSelectionDecision(
            attempted=True,
            winner="beatport",
            winner_reason="tidal_not_better_quality",
            tidal_match=best,
            ambiguous=False,
        )

    quality_label = (
        "tidal_verified_hires"
        if td_rank >= 3
        else ("tidal_verified_lossless" if td_rank == 2 else "tidal_verified_other")
    )
    return SourceSelectionDecision(
        attempted=True,
        winner="tidal",
        winner_reason=quality_label,
        tidal_match=best,
        ambiguous=False,
    )

