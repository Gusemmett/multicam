#!/usr/bin/env python3
"""Entry point for video syncer application."""

import sys
import argparse
import logging
from PySide6 import QtWidgets

from .gui import SyncBench


def main():
    """Main entry point for the video syncer application."""
    parser = argparse.ArgumentParser(description="Video synchronization tool")
    parser.add_argument("videos", nargs="+", help="Video files or stereo directories to synchronize")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("-o", "--output-dir", type=str, default=None, help="Directory to place synced outputs (videos/CSVs)")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.INFO
    if args.debug:
        log_level = logging.DEBUG
    elif args.verbose:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    if not args.videos:
        print("Usage: python -m video_syncer [-v] camA.mp4 camB.mp4 ...")
        sys.exit(1)

    logging.info(f"Starting video syncer with {len(args.videos)} videos")

    # Only create QApplication if one doesn't exist (standalone mode)
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    w = SyncBench(args.videos, output_dir=args.output_dir)
    w.resize(1200, 800)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
