"""V3 database schema and connection helpers."""

from tagslut.db.v3.db import open_db_v3
from tagslut.db.v3.doctor import doctor_v3
from tagslut.db.v3.identity_status import (
    IdentityStatusRow,
    compute_identity_statuses,
    summary_counts,
    upsert_identity_statuses,
)
from tagslut.db.v3.dj_profile import (
    ensure_schema as ensure_dj_profile_schema,
    get_profile,
    list_profiles,
    upsert_profile,
)
from tagslut.db.v3.preferred_asset import (
    PreferredChoice,
    choose_preferred_asset_for_identity,
    compute_candidate_score,
    compute_preferred_assets,
    upsert_preferred_assets,
)
from tagslut.db.v3.schema import create_schema_v3

__all__ = [
    "open_db_v3",
    "create_schema_v3",
    "doctor_v3",
    "PreferredChoice",
    "compute_candidate_score",
    "choose_preferred_asset_for_identity",
    "compute_preferred_assets",
    "upsert_preferred_assets",
    "IdentityStatusRow",
    "compute_identity_statuses",
    "upsert_identity_statuses",
    "summary_counts",
    "ensure_dj_profile_schema",
    "get_profile",
    "list_profiles",
    "upsert_profile",
]
