from __future__ import annotations

import os


def _env_first(*keys: str) -> str:
    for key in keys:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def current_operator() -> str:
    return _env_first("TAGSLUT_OPERATOR", "LOGNAME", "USER")


def current_run_id() -> str:
    return (os.environ.get("TAGSLUT_RUN_ID") or "").strip()


def current_tool() -> str:
    return (os.environ.get("TAGSLUT_TOOL") or "").strip() or "cli"


def current_correlation_id() -> str:
    return (os.environ.get("TAGSLUT_CORRELATION_ID") or "").strip()


def context_details() -> dict[str, str]:
    details: dict[str, str] = {}
    operator = current_operator()
    if operator:
        details["operator"] = operator
    tool = current_tool()
    if tool:
        details["tool"] = tool
    run_id = current_run_id()
    if run_id:
        details["run_id"] = run_id
    corr_id = current_correlation_id()
    if corr_id:
        details["correlation_id"] = corr_id
    return details

