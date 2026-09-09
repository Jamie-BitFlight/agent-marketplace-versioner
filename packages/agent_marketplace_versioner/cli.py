"""Typer application exposed by the command-line entry point."""

# Copyright (c) 2026 Jamie Nelson
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Manage versions across agent marketplaces."""
