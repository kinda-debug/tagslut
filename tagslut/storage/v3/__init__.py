"""V3 database helpers and dual-write utilities."""

from tagslut.storage.v3.db import open_db_v3
from tagslut.storage.v3.doctor import doctor_v3
from tagslut.storage.v3.migration_runner import run_pending_v3, verify_v3_migration
from tagslut.storage.v3.dual_write import (
    dual_write_enabled,
    dual_write_registered_file,
    ensure_move_plan,
    identity_hints_from_metadata,
    insert_move_execution,
    move_asset_path,
    record_provenance_event,
    resolve_asset_id_by_path,
    upsert_asset_file,
    upsert_asset_link,
    upsert_track_identity,
)
from tagslut.storage.v3.identity_status import (
    IdentityStatusRow,
    compute_identity_statuses,
    summary_counts,
    upsert_identity_statuses,
)
from tagslut.storage.v3.dj_profile import (
    ensure_schema as ensure_dj_profile_schema,
    get_profile,
    list_profiles,
    upsert_profile,
)
from tagslut.storage.v3.preferred_asset import (
    PreferredChoice,
    choose_preferred_asset_for_identity,
    compute_candidate_score,
    compute_preferred_assets,
    upsert_preferred_assets,
)
from tagslut.storage.v3.schema import create_schema_v3
from tagslut.storage.v3.analysis_service import resolve_dj_tag_snapshot, resolve_dj_tag_snapshot_for_path
from tagslut.storage.v3.dj_exports import resolve_latest_dj_export_path

__all__ = [
    "open_db_v3",
    "create_schema_v3",
    "run_pending_v3",
    "verify_v3_migration",
    "doctor_v3",
    "PreferredChoice",
    "compute_candidate_score",
    "choose_preferred_asset_for_identity",
    "compute_preferred_assets",
    "upsert_preferred_assets",
    "resolve_dj_tag_snapshot",
    "resolve_dj_tag_snapshot_for_path",
    "resolve_latest_dj_export_path",
    "IdentityStatusRow",
    "compute_identity_statuses",
    "upsert_identity_statuses",
    "summary_counts",
    "ensure_dj_profile_schema",
    "get_profile",
    "list_profiles",
    "upsert_profile",
    "dual_write_enabled",
    "dual_write_registered_file",
    "ensure_move_plan",
    "identity_hints_from_metadata",
    "insert_move_execution",
    "move_asset_path",
    "record_provenance_event",
    "resolve_asset_id_by_path",
    "upsert_asset_file",
    "upsert_asset_link",
    "upsert_track_identity",
]
