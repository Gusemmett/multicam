"""MultiCam Controller - Cross-platform camera controller"""

import sys
from pathlib import Path


def _get_version() -> str:
    """Get version from VERSION file, works in both dev and bundled modes."""
    if getattr(sys, "frozen", False):
        # Running as bundled PyInstaller app
        version_file = Path(sys._MEIPASS) / "resources" / "VERSION"
    else:
        # Running in development
        version_file = Path(__file__).parent.parent / "resources" / "VERSION"

    try:
        return version_file.read_text().strip()
    except FileNotFoundError:
        return "0.0.0"


__version__ = _get_version()
