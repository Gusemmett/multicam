#!/usr/bin/env python3
"""
Bump the patch version in resources/VERSION.

1.0.0 -> 1.0.1
1.2.3 -> 1.2.4
"""

from pathlib import Path


def bump_patch_version():
    version_file = Path(__file__).parent.parent / "resources" / "VERSION"

    if not version_file.exists():
        raise FileNotFoundError(f"VERSION file not found at {version_file}")

    current = version_file.read_text().strip()
    parts = current.split(".")

    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {current}")

    major, minor, patch = parts
    new_patch = int(patch) + 1
    new_version = f"{major}.{minor}.{new_patch}"

    version_file.write_text(f"{new_version}\n")

    print(f"Version bumped: {current} -> {new_version}")
    return new_version


if __name__ == "__main__":
    bump_patch_version()
