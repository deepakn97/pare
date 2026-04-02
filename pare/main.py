"""PARE CLI Entry Point."""

from __future__ import annotations

import typer

from pare.cli import annotation, benchmark, cache, scenarios

app = typer.Typer(
    name="pare",
    help="Proactive Agents Research Environment - A Research Framework for Proactive AI Agents",
    no_args_is_help=True,
)

# Register subcommands
app.add_typer(annotation.app, name="annotation")
app.add_typer(benchmark.app, name="benchmark")
app.add_typer(cache.app, name="cache")
app.add_typer(scenarios.app, name="scenarios")


def main() -> None:
    """Main entry point for the Proactive Agents Research Environment CLI."""
    app()


if __name__ == "__main__":
    main()
