"""Settings dialog for application preferences"""

import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QDoubleSpinBox,
    QSpinBox,
    QComboBox,
    QLineEdit,
    QPushButton,
    QGroupBox,
    QDialogButtonBox,
    QFileDialog,
)
from PySide6.QtCore import Qt

from models.app_settings import AppSettings
from utils.constants import RESOLUTION_OPTIONS, RESOLUTION_DISPLAY_NAMES

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Dialog for editing application settings"""

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI layout"""
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)

        # Video Processing Section
        video_group = self.create_video_processing_section()
        main_layout.addWidget(video_group)

        # Cloud Storage Section
        cloud_group = self.create_cloud_storage_section()
        main_layout.addWidget(cloud_group)

        # Recording Section
        recording_group = self.create_recording_section()
        main_layout.addWidget(recording_group)

        # File Transfers Section
        file_transfers_group = self.create_file_transfers_section()
        main_layout.addWidget(file_transfers_group)

        # Add stretch to push buttons to bottom
        main_layout.addStretch()

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.on_save)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        # Load current settings into UI
        self.load_settings_to_ui()

    def create_video_processing_section(self) -> QGroupBox:
        """Create video processing settings section"""
        group = QGroupBox("Video Processing")
        layout = QVBoxLayout()

        # Re-encode to AV1 checkbox
        self.av1_checkbox = QCheckBox("Re-encode to AV1")
        self.av1_checkbox.setToolTip(
            "AV1 encoding produces smaller file sizes but takes longer to process.\n"
            "Disable for faster processing with H.264 encoding."
        )
        layout.addWidget(self.av1_checkbox)

        # Description label
        desc_label = QLabel("AV1: Smaller files, slower encoding\nH.264: Larger files, faster encoding")
        desc_label.setStyleSheet("color: gray; font-size: 10px; margin-left: 20px;")
        layout.addWidget(desc_label)

        # Max video resolution
        resolution_layout = QHBoxLayout()
        resolution_label = QLabel("Max Video Resolution:")
        resolution_layout.addWidget(resolution_label)

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([RESOLUTION_DISPLAY_NAMES[opt] for opt in RESOLUTION_OPTIONS])
        self.resolution_combo.setToolTip(
            "Maximum output video resolution.\n"
            "Videos larger than this will be downscaled to save space and bandwidth."
        )
        resolution_layout.addWidget(self.resolution_combo)
        resolution_layout.addStretch()

        layout.addLayout(resolution_layout)

        # Resolution description
        res_desc_label = QLabel("Downscale videos to reduce file size")
        res_desc_label.setStyleSheet("color: gray; font-size: 10px; margin-left: 20px;")
        layout.addWidget(res_desc_label)

        group.setLayout(layout)
        return group

    def create_cloud_storage_section(self) -> QGroupBox:
        """Create cloud storage settings section"""
        group = QGroupBox("Cloud Storage (S3)")
        layout = QVBoxLayout()

        # 1. Upload Type/Method selector (TOP LEVEL)
        method_layout = QHBoxLayout()
        method_label = QLabel("Upload/File Management:")
        method_layout.addWidget(method_label)

        self.upload_type_combo = QComboBox()
        self.upload_type_combo.addItem("Direct upload from devices", "direct")
        self.upload_type_combo.addItem("Download and process then upload", "download_and_process")
        self.upload_type_combo.setToolTip(
            "Direct upload: Devices upload raw files directly to S3 (fastest, no processing)\n"
            "Download and process: Controller downloads, processes, then uploads (syncing + encoding)"
        )
        self.upload_type_combo.currentIndexChanged.connect(self.on_upload_type_changed)
        method_layout.addWidget(self.upload_type_combo)
        method_layout.addStretch()

        layout.addLayout(method_layout)

        # Upload type description
        self.upload_type_desc = QLabel()
        self.upload_type_desc.setStyleSheet("color: gray; font-size: 10px; margin-left: 20px; margin-bottom: 10px;")
        layout.addWidget(self.upload_type_desc)

        # 2. Upload to S3 checkbox (SECOND LEVEL)
        self.upload_s3_checkbox = QCheckBox("Upload to S3")
        self.upload_s3_checkbox.setToolTip("Automatically upload videos to Amazon S3")
        self.upload_s3_checkbox.stateChanged.connect(self.on_upload_s3_changed)
        layout.addWidget(self.upload_s3_checkbox)

        # 3. S3 Bucket selector (THIRD LEVEL)
        bucket_layout = QHBoxLayout()
        bucket_layout.setContentsMargins(20, 5, 0, 0)
        bucket_label = QLabel("S3 Bucket:")
        bucket_layout.addWidget(bucket_label)

        self.bucket_combo = QComboBox()
        from utils.constants import S3_BUCKET_OPTIONS
        for name, bucket_id in S3_BUCKET_OPTIONS.items():
            self.bucket_combo.addItem(name, bucket_id)
        self.bucket_combo.setToolTip(
            "Select which S3 bucket to use:\n"
            "• Production: Live customer data\n"
            "• Development: Testing and development"
        )
        bucket_layout.addWidget(self.bucket_combo)
        bucket_layout.addStretch()

        layout.addLayout(bucket_layout)

        # Bucket description
        bucket_desc = QLabel("Choose production or development bucket")
        bucket_desc.setStyleSheet("color: gray; font-size: 10px; margin-left: 40px; margin-bottom: 10px;")
        layout.addWidget(bucket_desc)

        # 4. CONDITIONAL SETTINGS (shown only for download_and_process)
        # Upload mode selector (indented, depends on upload_s3 AND download_and_process)
        upload_mode_layout = QHBoxLayout()
        upload_mode_layout.setContentsMargins(20, 0, 0, 0)
        upload_mode_label = QLabel("Upload Mode:")
        upload_mode_layout.addWidget(upload_mode_label)

        self.upload_mode_combo = QComboBox()
        self.upload_mode_combo.addItem("Immediate (upload right after processing)", "immediate")
        self.upload_mode_combo.addItem("Manual (queue for later)", "manual")
        self.upload_mode_combo.setToolTip(
            "Immediate: Upload files to S3 immediately after processing\n"
            "Manual: Queue files for upload later (e.g., at night when bandwidth is available)"
        )
        upload_mode_layout.addWidget(self.upload_mode_combo)
        upload_mode_layout.addStretch()

        layout.addLayout(upload_mode_layout)

        # Upload mode description
        self.upload_mode_desc = QLabel("Choose when to upload: now or queue for later")
        self.upload_mode_desc.setStyleSheet("color: gray; font-size: 10px; margin-left: 40px;")
        layout.addWidget(self.upload_mode_desc)

        # Delete after upload checkbox (indented, depends on upload_s3 AND download_and_process)
        self.delete_after_upload_checkbox = QCheckBox("Delete local files after upload")
        self.delete_after_upload_checkbox.setToolTip(
            "Automatically delete local video files after successful S3 upload.\n"
            "This frees up disk space but requires re-downloading from S3 to access files."
        )
        self.delete_after_upload_checkbox.setStyleSheet("margin-left: 20px;")
        layout.addWidget(self.delete_after_upload_checkbox)

        # Description label
        desc_label = QLabel("Upload videos to cloud storage for backup and sharing")
        desc_label.setStyleSheet("color: gray; font-size: 10px; margin-left: 20px;")
        layout.addWidget(desc_label)

        group.setLayout(layout)
        return group

    def create_recording_section(self) -> QGroupBox:
        """Create recording settings section"""
        group = QGroupBox("Recording")
        layout = QVBoxLayout()

        # Recording delay
        delay_layout = QHBoxLayout()
        delay_label = QLabel("Recording Delay:")
        delay_layout.addWidget(delay_label)

        self.delay_spinbox = QDoubleSpinBox()
        self.delay_spinbox.setMinimum(1.0)
        self.delay_spinbox.setMaximum(10.0)
        self.delay_spinbox.setSingleStep(0.5)
        self.delay_spinbox.setSuffix(" seconds")
        self.delay_spinbox.setToolTip(
            "Delay before starting recording to ensure all devices are synchronized.\n"
            "Range: 1.0 to 10.0 seconds"
        )
        delay_layout.addWidget(self.delay_spinbox)
        delay_layout.addStretch()

        layout.addLayout(delay_layout)

        # Description label
        desc_label = QLabel("Countdown time before recording starts (for device synchronization)")
        desc_label.setStyleSheet("color: gray; font-size: 10px; margin-left: 20px;")
        layout.addWidget(desc_label)

        group.setLayout(layout)
        return group

    def create_file_transfers_section(self) -> QGroupBox:
        """Create file transfers settings section"""
        group = QGroupBox("File Transfers")
        layout = QVBoxLayout()

        # Max download retries
        retries_layout = QHBoxLayout()
        retries_label = QLabel("Max Download Retries:")
        retries_layout.addWidget(retries_label)

        self.retries_spinbox = QSpinBox()
        self.retries_spinbox.setMinimum(0)
        self.retries_spinbox.setMaximum(10)
        self.retries_spinbox.setSingleStep(1)
        self.retries_spinbox.setToolTip(
            "Number of times to retry failed downloads.\n"
            "Higher values are more reliable on unstable networks.\n"
            "Range: 0 to 10"
        )
        retries_layout.addWidget(self.retries_spinbox)
        retries_layout.addStretch()

        layout.addLayout(retries_layout)

        # Downloads directory
        dir_layout = QHBoxLayout()
        dir_label = QLabel("Downloads Directory:")
        dir_layout.addWidget(dir_label)

        self.downloads_dir_input = QLineEdit()
        self.downloads_dir_input.setPlaceholderText("Default: ~/Downloads/multiCam")
        self.downloads_dir_input.setToolTip(
            "Custom directory for downloaded files.\n"
            "Leave empty to use default location (~/Downloads/multiCam)"
        )
        dir_layout.addWidget(self.downloads_dir_input)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setMaximumWidth(100)
        self.browse_btn.clicked.connect(self.on_browse_directory)
        dir_layout.addWidget(self.browse_btn)

        layout.addLayout(dir_layout)

        # Delete ZIP after unpack checkbox
        self.delete_zip_checkbox = QCheckBox("Delete ZIP files after unpacking")
        self.delete_zip_checkbox.setToolTip(
            "Automatically delete ZIP files after successfully extracting their contents.\n"
            "This saves disk space but means you won't have the original ZIP archive."
        )
        layout.addWidget(self.delete_zip_checkbox)

        # Description label
        desc_label = QLabel("Configure download behavior and storage location")
        desc_label.setStyleSheet("color: gray; font-size: 10px; margin-left: 20px;")
        layout.addWidget(desc_label)

        group.setLayout(layout)
        return group

    def load_settings_to_ui(self):
        """Load current settings values into UI widgets"""
        self.av1_checkbox.setChecked(self.settings.reencode_to_av1)

        # Load max video resolution
        try:
            index = RESOLUTION_OPTIONS.index(self.settings.max_video_resolution)
        except ValueError:
            index = 2  # Default to 720p
        self.resolution_combo.setCurrentIndex(index)

        self.upload_s3_checkbox.setChecked(self.settings.upload_to_s3)

        # Load S3 bucket
        from utils.constants import S3_BUCKET_OPTIONS
        bucket_values = list(S3_BUCKET_OPTIONS.values())
        try:
            bucket_index = bucket_values.index(self.settings.s3_bucket)
            self.bucket_combo.setCurrentIndex(bucket_index)
        except ValueError:
            self.bucket_combo.setCurrentIndex(0)  # Default to Production

        # Load upload type/method
        upload_type_index = 0 if self.settings.upload_method == "direct" else 1
        self.upload_type_combo.setCurrentIndex(upload_type_index)

        # Load upload mode
        upload_mode_index = 0 if self.settings.upload_mode == "immediate" else 1
        self.upload_mode_combo.setCurrentIndex(upload_mode_index)

        self.delete_after_upload_checkbox.setChecked(self.settings.delete_after_upload)
        self.delay_spinbox.setValue(self.settings.recording_delay)
        self.retries_spinbox.setValue(self.settings.max_download_retries)
        self.downloads_dir_input.setText(self.settings.downloads_directory)
        self.delete_zip_checkbox.setChecked(self.settings.delete_zip_after_unpack)

        # Update dependent widget states
        self.update_dependent_widget_states()

    def on_upload_s3_changed(self, state):
        """Handle upload to S3 checkbox state change"""
        self.update_dependent_widget_states()

    def on_upload_type_changed(self):
        """Handle upload type combo box change"""
        self.update_dependent_widget_states()

    def update_dependent_widget_states(self):
        """Update widget enabled states based on current selections"""
        upload_s3_enabled = self.upload_s3_checkbox.isChecked()
        upload_type = self.upload_type_combo.currentData()
        is_direct = upload_type == "direct"
        is_download_and_process = upload_type == "download_and_process"

        # Update description based on upload type
        if is_direct:
            self.upload_type_desc.setText("→ Raw files, no processing, uses device bandwidth")
        else:
            self.upload_type_desc.setText("→ Syncing, encoding, RRD packages, uses controller bandwidth")

        # Bucket selector depends on upload_s3
        self.bucket_combo.setEnabled(upload_s3_enabled)

        # Upload mode (immediate/manual) only applies to download_and_process
        self.upload_mode_combo.setEnabled(upload_s3_enabled and is_download_and_process)
        self.upload_mode_desc.setVisible(upload_s3_enabled and is_download_and_process)
        self.delete_after_upload_checkbox.setEnabled(upload_s3_enabled and is_download_and_process)

        # Show/hide conditional settings based on upload type
        self.upload_mode_combo.setVisible(is_download_and_process)
        self.upload_mode_desc.setVisible(is_download_and_process)
        self.delete_after_upload_checkbox.setVisible(is_download_and_process)

        # Processing options only apply to download_and_process
        self.av1_checkbox.setEnabled(is_download_and_process)
        self.resolution_combo.setEnabled(is_download_and_process)

        # If upload is disabled or direct mode, reset dependent options
        if not upload_s3_enabled or is_direct:
            self.delete_after_upload_checkbox.setChecked(False)

    def on_browse_directory(self):
        """Open directory browser dialog"""
        current_dir = self.downloads_dir_input.text() or str(Path.home() / "Downloads" / "multiCam")
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Downloads Directory",
            current_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if directory:
            self.downloads_dir_input.setText(directory)

    def on_save(self):
        """Save settings and close dialog"""
        # Update settings from UI
        self.settings.reencode_to_av1 = self.av1_checkbox.isChecked()

        # Map resolution combo index to setting value
        self.settings.max_video_resolution = RESOLUTION_OPTIONS[self.resolution_combo.currentIndex()]

        self.settings.upload_to_s3 = self.upload_s3_checkbox.isChecked()

        # Save selected bucket
        self.settings.s3_bucket = self.bucket_combo.currentData()

        # Get upload method from combo box
        self.settings.upload_method = self.upload_type_combo.currentData()

        # Get upload mode from combo box data
        self.settings.upload_mode = self.upload_mode_combo.currentData()

        self.settings.delete_after_upload = self.delete_after_upload_checkbox.isChecked()
        self.settings.recording_delay = self.delay_spinbox.value()
        self.settings.max_download_retries = self.retries_spinbox.value()
        self.settings.downloads_directory = self.downloads_dir_input.text().strip()
        self.settings.delete_zip_after_unpack = self.delete_zip_checkbox.isChecked()

        # Validate settings
        is_valid, error_message = self.settings.validate()
        if not is_valid:
            logger.error(f"Invalid settings: {error_message}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Invalid Settings", error_message)
            return

        # Save to file
        if self.settings.save():
            logger.info("Settings saved successfully")
            self.accept()
        else:
            logger.error("Failed to save settings")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Save Failed", "Failed to save settings to file.")
