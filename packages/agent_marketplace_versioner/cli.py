"""Typer application exposed by the command-line entry point."""

# Copyright (c) 2026 Jamie Nelson
from __future__ import annotations

import typer

from agent_marketplace_versioner.auto_sync_manifests import sync_native_marketplaces, sync_staged_manifests

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Manage versions across agent marketplaces."""


@app.command()
def sync(
    marketplace: bool = typer.Option(
        False, "--marketplace", help="Reconcile and version native marketplace manifests."
    ),
) -> None:
    """Synchronize staged native manifests or post-merge marketplaces."""
    if marketplace:
        for path in sync_native_marketplaces():
            typer.echo(path.as_posix())
        return
    for source, version in sync_staged_manifests().items():
        typer.echo(f"{source.as_posix()} {version}")
