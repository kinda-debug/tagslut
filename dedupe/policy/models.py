"""Policy model types used by the v3 decide engine."""

from __future__ import annotations

from dataclasses import dataclass

ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "archive",
        "keep",
        "promote",
        "quarantine",
        "replace",
        "review",
        "skip",
        "stash",
    }
)

ALLOWED_COLLISION_POLICIES: frozenset[str] = frozenset({"abort", "replace", "skip"})
ALLOWED_MATCH_KINDS: frozenset[str] = frozenset(
    {"artist_title_duration", "beatport_id", "isrc"}
)


@dataclass(frozen=True)
class MatchRules:
    """Rules for duplicate matching and default action selection."""

    allow_match_by: tuple[str, ...]
    duplicate_action: str
    unmatched_action: str
    duration_margin_ms: int


@dataclass(frozen=True)
class DurationRules:
    """Rules related to duration validation and DJ hard-gates."""

    require_ok_for_dj_promotion: bool
    ok_statuses: tuple[str, ...]
    non_ok_action: str


@dataclass(frozen=True)
class ExecutionRules:
    """Execution-time move collision policy."""

    collision_policy: str


@dataclass(frozen=True)
class PolicyProfile:
    """Fully loaded and validated policy profile."""

    name: str
    version: str
    description: str
    lane: str
    match_rules: MatchRules
    duration_rules: DurationRules
    execution_rules: ExecutionRules
    source_path: str
    source_hash: str

    @property
    def policy_id(self) -> str:
        return f"{self.name}:{self.version}"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "lane": self.lane,
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "rules": {
                "match": {
                    "allow_match_by": list(self.match_rules.allow_match_by),
                    "duplicate_action": self.match_rules.duplicate_action,
                    "unmatched_action": self.match_rules.unmatched_action,
                    "duration_margin_ms": self.match_rules.duration_margin_ms,
                },
                "duration": {
                    "require_ok_for_dj_promotion": (
                        self.duration_rules.require_ok_for_dj_promotion
                    ),
                    "ok_statuses": list(self.duration_rules.ok_statuses),
                    "non_ok_action": self.duration_rules.non_ok_action,
                },
                "execution": {
                    "collision_policy": self.execution_rules.collision_policy,
                },
            },
        }
