"""Configuration helpers for the annotation module."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Config file location (shared with cache module)
CONFIG_DIR = Path.home() / ".config" / "pas"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_config() -> dict[str, str]:
    """Load PAS configuration from config file.

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
    """Save PAS configuration to config file.

    Args:
        config: Configuration dictionary to save.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_annotations_dir() -> Path:
    """Get the annotations directory path.

    Priority:
    1. PAS_ANNOTATIONS_DIR environment variable
    2. Persistent config file setting (~/.config/pas/config.json -> annotations_dir)
    3. Default: ~/.cache/pas/annotations

    Returns:
        Path to the annotations directory.
    """
    # Check environment variable first
    env_dir = os.environ.get("PAS_ANNOTATIONS_DIR")
    if env_dir:
        return Path(env_dir)

    # Check config file
    config = _load_config()
    if "annotations_dir" in config:
        return Path(config["annotations_dir"])

    # Default
    return Path.home() / ".cache" / "pas" / "annotations"


def set_annotations_dir(folder_path: Path, create: bool = False) -> None:
    """Set the annotations directory path (persistent).

    Args:
        folder_path: Path to the annotations directory.
        create: If True, create the directory if it doesn't exist.

    Raises:
        FileNotFoundError: If the directory doesn't exist and create is False.
        NotADirectoryError: If the path exists but is not a directory.
    """
    folder_path = folder_path.resolve()

    if not folder_path.exists():
        if create:
            folder_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created annotations directory: {folder_path}")
        else:
            raise FileNotFoundError(f"Directory does not exist: {folder_path}")

    if not folder_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {folder_path}")

    config = _load_config()
    config["annotations_dir"] = str(folder_path)
    _save_config(config)

    logger.info(f"Annotations directory set to: {folder_path}")


def reset_annotations_dir() -> Path:
    """Reset annotations directory to default location.

    Returns:
        The default annotations directory path.
    """
    config = _load_config()

    if "annotations_dir" in config:
        del config["annotations_dir"]
        _save_config(config)

    default_dir = Path.home() / ".cache" / "pas" / "annotations"
    logger.info(f"Annotations directory reset to default: {default_dir}")
    return default_dir


def get_samples_file() -> Path:
    """Get the path to the samples parquet file.

    Returns:
        Path to samples.parquet.
    """
    return get_annotations_dir() / "samples.parquet"


def get_annotations_file() -> Path:
    """Get the path to the annotations CSV file.

    Returns:
        Path to annotations.csv.
    """
    return get_annotations_dir() / "annotations.csv"


def ensure_annotations_dir() -> Path:
    """Ensure the annotations directory exists.

    Returns:
        Path to the annotations directory.
    """
    annotations_dir = get_annotations_dir()
    annotations_dir.mkdir(parents=True, exist_ok=True)
    return annotations_dir
