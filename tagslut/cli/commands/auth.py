from __future__ import annotations

import click

from tagslut.cli.runtime import run_tagslut_wrapper, WRAPPER_CONTEXT


def register_auth_group(cli: click.Group) -> None:
    @cli.group()
    def auth():  # type: ignore  # TODO: mypy-strict
        """Canonical provider authentication commands."""

    @auth.command("status", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def auth_status_wrapper(args):  # type: ignore  # TODO: mypy-strict
        """Show provider auth/token status."""
        run_tagslut_wrapper(["_metadata", "auth-status", *list(args)])

    @auth.command("init", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def auth_init_wrapper(args):  # type: ignore  # TODO: mypy-strict
        """Initialize provider token template file."""
        run_tagslut_wrapper(["_metadata", "auth-init", *list(args)])

    @auth.command("refresh", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def auth_refresh_wrapper(args):  # type: ignore  # TODO: mypy-strict
        """Refresh provider access tokens."""
        run_tagslut_wrapper(["_metadata", "auth-refresh", *list(args)])

    @auth.command("login", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def auth_login_wrapper(args):  # type: ignore  # TODO: mypy-strict
        """Run interactive provider login flows."""
        run_tagslut_wrapper(["_metadata", "auth-login", *list(args)])
