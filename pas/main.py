"""PAS CLI Entry Point."""

from __future__ import annotations

import typer

from pas.cli import annotation, benchmark, cache

app = typer.Typer(
    name="pas", help="Proactive Agent Sandbox - A Research Framework for Proactive AI Agents", no_args_is_help=True
)

# Register subcommands
app.add_typer(annotation.app, name="annotation")
app.add_typer(benchmark.app, name="benchmark")
app.add_typer(cache.app, name="cache")


def main() -> None:
    """Main entry point for the Proactive Agent Sandbox CLI."""
    app()


if __name__ == "__main__":
    main()
