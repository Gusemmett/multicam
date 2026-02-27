"""Path utilities for determining output locations."""

import pathlib


def determine_output_path(
    input_path: str,
    output_dir: str | None,
    replace_files: bool,
    force_mp4: bool,
    suffix: str = "-synced"
) -> str:
    """Determine output path based on settings.

    Args:
        input_path: Original input file path
        output_dir: Output directory (if not replacing files)
        replace_files: Whether to replace original files
        force_mp4: Whether to force .mp4 extension
        suffix: Suffix to add to filename (default: "-synced")

    Returns:
        Output file path as string
    """
    p = pathlib.Path(input_path)

    # Always use suffix for temporary file - will be moved later if replace_files=True
    out_name = p.stem + suffix
    if force_mp4:
        out_name += ".mp4"
    else:
        out_name += p.suffix

    if replace_files:
        # Write to temp file in same directory
        return str(p.parent / out_name)
    else:
        return str(pathlib.Path(output_dir) / out_name)
