#!/usr/bin/env python3
"""Utility script to fix scenario naming issues in generated scenarios.

Removes the 'scenario_' prefix from @register_scenario decorators, class names, and filenames.
"""

from __future__ import annotations

import re
from pathlib import Path


def fix_scenario_content(content: str) -> str:
    """Fix scenario naming in file content."""
    lines = content.split("\n")
    fixed_lines = []

    for line in lines:
        # Fix @register_scenario decorator
        if "@register_scenario(" in line:
            match = re.search(r'@register_scenario\(["\']([^"\']+)["\']\)', line)
            if match:
                scenario_id = match.group(1)
                if scenario_id.startswith("scenario_"):
                    scenario_id = scenario_id[9:]  # Remove "scenario_" prefix (9 characters)
                    fixed_line = line.replace(match.group(1), scenario_id)
                    fixed_lines.append(fixed_line)
                    print(f"  Fixed scenario ID: {match.group(1)} -> {scenario_id}")
                    continue

        # Fix class names that start with "Scenario" - remove the "Scenario" prefix entirely
        if line.strip().startswith("class Scenario"):
            class_match = re.search(r"class\s+(Scenario\w+)", line)
            if class_match:
                class_name = class_match.group(1)
                # Remove "Scenario" prefix (8 characters) from class name
                scenario_part = class_name[8:]  # Remove "Scenario" prefix (8 characters)
                fixed_class_name = scenario_part
                fixed_line = line.replace(class_name, fixed_class_name)
                fixed_lines.append(fixed_line)
                print(f"  Fixed class name: {class_name} -> {fixed_class_name}")
                continue

        fixed_lines.append(line)

    return "\n".join(fixed_lines)


def get_scenario_files() -> list[Path]:
    """Get all scenario files that need fixing."""
    scenarios_dir = Path(__file__).resolve().parents[2] / "scenarios" / "generated_scenarios"
    scenario_files: list[Path] = []

    if not scenarios_dir.exists():
        print(f"Scenarios directory not found: {scenarios_dir}")
        return scenario_files

    for file_path in scenarios_dir.glob("*.py"):
        if file_path.is_file() and not file_path.name.startswith("__"):
            # Check if file contains scenario_ prefix OR if it contains class names with "Scenario" prefix
            if "scenario_" in file_path.name:
                scenario_files.append(file_path)
            else:
                # Check if file contains class definitions that start with "Scenario"
                try:
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()
                        if "class Scenario" in content:
                            scenario_files.append(file_path)
                except Exception as e:
                    print(f"Warning: Could not read file {file_path}: {e}")

    return scenario_files


def fix_scenario_file(file_path: Path) -> bool:
    """Fix a single scenario file."""
    print(f"Processing: {file_path.name}")

    try:
        # Read the file
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # Fix the content
        fixed_content = fix_scenario_content(content)

        # Check if content actually changed
        if content == fixed_content:
            print("  No changes needed")
            return False

        # Write the fixed content back
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(fixed_content)

        # Rename the file if it has scenario_ prefix
        new_name = file_path.name
        if new_name.startswith("scenario_"):
            new_name = new_name[9:]  # Remove "scenario_" prefix (9 characters)
            new_path = file_path.parent / new_name

            # Rename the file
            file_path.rename(new_path)
            print(f"  Renamed file: {file_path.name} -> {new_name}")
            return True
        else:
            return True

    except Exception as e:
        print(f"  Error processing file: {e}")
        return False


def main() -> None:
    """Main function to fix all scenario files."""
    print("Fixing scenario naming issues...")
    print("=" * 50)

    scenario_files = get_scenario_files()

    if not scenario_files:
        print("No scenario files found that need fixing.")
        return

    print(f"Found {len(scenario_files)} scenario files that may need fixing:")
    for file_path in scenario_files:
        print(f"  - {file_path.name}")

    print("\nProcessing files...")
    print("-" * 30)

    fixed_count = 0
    for file_path in scenario_files:
        if fix_scenario_file(file_path):
            fixed_count += 1

    print("\n" + "=" * 50)
    print(f"Fixed {fixed_count} out of {len(scenario_files)} scenario files.")
    print("Done!")


if __name__ == "__main__":
    main()
