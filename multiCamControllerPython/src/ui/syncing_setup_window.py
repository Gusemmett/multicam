"""Syncing setup window for folder selection"""

import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QRadioButton,
    QButtonGroup,
    QComboBox,
    QFrame,
    QProgressBar,
)
from PySide6.QtCore import Qt, Signal

logger = logging.getLogger(__name__)


class SyncingSetupWindow(QWidget):
    """Widget for setting up video syncing workflow"""

    # Signal emitted when setup is complete with source type, path, and optional job_id
    setup_complete = Signal(str, str, str)  # (source_type, path, job_id)
    # source_type: "local", "s3", or "auto"
    # path: local folder path or S3 prefix
    # job_id: job ID for auto mode, empty string otherwise

    def __init__(self, last_video_folder=None, last_s3_path=None, parent=None):
        super().__init__(parent)
        self.last_video_folder = last_video_folder
        self.last_s3_path = last_s3_path
        self.source_type = "local"  # Default to local
        self.local_folder_path = None
        self.s3_path = None
        self.current_job_id = None  # Track current job ID for auto mode
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI layout"""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(20)

        # Title
        title_label = QLabel("Video Syncing Setup")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        main_layout.addSpacing(10)

        # Source type selection
        source_label = QLabel("Video Source:")
        source_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        main_layout.addWidget(source_label)

        source_layout = QHBoxLayout()
        self.local_radio = QRadioButton("Local Folder")
        self.s3_radio = QRadioButton("S3 Directory")
        self.auto_radio = QRadioButton("Auto")
        self.local_radio.setChecked(True)

        self.source_button_group = QButtonGroup()
        self.source_button_group.addButton(self.local_radio)
        self.source_button_group.addButton(self.s3_radio)
        self.source_button_group.addButton(self.auto_radio)

        # Connect all radio buttons to update handler
        self.local_radio.toggled.connect(self.on_source_type_changed)
        self.s3_radio.toggled.connect(self.on_source_type_changed)
        self.auto_radio.toggled.connect(self.on_source_type_changed)

        source_layout.addWidget(self.local_radio)
        source_layout.addWidget(self.s3_radio)
        source_layout.addWidget(self.auto_radio)
        source_layout.addStretch()
        main_layout.addLayout(source_layout)

        main_layout.addSpacing(10)

        # Local folder section
        self.local_frame = QFrame()
        local_frame_layout = QVBoxLayout(self.local_frame)
        local_frame_layout.setContentsMargins(0, 0, 0, 0)

        local_instruction = QLabel(
            "Select the folder containing your recording session.\n\n"
            "The folder should contain:\n"
            "• Individual video files (.mov/.mp4) from regular cameras\n"
            "• Subdirectories with stereo pairs (left.mp4, right.mp4) for ego devices"
        )
        local_instruction.setStyleSheet("font-size: 12px; color: gray;")
        local_instruction.setWordWrap(True)
        local_frame_layout.addWidget(local_instruction)

        local_frame_layout.addSpacing(10)

        folder_layout = QHBoxLayout()
        folder_label = QLabel("Session Folder:")
        folder_label.setMinimumWidth(120)
        folder_layout.addWidget(folder_label)

        self.local_folder_input = QLineEdit()
        self.local_folder_input.setPlaceholderText("No folder selected")
        self.local_folder_input.setReadOnly(True)
        if self.last_video_folder:
            self.local_folder_input.setText(self.last_video_folder)
            self.local_folder_path = self.last_video_folder
        self.local_folder_input.textChanged.connect(self.validate_selection)
        folder_layout.addWidget(self.local_folder_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.setMinimumWidth(100)
        browse_btn.clicked.connect(self.on_browse_local_folder)
        folder_layout.addWidget(browse_btn)

        local_frame_layout.addLayout(folder_layout)
        main_layout.addWidget(self.local_frame)

        # S3 section
        self.s3_frame = QFrame()
        s3_frame_layout = QVBoxLayout(self.s3_frame)
        s3_frame_layout.setContentsMargins(0, 0, 0, 0)

        s3_instruction = QLabel(
            "Enter the full S3 URI to your recording session.\n\n"
            "Example: s3://bucket-name/2025-01-15/session_123/\n\n"
            "⚠️ Note: Only the first 20MB of each video will be downloaded\n"
            "for syncing. Full processing will be done in the cloud using\n"
            "the generated sync_info.json file."
        )
        s3_instruction.setStyleSheet("font-size: 12px; color: gray;")
        s3_instruction.setWordWrap(True)
        s3_frame_layout.addWidget(s3_instruction)

        s3_frame_layout.addSpacing(10)

        # S3 URI input
        s3_uri_layout = QHBoxLayout()
        s3_uri_label = QLabel("S3 URI:")
        s3_uri_label.setMinimumWidth(120)
        s3_uri_layout.addWidget(s3_uri_label)

        self.s3_uri_input = QLineEdit()
        self.s3_uri_input.setPlaceholderText("s3://bucket-name/2025-01-15/session_123/")
        if self.last_s3_path:
            self.s3_uri_input.setText(self.last_s3_path)
            self.s3_path = self.last_s3_path
        self.s3_uri_input.textChanged.connect(self.validate_selection)
        s3_uri_layout.addWidget(self.s3_uri_input)

        s3_frame_layout.addLayout(s3_uri_layout)
        main_layout.addWidget(self.s3_frame)

        # Initially hide S3 frame
        self.s3_frame.setVisible(False)

        # Auto section
        self.auto_frame = QFrame()
        auto_frame_layout = QVBoxLayout(self.auto_frame)
        auto_frame_layout.setContentsMargins(0, 0, 0, 0)

        auto_instruction = QLabel(
            "Automatically fetch the next syncing job from the API.\n\n"
            "The system will retrieve the oldest session waiting to be synced\n"
            "and automatically populate the S3 URI.\n\n"
            "Click 'Get Next Job' to fetch a job from the queue."
        )
        auto_instruction.setStyleSheet("font-size: 12px; color: gray;")
        auto_instruction.setWordWrap(True)
        auto_frame_layout.addWidget(auto_instruction)

        auto_frame_layout.addSpacing(10)

        # Get Next Job button and status
        auto_job_layout = QHBoxLayout()
        auto_job_layout.addStretch()

        self.get_job_btn = QPushButton("Get Next Job")
        self.get_job_btn.setMinimumWidth(120)
        self.get_job_btn.clicked.connect(self.on_get_next_job)
        self.get_job_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        auto_job_layout.addWidget(self.get_job_btn)
        auto_job_layout.addStretch()

        auto_frame_layout.addLayout(auto_job_layout)

        auto_frame_layout.addSpacing(10)

        # Job info display
        self.job_info_label = QLabel("")
        self.job_info_label.setStyleSheet("font-size: 12px; color: #0066cc;")
        self.job_info_label.setWordWrap(True)
        self.job_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        auto_frame_layout.addWidget(self.job_info_label)

        main_layout.addWidget(self.auto_frame)

        # Initially hide Auto frame
        self.auto_frame.setVisible(False)

        # Add stretch
        main_layout.addStretch()

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(self.cancel_btn)

        self.start_btn = QPushButton("Start Syncing")
        self.start_btn.setMinimumWidth(120)
        self.start_btn.clicked.connect(self.on_start_syncing)
        self.start_btn.setEnabled(bool(self.local_folder_path))
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        button_layout.addWidget(self.start_btn)

        main_layout.addLayout(button_layout)

        # Progress section (initially hidden)
        self.progress_frame = QFrame()
        self.progress_frame.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(0, 10, 0, 0)

        self.progress_label = QLabel("Downloading files from S3...")
        self.progress_label.setStyleSheet("font-size: 13px; color: #0066cc;")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m files")
        progress_layout.addWidget(self.progress_bar)

        main_layout.addWidget(self.progress_frame)

    def on_source_type_changed(self):
        """Handle source type radio button change"""
        if self.local_radio.isChecked():
            self.source_type = "local"
            self.local_frame.setVisible(True)
            self.s3_frame.setVisible(False)
            self.auto_frame.setVisible(False)
        elif self.s3_radio.isChecked():
            self.source_type = "s3"
            self.local_frame.setVisible(False)
            self.s3_frame.setVisible(True)
            self.auto_frame.setVisible(False)
        else:  # auto
            self.source_type = "auto"
            self.local_frame.setVisible(False)
            self.s3_frame.setVisible(False)
            self.auto_frame.setVisible(True)

        self.validate_selection()

    def on_browse_local_folder(self):
        """Open directory browser for local folder"""
        start_dir = self.local_folder_input.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Session Folder",
            start_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.local_folder_input.setText(folder)
            self.local_folder_path = folder

    def validate_selection(self):
        """Validate selection and enable/disable start button"""
        is_valid = False

        if self.source_type == "local":
            is_valid = bool(self.local_folder_input.text())
        elif self.source_type == "s3":
            s3_uri = self.s3_uri_input.text().strip()
            # Basic validation: must start with s3://
            is_valid = bool(s3_uri and s3_uri.startswith('s3://'))
        else:  # auto
            # Valid if we have a job ID (job has been fetched)
            is_valid = bool(self.current_job_id)

        self.start_btn.setEnabled(is_valid)

    def on_start_syncing(self):
        """Handle start syncing button click"""
        if self.source_type == "local":
            self._start_local_syncing()
        elif self.source_type == "s3":
            self._start_s3_syncing()
        else:  # auto
            self._start_auto_syncing()

    def _start_local_syncing(self):
        """Start syncing with local folder"""
        if not self.local_folder_path:
            QMessageBox.warning(
                self,
                "No Folder Selected",
                "Please select a session folder."
            )
            return

        # Validate that the folder exists
        folder_path = Path(self.local_folder_path)
        if not folder_path.exists() or not folder_path.is_dir():
            QMessageBox.critical(
                self,
                "Invalid Folder",
                f"The selected folder does not exist:\n{self.local_folder_path}"
            )
            return

        logger.info(f"Setup complete: source=local, path={self.local_folder_path}")

        # Disable start button during workflow
        self.start_btn.setEnabled(False)

        # Emit signal with source type, path, and empty job_id
        self.setup_complete.emit("local", self.local_folder_path, "")

    def _start_s3_syncing(self):
        """Start syncing with S3 directory"""
        s3_uri = self.s3_uri_input.text().strip()

        if not s3_uri:
            QMessageBox.warning(
                self,
                "No S3 URI Entered",
                "Please enter an S3 URI."
            )
            return

        # Validate S3 URI format
        if not s3_uri.startswith('s3://'):
            QMessageBox.warning(
                self,
                "Invalid S3 URI",
                "S3 URI must start with 's3://'\n\n"
                "Example: s3://bucket-name/2025-01-15/session_123/"
            )
            return

        # Parse S3 URI: s3://bucket-name/path/to/folder/
        try:
            # Remove s3:// prefix
            uri_without_prefix = s3_uri[5:]  # Remove 's3://'

            # Split on first /
            if '/' in uri_without_prefix:
                bucket, path = uri_without_prefix.split('/', 1)
            else:
                bucket = uri_without_prefix
                path = ""

            if not bucket:
                raise ValueError("Bucket name is empty")

            # Ensure path ends with / if not empty
            if path and not path.endswith('/'):
                path += '/'

            logger.info(f"Setup complete: source=s3, bucket={bucket}, path={path}")

            # Disable start button during workflow
            self.start_btn.setEnabled(False)

            # Combine as bucket:path for orchestrator
            s3_full_path = f"{bucket}:{path}"

            # Emit signal with source type, full S3 path, and empty job_id
            self.setup_complete.emit("s3", s3_full_path, "")

        except Exception as e:
            logger.error(f"Failed to parse S3 URI: {e}")
            QMessageBox.critical(
                self,
                "Invalid S3 URI",
                f"Failed to parse S3 URI:\n{s3_uri}\n\n"
                f"Error: {str(e)}\n\n"
                "Expected format: s3://bucket-name/path/to/folder/"
            )
            return

    def show_progress(self, current: int, total: int):
        """Show download progress"""
        self.progress_frame.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"Downloading {current}/{total} files from S3...")

    def hide_progress(self):
        """Hide download progress"""
        self.progress_frame.setVisible(False)
        self.progress_bar.setValue(0)

    def on_get_next_job(self):
        """Handle Get Next Job button click"""
        from services.video_job_service import VideoJobService
        import requests

        logger.info("Fetching next syncing job from API")

        # Disable button during fetch
        self.get_job_btn.setEnabled(False)
        self.job_info_label.setText("Fetching next job from API...")

        try:
            # Get next job from API
            job = VideoJobService.get_next_job(job_type="SYNCING", worker_id="multiCamController")

            if job is None:
                # No jobs available
                QMessageBox.information(
                    self,
                    "No Jobs Available",
                    "There are currently no syncing jobs available in the queue.\n\n"
                    "Please try again later or check the job service status."
                )
                self.job_info_label.setText("No jobs available")
                self.get_job_btn.setEnabled(True)
                self.current_job_id = None
                self.s3_path = None
                self.validate_selection()
                return

            # Job retrieved successfully
            self.current_job_id = job.job_id
            self.s3_path = job.s3_uri

            # Parse S3 URI to extract bucket and path
            if job.s3_uri.startswith('s3://'):
                uri_without_prefix = job.s3_uri[5:]
                if '/' in uri_without_prefix:
                    bucket, path = uri_without_prefix.split('/', 1)
                else:
                    bucket = uri_without_prefix
                    path = ""

                # Store the parsed S3 path
                self.s3_path = f"{bucket}:{path}"

            # Update UI
            session_info = f"Session: {job.session_name}" if job.session_name else f"Job ID: {job.job_id[:8]}..."
            self.job_info_label.setText(
                f"✓ Job Retrieved!\n\n"
                f"{session_info}\n"
                f"S3 URI: {job.s3_uri}\n"
                f"Expires: {job.expires_at}"
            )

            # Enable start button
            self.get_job_btn.setEnabled(True)
            self.validate_selection()

            logger.info(f"Retrieved job {job.job_id} for session {job.session_name}")

        except requests.exceptions.Timeout:
            QMessageBox.critical(
                self,
                "Request Timeout",
                "The request to fetch a job timed out.\n\n"
                "Please check your network connection and try again."
            )
            self.job_info_label.setText("Request timed out")
            self.get_job_btn.setEnabled(True)

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch job: {e}")
            QMessageBox.critical(
                self,
                "API Error",
                f"Failed to fetch job from API:\n\n{str(e)}\n\n"
                "Please check your network connection and try again."
            )
            self.job_info_label.setText("Failed to fetch job")
            self.get_job_btn.setEnabled(True)

        except Exception as e:
            logger.error(f"Unexpected error fetching job: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"An unexpected error occurred:\n\n{str(e)}"
            )
            self.job_info_label.setText("Error fetching job")
            self.get_job_btn.setEnabled(True)

    def _start_auto_syncing(self):
        """Start syncing with auto-fetched job"""
        if not self.current_job_id or not self.s3_path:
            QMessageBox.warning(
                self,
                "No Job Selected",
                "Please click 'Get Next Job' to fetch a job first."
            )
            return

        logger.info(f"Starting auto syncing with job {self.current_job_id}")

        # Disable buttons during workflow
        self.start_btn.setEnabled(False)
        self.get_job_btn.setEnabled(False)

        # Emit signal with source type, S3 path, and job_id
        self.setup_complete.emit("auto", self.s3_path, self.current_job_id)

    def reset_for_next_sync(self):
        """Reset the widget for the next sync session"""
        logger.info("Resetting setup window for next sync")
        self.start_btn.setEnabled(True)
        self.get_job_btn.setEnabled(True)
        self.hide_progress()
        self.current_job_id = None
        self.job_info_label.setText("")
        # Keep the previous inputs so user can easily modify them
