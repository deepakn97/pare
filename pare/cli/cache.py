"""Cache CLI command for managing PARE scenario result cache."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

import typer

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="cache",
    help="Manage PARE scenario result cache",
)

# Config file location
CONFIG_DIR = Path.home() / ".config" / "pare"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_config() -> dict[str, str]:
    """Load PARE configuration from config file.

    Returns:
        Configuration dictionary.
    """
    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load config file: {e}")
        return {}


def _save_config(config: dict[str, str]) -> None:
    """Save PARE configuration to config file.

    Args:
        config: Configuration dictionary to save.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def _get_cache_dir() -> Path:
    """Get the current cache directory.

    Priority:
    1. PARE_CACHE_DIR environment variable
    2. Persistent config file setting
    3. Default: ~/.cache/pare/scenario_results

    Returns:
        Path to the cache directory.
    """
    import os

    # Check environment variable first
    env_cache_dir = os.environ.get("PARE_CACHE_DIR")
    if env_cache_dir:
        return Path(env_cache_dir)

    # Check config file
    config = _load_config()
    if "cache_dir" in config:
        return Path(config["cache_dir"])

    # Default
    return Path.home() / ".cache" / "pare" / "scenario_results"


def _format_size(size_bytes: int) -> str:
    """Format size in bytes to human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Human-readable size string.
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


@app.command()
def status() -> None:
    """Show cache status including location, entry count, and size."""
    cache_dir = _get_cache_dir()

    typer.echo("PARE Cache Status")
    typer.echo("=" * 40)
    typer.echo(f"Cache directory: {cache_dir}")

    # Check source of cache dir setting
    import os

    if os.environ.get("PARE_CACHE_DIR"):
        typer.echo("  (set via PARE_CACHE_DIR environment variable)")
    elif _load_config().get("cache_dir"):
        typer.echo("  (set via config file)")
    else:
        typer.echo("  (default location)")

    if not cache_dir.exists():
        typer.echo("\nCache directory does not exist (no cached results)")
        return

    # Count entries and calculate size
    cache_files = list(cache_dir.glob("*.json"))
    total_size = sum(f.stat().st_size for f in cache_files)

    typer.echo(f"\nEntries: {len(cache_files)}")
    typer.echo(f"Total size: {_format_size(total_size)}")

    # Show config file location
    typer.echo(f"\nConfig file: {CONFIG_FILE}")
    if CONFIG_FILE.exists():
        typer.echo("  (exists)")
    else:
        typer.echo("  (not created yet)")


@app.command()
def invalidate(
    confirm: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Clear all cached scenario results."""
    cache_dir = _get_cache_dir()

    if not cache_dir.exists():
        typer.echo("Cache directory does not exist. Nothing to clear.")
        return

    cache_files = list(cache_dir.glob("*.json"))
    if not cache_files:
        typer.echo("Cache is already empty.")
        return

    total_size = sum(f.stat().st_size for f in cache_files)

    if not confirm:
        typer.echo(f"This will delete {len(cache_files)} cached results ({_format_size(total_size)})")
        typer.echo(f"Cache directory: {cache_dir}")
        if not typer.confirm("Are you sure you want to continue?"):
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    # Delete cache files
    deleted_count = 0
    for cache_file in cache_files:
        try:
            cache_file.unlink()
            deleted_count += 1
        except OSError as e:
            typer.echo(f"Failed to delete {cache_file}: {e}", err=True)

    typer.echo(f"Deleted {deleted_count} cached results.")


@app.command("set")
def set_cache_dir(
    folder_path: Annotated[
        Path,
        typer.Argument(help="Path to the cache directory"),
    ],
    create: Annotated[
        bool,
        typer.Option("--create", "-c", help="Create the directory if it doesn't exist"),
    ] = False,
) -> None:
    """Set the cache directory path (persistent).

    This setting is saved to ~/.config/pare/config.json and persists across sessions.
    The PARE_CACHE_DIR environment variable takes precedence over this setting.
    """
    # Resolve to absolute path
    folder_path = folder_path.resolve()

    # Check if directory exists or should be created
    if not folder_path.exists():
        if create:
            folder_path.mkdir(parents=True, exist_ok=True)
            typer.echo(f"Created directory: {folder_path}")
        else:
            typer.echo(f"Directory does not exist: {folder_path}", err=True)
            typer.echo("Use --create to create it automatically.")
            raise typer.Exit(code=1)

    if not folder_path.is_dir():
        typer.echo(f"Path is not a directory: {folder_path}", err=True)
        raise typer.Exit(code=1)

    # Load existing config and update
    config = _load_config()
    config["cache_dir"] = str(folder_path)
    _save_config(config)

    typer.echo(f"Cache directory set to: {folder_path}")
    typer.echo(f"Config saved to: {CONFIG_FILE}")

    # Warn if environment variable is set
    import os

    if os.environ.get("PARE_CACHE_DIR"):
        typer.echo(
            "\nNote: PARE_CACHE_DIR environment variable is set and will take precedence over this config file setting."
        )


@app.command()
def reset() -> None:
    """Reset cache directory to default location.

    Removes the cache_dir setting from the config file.
    """
    config = _load_config()

    if "cache_dir" not in config:
        typer.echo("Cache directory is already using the default location.")
        return

    del config["cache_dir"]
    _save_config(config)

    default_cache_dir = Path.home() / ".cache" / "pare" / "scenario_results"
    typer.echo(f"Cache directory reset to default: {default_cache_dir}")
