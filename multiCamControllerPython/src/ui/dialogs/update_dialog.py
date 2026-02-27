"""Update notification and progress dialogs"""

import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt

from models.update_info import ReleaseInfo, UpdateProgress

logger = logging.getLogger(__name__)


def format_bytes(size: int) -> str:
    """Format bytes as human-readable string"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class UpdateAvailableDialog(QDialog):
    """Dialog shown when an update is available"""

    def __init__(self, current_version: str, release: ReleaseInfo, parent=None):
        super().__init__(parent)
        self.release = release
        self.download_requested = False
        self.setup_ui(current_version, release)

    def setup_ui(self, current_version: str, release: ReleaseInfo):
        """Setup the UI layout"""
        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.setMinimumHeight(350)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Header
        header = QLabel("A new version of MultiCam Controller is available!")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Version info
        version_layout = QVBoxLayout()
        version_layout.setSpacing(5)

        current_label = QLabel(f"Current version: {current_version}")
        current_label.setStyleSheet("color: gray;")
        version_layout.addWidget(current_label)

        new_label = QLabel(f"New version: {release.version}")
        new_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        version_layout.addWidget(new_label)

        size_label = QLabel(f"Download size: {format_bytes(release.file_size)}")
        size_label.setStyleSheet("color: gray; font-size: 11px;")
        version_layout.addWidget(size_label)

        layout.addLayout(version_layout)

        # Release notes
        notes_label = QLabel("Release Notes:")
        notes_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(notes_label)

        notes_text = QTextEdit()
        notes_text.setReadOnly(True)
        notes_text.setMarkdown(release.release_notes or "No release notes available.")
        notes_text.setMinimumHeight(150)
        layout.addWidget(notes_text)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        remind_later_btn = QPushButton("Remind Later")
        remind_later_btn.clicked.connect(self.reject)
        button_layout.addWidget(remind_later_btn)

        download_btn = QPushButton("Download && Install")
        download_btn.setDefault(True)
        download_btn.clicked.connect(self.on_download)
        button_layout.addWidget(download_btn)

        layout.addLayout(button_layout)

    def on_download(self):
        """Handle download button click"""
        self.download_requested = True
        self.accept()


class UpdateProgressDialog(QDialog):
    """Dialog showing download progress"""

    def __init__(self, release: ReleaseInfo, parent=None):
        super().__init__(parent)
        self.release = release
        self.cancelled = False
        self.setup_ui(release)

    def setup_ui(self, release: ReleaseInfo):
        """Setup the UI layout"""
        self.setWindowTitle("Downloading Update")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setFixedHeight(150)

        # Prevent closing via X button during download
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Status label
        self.status_label = QLabel(f"Downloading MultiCam Controller {release.version}...")
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Progress details
        self.details_label = QLabel("Starting download...")
        self.details_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.details_label)

        # Cancel button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.on_cancel)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def update_progress(self, progress: UpdateProgress):
        """Update the progress display"""
        percent = int(progress.percent)
        self.progress_bar.setValue(percent)

        downloaded = format_bytes(progress.bytes_downloaded)
        total = format_bytes(progress.total_bytes)
        speed = format_bytes(int(progress.download_speed)) + "/s"

        eta = progress.eta_seconds
        if eta and eta < 3600:
            eta_str = f"{int(eta // 60)}:{int(eta % 60):02d} remaining"
        elif eta:
            eta_str = "Calculating..."
        else:
            eta_str = ""

        self.details_label.setText(f"{downloaded} / {total}  ({speed})  {eta_str}")

    def on_cancel(self):
        """Handle cancel button click"""
        self.cancelled = True
        self.reject()

    def set_complete(self):
        """Update UI to show download complete"""
        self.status_label.setText("Download complete!")
        self.progress_bar.setValue(100)
        self.details_label.setText("Preparing update...")
        self.cancel_btn.setEnabled(False)


class UpdateReadyDialog(QDialog):
    """Dialog shown when update is ready to install"""

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.restart_requested = False
        self.setup_ui(version)

    def setup_ui(self, version: str):
        """Setup the UI layout"""
        self.setWindowTitle("Update Ready")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Header
        header = QLabel("Update Downloaded Successfully!")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        # Message
        message = QLabel(
            f"MultiCam Controller {version} has been downloaded and is ready to install.\n\n"
            "The application will restart to apply the update."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        # Warning
        warning = QLabel(
            "Please save any work before continuing."
        )
        warning.setStyleSheet("color: #FF9800; font-style: italic;")
        layout.addWidget(warning)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        later_btn = QPushButton("Later")
        later_btn.clicked.connect(self.reject)
        button_layout.addWidget(later_btn)

        restart_btn = QPushButton("Restart Now")
        restart_btn.setDefault(True)
        restart_btn.clicked.connect(self.on_restart)
        button_layout.addWidget(restart_btn)

        layout.addLayout(button_layout)

    def on_restart(self):
        """Handle restart button click"""
        self.restart_requested = True
        self.accept()
