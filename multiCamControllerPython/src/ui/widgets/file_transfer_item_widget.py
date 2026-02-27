"""Widget for displaying individual file transfer status"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
)
from PySide6.QtCore import Qt, Signal as pyqtSignal

from models.file_transfer import FileTransferItem, TransferState


class FileTransferItemWidget(QWidget):
    """Widget displaying a single file transfer with progress and controls"""

    retry_clicked = pyqtSignal(object)  # FileTransferItem
    cancel_clicked = pyqtSignal(object)  # FileTransferItem

    def __init__(self, item: FileTransferItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setup_ui()
        self.update_display()

    def setup_ui(self):
        """Setup the UI layout"""
        main_layout = QHBoxLayout(self)
        # Add left indentation to visually nest under session header
        main_layout.setContentsMargins(20, 5, 8, 5)

        # Set fixed height to prevent expanding
        self.setMaximumHeight(60)
        self.setMinimumHeight(60)

        # Left section - File info and progress
        left_layout = QVBoxLayout()

        # Top row: filename + progress bar
        top_row = QHBoxLayout()

        self.file_label = QLabel()
        self.file_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.file_label.setMinimumWidth(200)
        top_row.addWidget(self.file_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMaximumHeight(18)
        self.progress_bar.setMinimumWidth(150)
        top_row.addWidget(self.progress_bar, stretch=1)

        left_layout.addLayout(top_row)

        # Status text (speed, ETA, error)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-size: 10px; color: #666;")
        self.status_label.setWordWrap(True)
        left_layout.addWidget(self.status_label)

        main_layout.addLayout(left_layout, stretch=1)

        # Right section - Action buttons
        button_layout = QVBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setMaximumWidth(60)
        self.retry_btn.setMaximumHeight(25)
        self.retry_btn.clicked.connect(lambda: self.retry_clicked.emit(self.item))
        button_layout.addWidget(self.retry_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMaximumWidth(60)
        self.cancel_btn.setMaximumHeight(25)
        self.cancel_btn.clicked.connect(lambda: self.cancel_clicked.emit(self.item))
        button_layout.addWidget(self.cancel_btn)

        button_layout.addStretch()
        main_layout.addLayout(button_layout)

    def update_display(self):
        """Update the display based on current transfer state"""
        # Check if this is a direct upload item (uploaded directly from device to cloud, no local file)
        is_direct_upload = self.item.state == TransferState.UPLOADED and not self.item.localPath
        
        # Extract filename from localPath if available, otherwise use fileId
        if self.item.fileId == "UPLOAD_SESSION_TO_S3":
            # Special display name for the upload task
            filename = "Upload to S3"
        elif self.item.localPath:
            filename = Path(self.item.localPath).name
        else:
            # For direct uploads, just show device name
            if is_direct_upload:
                filename = f"Device: {self.item.deviceName}"
            else:
                # Use last part of fileId or truncate if too long
                filename = self.item.fileId.split('/')[-1]
                if len(filename) > 50:
                    filename = filename[:47] + "..."

        self.file_label.setText(filename)

        # For direct uploads, hide progress bar and status text, reduce height
        if is_direct_upload:
            self.progress_bar.setVisible(False)
            self.status_label.setVisible(False)
            self.setMaximumHeight(30)
            self.setMinimumHeight(30)
        else:
            self.progress_bar.setVisible(True)
            self.status_label.setVisible(True)
            self.setMaximumHeight(60)
            self.setMinimumHeight(60)
            
            # Progress bar - use overall_progress (0-100% for downloads or upload tasks)
            self.progress_bar.setValue(int(self.item.overall_progress))

            # Update progress bar color based on state
            if self.item.state == TransferState.FAILED:
                self.progress_bar.setStyleSheet(
                    "QProgressBar::chunk { background-color: #dc3545; }"
                )
            elif self.item.state == TransferState.UPLOADED:
                self.progress_bar.setStyleSheet(
                    "QProgressBar::chunk { background-color: #28a745; }"
                )
            elif self.item.state == TransferState.CANCELLED:
                self.progress_bar.setStyleSheet(
                    "QProgressBar::chunk { background-color: #6c757d; }"
                )
            elif self.item.state in [TransferState.DOWNLOADING, TransferState.UPLOADING]:
                self.progress_bar.setStyleSheet(
                    "QProgressBar::chunk { background-color: #007bff; }"
                )
            elif self.item.state == TransferState.RETRYING:
                self.progress_bar.setStyleSheet(
                    "QProgressBar::chunk { background-color: #ffc107; }"
                )
            else:
                self.progress_bar.setStyleSheet("")

            # Status text
            self.status_label.setText(self.item.status_text)

            # Error styling
            if self.item.state == TransferState.FAILED:
                self.status_label.setStyleSheet("font-size: 10px; color: #dc3545; font-weight: bold;")
            else:
                self.status_label.setStyleSheet("font-size: 10px; color: #666;")

        # Button visibility
        self.retry_btn.setVisible(self.item.state == TransferState.FAILED and self.item.can_retry)
        self.cancel_btn.setVisible(
            self.item.state in [TransferState.PENDING, TransferState.DOWNLOADING, TransferState.UPLOADING, TransferState.RETRYING]
        )

    def update_item(self, item: FileTransferItem):
        """Update with new item data"""
        self.item = item
        self.update_display()
