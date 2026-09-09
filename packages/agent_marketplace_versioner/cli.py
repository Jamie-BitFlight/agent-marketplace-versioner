"""Typer application exposed by the command-line entry point."""

# Copyright (c) 2026 Jamie Nelson
from __future__ import annotations

import typer

from agent_marketplace_versioner.auto_sync_manifests import (
    reconcile_native_manifests,
    sync_native_marketplaces,
    sync_staged_manifests,
)
from agent_marketplace_versioner.check_plugin_version_bump import _run_audit, _run_check, _run_repair

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Manage versions across agent marketplaces."""


@app.command()
def sync(
    marketplace: bool = typer.Option(
        False, "--marketplace", help="Reconcile and version native marketplace manifests."
    ),
    base_ref: str | None = typer.Option(None, "--base-ref", help="Base revision for a marketplace version bump."),
    head_ref: str = typer.Option("HEAD", "--head-ref", help="Candidate revision for a marketplace version bump."),
) -> None:
    """Synchronize staged native manifests or post-merge marketplaces."""
    if marketplace:
        for path in sync_native_marketplaces(base_ref=base_ref, head_ref=head_ref):
            typer.echo(path.as_posix())
        return
    for source, version in sync_staged_manifests().items():
        typer.echo(f"{source.as_posix()} {version}")


@app.command()
def check(
    base_ref: str | None = typer.Option(None, "--base-ref", help="Git base ref; defaults to origin/main or main."),
    head_ref: str | None = typer.Option(None, "--head-ref", help="Git head ref; defaults to HEAD."),
) -> None:
    """Fail when changed native manifests did not increase their version."""
    raise typer.Exit(_run_check(base_ref, head_ref))


@app.command()
def audit() -> None:
    """Report native manifests with content drift after their last version bump."""
    raise typer.Exit(_run_audit())


@app.command()
def repair() -> None:
    """Patch-bump native manifests with content drift after their last version bump."""
    raise typer.Exit(_run_repair())


@app.command()
def reconcile(
    dry_run: bool = typer.Option(False, "--dry-run", help="Report manifest drift without changing files."),
) -> None:
    """Reconcile native component arrays and marketplace membership."""
    raise typer.Exit(reconcile_native_manifests(dry_run=dry_run))
