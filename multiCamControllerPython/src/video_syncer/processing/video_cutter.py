"""Video cutting and synchronization processor."""

import subprocess
import pathlib
import logging
import threading
import shutil
from PySide6 import QtWidgets

from ..utils import format_time_us, determine_output_path
from .ffmpeg_builder import FFmpegCommandBuilder
from .csv_processor import CSVProcessor


class VideoCutter:
    """Handles cutting and syncing videos using FFmpeg."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self.output_files = {}  # Track output files: {original_path: synced_path}
        self.cancelled = False  # Track if operation was cancelled

    def cut_videos(
        self,
        tracks: list[dict],
        sync_params: dict,
        replace_files: bool,
        force_mp4: bool,
        target_height: int | None,
        output_dir: str | None = None,
        codec: str = "av1",
        crf: str = "30",
        max_resolution: tuple[int, int] | None = None,
    ):
        """Cut and sync videos directly using FFmpeg.

        Args:
            tracks: List of track dictionaries
            sync_params: Synchronization parameters from SyncEngine
            replace_files: Whether to replace original files
            force_mp4: Whether to force MP4 output format
            target_height: Target resolution height (None = no scaling)
                         DEPRECATED: Use max_resolution instead
            output_dir: Output directory (required if not replacing files)
            codec: Video codec to use - 'av1' or 'h264' (default: 'av1')
            crf: Constant Rate Factor for quality (default: '30' for AV1)
            max_resolution: Maximum resolution as (width, height) tuple
        """
        self.cancelled = False

        def cut_worker():
            try:
                cut_times_us = sync_params["cut_times_us"]
                duration_us = sync_params["duration_us"]
                duration_str = format_time_us(duration_us)

                total_operations = len(tracks) * 2  # videos + CSVs
                completed = 0

                # Track temp files to replace originals
                files_to_replace = []  # list of (temp_path, original_path) tuples
                # Track output files for integration
                self.output_files.clear()

                # Cut videos
                for i, (track, cut_us) in enumerate(zip(tracks, cut_times_us)):
                    if self.cancelled:
                        return

                    cut_str = format_time_us(cut_us)

                    if track.get("stereo"):
                        # Process stereo pair (and RGB if present)
                        sides = ["left", "right"]
                        if track.get("path_rgb"):
                            sides.append("rgb")

                        for side in sides:
                            if self.cancelled:
                                return

                            in_path = track[f"path_{side}"]
                            out_path = determine_output_path(
                                in_path, output_dir, replace_files, force_mp4
                            )

                            p = pathlib.Path(in_path)
                            # Update inline progress
                            if hasattr(self.parent, '_show_progress'):
                                self.parent._show_progress(f"Processing {p.name}... ({int(completed / total_operations * 100)}%)")

                            # Build and run FFmpeg command
                            cmd = FFmpegCommandBuilder.build_cut_command(
                                in_path, out_path, cut_str, duration_str,
                                target_height=target_height,
                                codec=codec,
                                crf=crf,
                                max_resolution=max_resolution
                            )

                            result = subprocess.run(cmd, capture_output=True, text=True)
                            if result.returncode != 0:
                                logging.error(f"FFmpeg failed for {in_path}: {result.stderr}")
                            elif replace_files:
                                files_to_replace.append((out_path, in_path))
                            else:
                                # Track non-replaced outputs
                                self.output_files[in_path] = out_path

                            completed += 0.5
                    else:
                        # Process single video
                        in_path = track["path"]
                        out_path = determine_output_path(
                            in_path, output_dir, replace_files, force_mp4
                        )

                        p = pathlib.Path(in_path)
                        # Update inline progress
                        if hasattr(self.parent, '_show_progress'):
                            self.parent._show_progress(f"Processing {p.name}... ({int(completed / total_operations * 100)}%)")

                        # Build and run FFmpeg command
                        cmd = FFmpegCommandBuilder.build_cut_command(
                            in_path, out_path, cut_str, duration_str,
                            target_height=target_height,
                            codec=codec,
                            crf=crf,
                            max_resolution=max_resolution
                        )

                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode != 0:
                            logging.error(f"FFmpeg failed for {in_path}: {result.stderr}")
                        elif replace_files:
                            files_to_replace.append((out_path, in_path))
                        else:
                            # Track non-replaced outputs
                            self.output_files[in_path] = out_path

                        completed += 1

                # Process CSV files for stereo tracks
                csv_files_to_replace = []
                for track, cut_us in zip(tracks, cut_times_us):
                    if not track.get("stereo") or self.cancelled:
                        continue

                    # Update inline progress
                    if hasattr(self.parent, '_show_progress'):
                        self.parent._show_progress(f"Processing CSV files... ({int(completed / total_operations * 100)}%)")

                    temp_csvs = CSVProcessor.process_stereo_csvs(
                        track, output_dir, cut_us, duration_us, replace_files
                    )
                    if replace_files and temp_csvs:
                        csv_files_to_replace.extend(temp_csvs)

                    completed += 1

                # Replace original files with processed versions
                if replace_files and not self.cancelled:
                    if hasattr(self.parent, '_show_progress'):
                        self.parent._show_progress("Replacing original files... (95%)")

                    for temp_path, original_path in files_to_replace + csv_files_to_replace:
                        try:
                            shutil.move(temp_path, original_path)
                            # When replacing, map original to itself (in-place sync)
                            self.output_files[original_path] = original_path
                        except Exception as e:
                            logging.error(f"Failed to replace {original_path}: {e}")

                if not self.cancelled:
                    if hasattr(self.parent, '_show_progress'):
                        self.parent._show_progress("Complete! (100%)")
                    # Emit completion signal if parent has it
                    if hasattr(self.parent, 'videos_synced'):
                        self.parent.videos_synced.emit(self.output_files)

            except Exception as e:
                logging.error(f"Error during video cutting: {e}")
                if not self.cancelled:
                    # Use parent's status display instead of message box
                    if hasattr(self.parent, '_show_status'):
                        self.parent._show_status(f"Failed to cut videos: {str(e)}", error=True)

        # Run in thread to avoid blocking UI
        thread = threading.Thread(target=cut_worker)
        thread.daemon = True
        thread.start()
