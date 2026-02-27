"""Main application window for video synchronization."""

import logging
import pathlib
from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt

from ..core import TrackDecoder, SyncEngine
from ..processing import VideoCutter
from ..processing.rrd_packager import package_to_rrd
from .video_pane import VideoPane
from .track_controls import TrackControlWidget


class SyncBench(QtWidgets.QMainWindow):
    """Main application window for video synchronization."""

    # Signals for integration
    videos_synced = QtCore.Signal(dict)  # Emits dict of synced files: {original_path: synced_path}
    sync_cancelled = QtCore.Signal()

    def __init__(self, paths: list[str], output_dir: str | None = None, codec: str = "av1", max_resolution: tuple[int, int] | None = None, s3_mode: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Python Video Sync Bench")
        self.playing = False
        self.selected_track = 0  # Currently selected track for keyboard control
        self.output_dir = str(pathlib.Path(output_dir).resolve()) if output_dir else None
        self.codec = codec  # Video codec setting from app preferences
        self.max_resolution = max_resolution or (1280, 720)  # Default to 720p if not specified
        self.s3_mode = s3_mode  # If True, skip video processing (partial S3 files)

        # Track synced output files
        self.synced_output_files = {}  # original -> synced mapping

        # Initialize processors
        self.video_cutter = VideoCutter(self)

        # Connect to videos_synced signal for RRD packaging (only in local mode)
        if not self.s3_mode:
            self.videos_synced.connect(self._on_videos_synced)

        # Per-track state - each track now has independent time
        self.tracks = []
        self.sync_defined = False

        # Load tracks
        self._load_tracks(paths)

        # Setup UI
        self._setup_ui()
        self._setup_keyboard_shortcuts()

        # Timer for playback
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(16)  # ~60 Hz
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        # Highlight selected track and display it
        self._update_selected_track()
        self._update_displayed_track()
        self.redraw()

    def _load_tracks(self, paths: list[str]):
        """Load video tracks from paths."""
        for p in paths:
            pth = pathlib.Path(p)
            if pth.is_dir():
                # Check if this directory contains a stereo pair (left.mp4 and right.mp4)
                has_left = (pth / "left.mp4").exists()
                has_right = (pth / "right.mp4").exists()

                if has_left and has_right:
                    # This is a stereo directory
                    self._load_stereo_track(pth)
                else:
                    # This directory contains single video files
                    # Load each video file as a separate track
                    video_files = list(pth.glob("*.mp4")) + list(pth.glob("*.mov"))
                    for video_file in video_files:
                        self._load_single_track(video_file)
            else:
                self._load_single_track(pth)

    def _csv_has_ts_ns(self, csv_path: pathlib.Path) -> bool:
        """Check if a CSV file has ts_ns in its header."""
        try:
            with open(csv_path, 'r') as f:
                header = f.readline().strip()
                return 'ts_ns' in header.split(',')
        except Exception as e:
            logging.warning(f"Could not read CSV header from {csv_path}: {e}")
            return False

    def _load_stereo_track(self, pth: pathlib.Path):
        """Load a stereo track from a directory."""
        # Stereo pair: expect left.mp4 and right.mp4, optionally rgb.mp4
        left_mp4 = pth / "left.mp4"
        right_mp4 = pth / "right.mp4"
        rgb_mp4 = pth / "rgb.mp4"

        if not left_mp4.exists() or not right_mp4.exists():
            logging.warning(f"Stereo directory {pth} missing left.mp4 or right.mp4; skipping")
            return

        try:
            decoder = TrackDecoder(str(right_mp4))
        except Exception as e:
            logging.error(f"Failed to open stereo right video {right_mp4}: {e}")
            return

        # Scan directory for all CSV files with ts_ns header
        csv_files = []
        for csv_path in pth.glob("*.csv"):
            if self._csv_has_ts_ns(csv_path):
                csv_files.append(str(csv_path))
                logging.debug(f"Found CSV with ts_ns: {csv_path.name}")

        track_name = f"{pth.name} (stereo: right preview)"
        track_data = {
            "label": track_name,
            "stereo": True,
            "path_left": str(left_mp4),
            "path_right": str(right_mp4),
            "csv_files": csv_files,  # Store all CSVs with ts_ns
            "decoder": decoder,  # preview left
            "current_time_us": 0,
            "pane": VideoPane(track_name),
            "controls": TrackControlWidget(track_name, decoder.duration_us),
            "sync_cut_time_us": None,
            "cut_start_us": None,
            "cut_end_us": None,
        }

        # Add RGB files if they exist
        if rgb_mp4.exists():
            track_data["path_rgb"] = str(rgb_mp4)
            logging.info(f"Found RGB files for {pth.name}")

        logging.info(f"Loaded stereo track with {len(csv_files)} CSV file(s)")
        self.tracks.append(track_data)

    def _load_single_track(self, pth: pathlib.Path):
        """Load a single video track."""
        decoder = TrackDecoder(str(pth))
        track_name = pth.name

        # Scan parent directory for CSV files with ts_ns header
        csv_files = []
        if pth.parent:
            for csv_path in pth.parent.glob("*.csv"):
                if self._csv_has_ts_ns(csv_path):
                    csv_files.append(str(csv_path))
                    logging.debug(f"Found CSV with ts_ns for {track_name}: {csv_path.name}")

        track_data = {
            "label": track_name,
            "path": str(pth),
            "decoder": decoder,
            "current_time_us": 0,  # Independent time for each track
            "pane": VideoPane(track_name),
            "controls": TrackControlWidget(track_name, decoder.duration_us),
            "sync_cut_time_us": None,  # Will be set when sync point is defined
            "cut_start_us": None,
            "cut_end_us": None,
        }

        # Add CSV files if found
        if csv_files:
            track_data["csv_files"] = csv_files
            logging.info(f"Loaded single track {track_name} with {len(csv_files)} CSV file(s)")

        self.tracks.append(track_data)

    def _setup_ui(self):
        """Setup the user interface."""
        # Main layout: video panes on top, controls below
        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout()

        # Video counter label (e.g., "Video 2 of 5")
        self.video_counter_label = QtWidgets.QLabel()
        self.video_counter_label.setAlignment(Qt.AlignCenter)
        self.video_counter_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        main_layout.addWidget(self.video_counter_label)

        # Container widget for single video pane (will be swapped dynamically)
        self.video_container_widget = QtWidgets.QWidget()
        self.video_container = QtWidgets.QVBoxLayout(self.video_container_widget)
        self.video_container.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.video_container_widget, stretch=1)

        # Container widget for single track controls (will be swapped dynamically)
        self.controls_container_widget = QtWidgets.QWidget()
        self.controls_container = QtWidgets.QVBoxLayout(self.controls_container_widget)
        self.controls_container.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.controls_container_widget, stretch=0)

        # Connect scrubber signals for all tracks
        for i, track in enumerate(self.tracks):
            track["controls"].scrubber.valueChanged.connect(
                lambda val, idx=i: self._scrubber_changed(idx, val * 1000)
            )

        # Submit button at bottom
        self.submit_btn = QtWidgets.QPushButton("Submit")
        self.submit_btn.setMinimumHeight(50)
        self.submit_btn.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.submit_btn.clicked.connect(self._cut_videos_directly)
        self.submit_btn.setEnabled(False)  # Disabled until all synced
        main_layout.addWidget(self.submit_btn)

        # Progress bar and status label underneath submit button
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)  # Indeterminate by default
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(30)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("padding: 10px; font-size: 13px;")
        self.status_label.setVisible(False)
        main_layout.addWidget(self.status_label)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Setup toolbar
        self._setup_toolbar()

        # Add keyboard shortcuts cheat sheet below toolbar
        shortcuts_toolbar = QtWidgets.QToolBar()
        shortcuts_toolbar.setMovable(False)

        shortcuts_widget = QtWidgets.QWidget()
        shortcuts_layout = QtWidgets.QHBoxLayout(shortcuts_widget)
        shortcuts_layout.setContentsMargins(10, 5, 10, 5)

        shortcuts_label = QtWidgets.QLabel(
            "Shortcuts: ← → (1 frame) | Shift+← → (10 frames) | Enter (set sync point / submit)"
        )
        shortcuts_label.setStyleSheet("color: #666; font-size: 12px; font-style: italic;")
        shortcuts_layout.addWidget(shortcuts_label)
        shortcuts_layout.addStretch()

        shortcuts_toolbar.addWidget(shortcuts_widget)
        self.addToolBar(QtCore.Qt.TopToolBarArea, shortcuts_toolbar)

    def _setup_toolbar(self):
        """Setup the transport controls toolbar."""
        toolbar = self.addToolBar("Transport")

        # Video navigation buttons
        self.prev_video_btn = QAction("◄ Previous Video", self)
        self.prev_video_btn.triggered.connect(self._previous_video)
        self.prev_video_btn.setStatusTip("Go to previous video")
        toolbar.addAction(self.prev_video_btn)

        self.next_video_btn = QAction("Next Video ►", self)
        self.next_video_btn.triggered.connect(self._next_video)
        self.next_video_btn.setStatusTip("Go to next video")
        toolbar.addAction(self.next_video_btn)

        toolbar.addSeparator()

        # Add track selection
        for i in range(len(self.tracks)):
            select_action = QAction(f"Select Track {i+1}", self)
            select_action.triggered.connect(lambda checked, idx=i: self._select_track(idx))
            toolbar.addAction(select_action)

        toolbar.addSeparator()

        # Sync controls
        sync_action = QAction("Set Sync Point", self)
        sync_action.triggered.connect(self._set_sync_point)
        sync_action.setStatusTip("Set sync point for selected track (auto-advances to next track)")
        toolbar.addAction(sync_action)

        clear_sync_action = QAction("Clear Sync", self)
        clear_sync_action.triggered.connect(self._clear_sync)
        toolbar.addAction(clear_sync_action)

        toolbar.addSeparator()

        # Reference video cut controls
        cut_start_action = QAction("Set Cut Start (Ref)", self)
        cut_start_action.triggered.connect(self._set_cut_start)
        cut_start_action.setStatusTip("Set cut start time on reference video (first track)")
        toolbar.addAction(cut_start_action)

        cut_end_action = QAction("Set Cut End (Ref)", self)
        cut_end_action.triggered.connect(self._set_cut_end)
        cut_end_action.setStatusTip("Set cut end time on reference video (first track)")
        toolbar.addAction(cut_end_action)

        clear_cuts_action = QAction("Clear Cuts", self)
        clear_cuts_action.triggered.connect(self._clear_cuts)
        toolbar.addAction(clear_cuts_action)


    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for frame stepping."""
        # Right arrow: +1 frame
        right_action = QAction(self)
        right_action.setShortcut(QKeySequence(Qt.Key_Right))
        right_action.triggered.connect(lambda: self.step_frames(1))
        self.addAction(right_action)

        # Left arrow: -1 frame
        left_action = QAction(self)
        left_action.setShortcut(QKeySequence(Qt.Key_Left))
        left_action.triggered.connect(lambda: self.step_frames(-1))
        self.addAction(left_action)

        # Shift+Right: +10 frames
        shift_right_action = QAction(self)
        shift_right_action.setShortcut(QKeySequence(Qt.SHIFT | Qt.Key_Right))
        shift_right_action.triggered.connect(lambda: self.step_frames(10))
        self.addAction(shift_right_action)

        # Shift+Left: -10 frames
        shift_left_action = QAction(self)
        shift_left_action.setShortcut(QKeySequence(Qt.SHIFT | Qt.Key_Left))
        shift_left_action.triggered.connect(lambda: self.step_frames(-10))
        self.addAction(shift_left_action)

        # Space: Play/Pause
        space_action = QAction(self)
        space_action.setShortcut(QKeySequence(Qt.Key_Space))
        space_action.triggered.connect(self.toggle_play)
        self.addAction(space_action)

        # Number keys to select tracks
        for i in range(min(9, len(self.tracks))):
            num_action = QAction(self)
            num_action.setShortcut(QKeySequence(Qt.Key_1 + i))
            num_action.triggered.connect(lambda checked, idx=i: self._select_track(idx))
            self.addAction(num_action)

        # Enter key: Set sync point OR submit if all synced
        enter_action = QAction(self)
        enter_action.setShortcut(QKeySequence(Qt.Key_Return))
        enter_action.triggered.connect(self._handle_enter_key)
        self.addAction(enter_action)

    def _select_track(self, track_idx: int):
        """Select a track for keyboard control."""
        if 0 <= track_idx < len(self.tracks):
            self.selected_track = track_idx
            logging.info(f"Selected track {track_idx}: {self.tracks[track_idx]['label']}")
            self._update_selected_track()
            self._update_displayed_track()

    def _previous_video(self):
        """Navigate to the previous video."""
        if self.selected_track > 0:
            self._select_track(self.selected_track - 1)
            logging.info(f"Navigated to previous video: {self.selected_track}")

    def _next_video(self):
        """Navigate to the next video."""
        if self.selected_track < len(self.tracks) - 1:
            self._select_track(self.selected_track + 1)
            logging.info(f"Navigated to next video: {self.selected_track}")

    def _update_selected_track(self):
        """Update visual indication of selected track."""
        for i, track in enumerate(self.tracks):
            if i == self.selected_track:
                track["pane"].setStyleSheet("border: 3px solid blue; border-radius: 5px;")
            else:
                track["pane"].setStyleSheet("")

    def _update_displayed_track(self):
        """Update UI to show only the currently selected track."""
        if not self.tracks:
            return

        # Clear existing widgets from containers
        while self.video_container.count():
            item = self.video_container.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        while self.controls_container.count():
            item = self.controls_container.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Add current track's pane and controls
        current_track = self.tracks[self.selected_track]
        self.video_container.addWidget(current_track["pane"])
        self.controls_container.addWidget(current_track["controls"])

        # Update video counter label
        total_videos = len(self.tracks)
        current_num = self.selected_track + 1
        self.video_counter_label.setText(f"Video {current_num} of {total_videos}")

        # Update Previous/Next button states (if they exist)
        if hasattr(self, 'prev_video_btn'):
            self.prev_video_btn.setEnabled(self.selected_track > 0)
        if hasattr(self, 'next_video_btn'):
            self.next_video_btn.setEnabled(self.selected_track < len(self.tracks) - 1)

    def _scrubber_changed(self, track_idx: int, time_us: int):
        """Handle scrubber position change for individual track."""
        if self.playing:
            return  # Don't scrub during playback

        # Set this track's independent time
        self.tracks[track_idx]["current_time_us"] = time_us
        logging.debug(f"Scrubbed track {track_idx} to {time_us/1000:.1f}ms")
        self._redraw_track(track_idx)

    def _set_sync_point(self):
        """Set sync point for currently selected track and auto-advance workflow."""
        if not self.tracks:
            return

        current_track_idx = self.selected_track
        current_track = self.tracks[current_track_idx]
        current_time = current_track["current_time_us"]

        # Check if this is the first sync point being set
        any_sync_set = any(track.get("sync_cut_time_us") is not None for track in self.tracks)

        if not any_sync_set:
            # First track becomes the reference
            logging.info(f"Setting reference sync point: track {current_track_idx} at {current_time/1000:.1f}ms")
            current_track["controls"].set_sync_offset(0)
            current_track["sync_cut_time_us"] = current_time

            # Auto-scrub all other tracks to the same time for easier alignment
            for i, track in enumerate(self.tracks):
                if i != current_track_idx:
                    # Clamp to video duration
                    max_time = track["decoder"].duration_us if track["decoder"].duration_us > 0 else current_time
                    scrub_time = min(current_time, max_time)
                    track["current_time_us"] = scrub_time
                    logging.info(f"Auto-scrubbed track {i} to {scrub_time/1000:.1f}ms")

            # Redraw all tracks with new positions
            self.redraw()

        else:
            # Subsequent tracks: calculate offset relative to reference
            reference_time = None

            # Find the reference track (the one with offset 0)
            for track in self.tracks:
                if (track.get("sync_cut_time_us") is not None and
                    track["controls"].sync_offset_us == 0):
                    reference_time = track["sync_cut_time_us"]
                    break

            if reference_time is not None:
                offset_us = reference_time - current_time
                current_track["controls"].set_sync_offset(offset_us)
                current_track["sync_cut_time_us"] = current_time
                logging.info(f"Track {current_track_idx} sync set with offset: {offset_us/1000:.1f}ms")

        # Auto-select next unsynced track for smoother workflow
        next_track = self._find_next_unsynced_track()
        if next_track is not None:
            self._select_track(next_track)
            logging.info(f"Auto-selected next track: {next_track}")
        else:
            # All tracks are synced
            self.sync_defined = True
            self.submit_btn.setEnabled(True)  # Enable submit button
            logging.info("All tracks synced! Sync workflow complete. Press Enter or click Submit.")

    def _find_next_unsynced_track(self):
        """Find the next track that doesn't have a sync point set."""
        for i, track in enumerate(self.tracks):
            if track.get("sync_cut_time_us") is None:
                return i
        return None  # All tracks are synced

    def _handle_enter_key(self):
        """Handle Enter key: set sync point OR submit if all synced."""
        if self.sync_defined:
            # All tracks synced - submit
            self._cut_videos_directly()
        else:
            # Not all synced - set sync point
            self._set_sync_point()

    def _clear_sync(self):
        """Clear all sync points and reset workflow."""
        for track in self.tracks:
            track["controls"].set_sync_offset(0)
            track["controls"].sync_label.setText("Not synced")
            track["controls"].sync_label.setStyleSheet("color: orange; font-size: 13px; padding: 2px;")
            track["sync_cut_time_us"] = None
        self.sync_defined = False
        self.submit_btn.setEnabled(False)  # Disable submit button

        # Reset to first track for clean workflow restart
        self._select_track(0)
        logging.info("Sync cleared - videos now play independently. Ready to start sync workflow.")

    def _set_cut_start(self):
        """Set cut start time on reference video (first track)."""
        if not self.tracks:
            return

        reference_track = self.tracks[0]
        cut_start_us = reference_track["current_time_us"]

        # Validate: cut_start must be before cut_end if cut_end is set
        if reference_track["cut_end_us"] is not None and cut_start_us >= reference_track["cut_end_us"]:
            self._show_status(
                f"Invalid Cut Start: {cut_start_us/1000:.1f}ms must be before cut end {reference_track['cut_end_us']/1000:.1f}ms",
                error=True
            )
            return

        reference_track["cut_start_us"] = cut_start_us
        reference_track["controls"].set_cut_start(cut_start_us)
        logging.info(f"Reference video cut start set to {cut_start_us/1000:.1f}ms")
        self._show_status(f"Cut start set to {cut_start_us/1000:.1f}ms", error=False)

    def _set_cut_end(self):
        """Set cut end time on reference video (first track)."""
        if not self.tracks:
            return

        reference_track = self.tracks[0]
        cut_end_us = reference_track["current_time_us"]

        # Validate: cut_end must be after cut_start if cut_start is set
        if reference_track["cut_start_us"] is not None and cut_end_us <= reference_track["cut_start_us"]:
            self._show_status(
                f"Invalid Cut End: {cut_end_us/1000:.1f}ms must be after cut start {reference_track['cut_start_us']/1000:.1f}ms",
                error=True
            )
            return

        reference_track["cut_end_us"] = cut_end_us
        reference_track["controls"].set_cut_end(cut_end_us)
        logging.info(f"Reference video cut end set to {cut_end_us/1000:.1f}ms")
        self._show_status(f"Cut end set to {cut_end_us/1000:.1f}ms", error=False)

    def _clear_cuts(self):
        """Clear cut start/end times on reference video."""
        if not self.tracks:
            return

        reference_track = self.tracks[0]
        reference_track["cut_start_us"] = None
        reference_track["cut_end_us"] = None
        reference_track["controls"].clear_cuts()
        logging.info("Reference video cut times cleared")

    def _cut_videos_directly(self):
        """Cut and sync videos directly using FFmpeg."""
        sync_params = SyncEngine.calculate_sync_parameters(self.tracks)
        if not sync_params:
            self._show_status("Please set sync points first.", error=True)
            return

        # In S3 mode, skip video processing (we only have partial files)
        # Just emit the signal with empty dict to trigger metadata export
        if self.s3_mode:
            logging.info("S3 mode: Skipping video processing, emitting sync completion")
            self.videos_synced.emit({})  # Empty dict since no files were processed
            return

        # Show progress
        self._show_progress("Processing videos...")

        # Default settings for post-capture workflow:
        # - Always replace originals (in-place sync)
        # - Always convert to MP4
        # - Use codec and resolution from app preferences
        replace_files = True
        force_mp4 = True
        target_height = None  # Deprecated, using max_resolution instead
        output_dir = None
        codec = self.codec  # Use codec from app preferences
        crf = "30" if codec == "av1" else "18"  # Balance quality/size per codec
        max_resolution = self.max_resolution  # Use resolution from app preferences

        self.video_cutter.cut_videos(
            self.tracks,
            sync_params,
            replace_files,
            force_mp4,
            target_height,
            output_dir,
            codec=codec,
            crf=crf,
            max_resolution=max_resolution
        )

    def _on_videos_synced(self, output_files: dict):
        """Handle videos synced signal - automatically package to RRD."""
        if not output_files:
            logging.warning("No output files from video sync")
            return

        logging.info(f"Videos synced successfully, automatically packaging to RRD")
        # Automatically package to RRD after syncing
        self._package_to_rrd(output_files)

    def _package_to_rrd(self, output_files: dict):
        """Package synced videos into RRD file."""
        try:
            # Determine output path - use the directory of the first synced file
            first_file = next(iter(output_files.values()))
            first_path = pathlib.Path(first_file)

            # If it's a directory (stereo pair), use its parent
            if first_path.is_dir():
                session_dir = first_path.parent
            else:
                session_dir = first_path.parent

            # Create RRD filename based on session directory name
            rrd_filename = f"{session_dir.name}.rrd"
            output_path = session_dir / rrd_filename

            logging.info(f"Packaging {len(output_files)} videos to RRD: {output_path}")

            # Show progress in UI
            self._show_progress("Packaging videos into Rerun RRD file...")

            # Force UI update
            QtWidgets.QApplication.processEvents()

            # Package to RRD
            success = package_to_rrd(output_files, str(output_path))

            # Hide progress bar
            self.progress_bar.setVisible(False)

            if success:
                logging.info(f"RRD packaging successful: {output_path}")
                self._show_status(f"Successfully created RRD file: {output_path.name}", error=False)
            else:
                logging.error("RRD packaging failed")
                self._show_status("RRD creation failed. Check logs for details.", error=True)

        except Exception as e:
            logging.error(f"Error during RRD packaging: {e}", exc_info=True)
            self.progress_bar.setVisible(False)
            self._show_status(f"Error creating RRD file: {str(e)}", error=True)

    def toggle_play(self):
        """Toggle play/pause state."""
        self.playing = not self.playing
        logging.info(f"Playback {'started' if self.playing else 'paused'}")

    def step_frames(self, n: int):
        """Step forward or backward by n frames on selected track."""
        if not self.tracks:
            return

        # Step only the selected track
        track = self.tracks[self.selected_track]
        # Use the track's FPS to compute frame duration
        fps = track["decoder"].fps if getattr(track["decoder"], "fps", None) else 30.0
        frame_duration_us = int(1_000_000 / fps) if fps > 0 else 33_333
        step_us = int(frame_duration_us * n)
        track["current_time_us"] = max(0, track["current_time_us"] + step_us)

        # Clamp to video duration
        if track["decoder"].duration_us > 0:
            track["current_time_us"] = min(track["current_time_us"], track["decoder"].duration_us)

        logging.debug(f"Stepped track {self.selected_track} by {n} frames to {track['current_time_us']/1000:.1f}ms")
        self._redraw_track(self.selected_track)

    def _tick(self):
        """Timer tick for playback."""
        if self.playing:
            # Check if we have sync points set
            has_sync = any(track["controls"].sync_offset_us != 0 for track in self.tracks[1:])

            if has_sync:
                # Synced playback - advance reference track and calculate others
                self.tracks[0]["current_time_us"] += 16_667  # ~16.67ms per tick (60 Hz)
                reference_time = self.tracks[0]["current_time_us"]

                for i in range(1, len(self.tracks)):
                    offset = self.tracks[i]["controls"].sync_offset_us
                    synced_time = reference_time - offset
                    self.tracks[i]["current_time_us"] = max(0, synced_time)
            else:
                # Independent playback
                for track in self.tracks:
                    track["current_time_us"] += 16_667

            # Clamp all tracks to their durations
            for track in self.tracks:
                if track["decoder"].duration_us > 0:
                    track["current_time_us"] = min(track["current_time_us"], track["decoder"].duration_us)

            self.redraw()

    def _redraw_track(self, track_idx: int):
        """Redraw a single track."""
        track = self.tracks[track_idx]
        time_us = track["current_time_us"]
        pts, img = track["decoder"].frame_at_or_before(time_us)

        if img is not None:
            track["pane"].show_frame(img)
        else:
            logging.warning(f"No image returned for track {track_idx} at {time_us}us")

        track["controls"].update_time_display(time_us)

    def redraw(self):
        """Redraw all video panes with current frames."""
        for i in range(len(self.tracks)):
            self._redraw_track(i)

    def _show_progress(self, message: str):
        """Show progress bar with message."""
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("padding: 10px; font-size: 13px; color: #0066cc;")
        QtWidgets.QApplication.processEvents()

    def _show_status(self, message: str, error: bool = False):
        """Show status message (with optional error styling)."""
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(True)
        self.status_label.setText(message)

        if error:
            self.status_label.setStyleSheet("padding: 10px; font-size: 13px; color: #cc0000; background-color: #fff0f0; border-radius: 3px;")
        else:
            self.status_label.setStyleSheet("padding: 10px; font-size: 13px; color: #006600; background-color: #f0fff0; border-radius: 3px;")

        QtWidgets.QApplication.processEvents()

        # Auto-hide success messages after 5 seconds
        if not error:
            def hide_label():
                # Check if widget still exists before hiding
                try:
                    if self.status_label is not None:
                        self.status_label.setVisible(False)
                except RuntimeError:
                    # Widget was already deleted
                    pass
            QtCore.QTimer.singleShot(5000, hide_label)

    def closeEvent(self, event):
        """Handle window close event - clean up decoders."""
        logging.info("SyncBench closing - cleaning up decoders")
        self._cleanup_decoders()
        super().closeEvent(event)

    def _cleanup_decoders(self):
        """Close all video decoders to release resources."""
        for i, track in enumerate(self.tracks):
            decoder = track.get("decoder")
            if decoder is not None:
                try:
                    decoder.close()
                except Exception as e:
                    logging.error(f"Error closing decoder for track {i}: {e}")
        logging.info(f"Cleaned up {len(self.tracks)} decoders")
