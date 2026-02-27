"""Main file transfer status widget with overall progress"""

from datetime import datetime
from collections import defaultdict
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QButtonGroup,
    QProgressBar,
)
from PySide6.QtCore import Qt, Slot, QTimer

from models.file_transfer import FileTransferItem, TransferState
from services.file_transfer_manager import FileTransferManager
from .file_transfer_item_widget import FileTransferItemWidget
from .session_header_widget import SessionHeaderWidget

# Import for type hinting only
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from services.direct_upload_manager import DirectUploadManager


class FileStatusWidget(QWidget):
    """Main widget for displaying file transfer status with overall progress"""

    def __init__(self, transfer_manager: FileTransferManager, direct_upload_manager: 'DirectUploadManager' = None, parent=None):
        super().__init__(parent)
        self.transfer_manager = transfer_manager
        self.direct_upload_manager = direct_upload_manager
        self.item_widgets = {}  # Map fileId (str) to FileTransferItemWidget
        self.session_headers = {}  # Map sessionId (str) to SessionHeaderWidget
        self.session_items = defaultdict(list)  # Map sessionId to list of fileIds
        self.session_expanded = {}  # Map sessionId to expanded state (bool)
        self.session_types = {}  # Map sessionId to session type (e.g., "D2C")
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        """Setup the UI layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Scroll area for transfer items
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.StyledPanel)

        # Container for transfer items
        self.items_container = QWidget()
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.items_layout.setSpacing(2)
        self.items_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area.setWidget(self.items_container)
        main_layout.addWidget(scroll_area)

        # Global upload progress bar (hidden by default)
        self.create_upload_progress(main_layout)

        # Control buttons at bottom
        self.create_controls(main_layout)

    def create_upload_progress(self, parent_layout):
        """Create global upload progress section"""
        self.upload_progress_widget = QWidget()
        upload_layout = QVBoxLayout(self.upload_progress_widget)
        upload_layout.setContentsMargins(5, 5, 5, 5)
        upload_layout.setSpacing(3)

        # Status label
        self.upload_status_label = QLabel("Uploading to S3...")
        self.upload_status_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        upload_layout.addWidget(self.upload_status_label)

        # Progress bar
        self.upload_progress_bar = QProgressBar()
        self.upload_progress_bar.setMinimum(0)
        self.upload_progress_bar.setMaximum(100)
        self.upload_progress_bar.setTextVisible(True)
        self.upload_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 3px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #5cb85c;
                border-radius: 2px;
            }
        """)
        upload_layout.addWidget(self.upload_progress_bar)

        # Details label (current file, speed, ETA)
        self.upload_details_label = QLabel("")
        self.upload_details_label.setStyleSheet("color: gray; font-size: 10px;")
        upload_layout.addWidget(self.upload_details_label)

        parent_layout.addWidget(self.upload_progress_widget)
        self.upload_progress_widget.setVisible(False)  # Hidden by default

    def create_controls(self, parent_layout):
        """Create control buttons"""
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 5, 0, 0)

        # Upload All Pending button
        self.upload_all_pending_btn = QPushButton("Upload All Pending")
        self.upload_all_pending_btn.setMinimumWidth(150)
        self.upload_all_pending_btn.setStyleSheet("""
            QPushButton {
                background-color: #5cb85c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4cae4c;
            }
            QPushButton:pressed {
                background-color: #3d8b3d;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.upload_all_pending_btn.clicked.connect(self.on_upload_all_pending)
        button_row.addWidget(self.upload_all_pending_btn)

        button_row.addStretch()
        parent_layout.addLayout(button_row)

    def connect_signals(self):
        """Connect signals from transfer manager"""
        self.transfer_manager.transfer_state_changed.connect(self.on_transfer_state_changed)
        self.transfer_manager.all_transfers_complete.connect(self.on_all_transfers_complete)
        self.transfer_manager.pending_uploads_manager.pending_uploads_changed.connect(self.update_summary)

        # Connect global upload progress signals
        self.transfer_manager.global_upload_started.connect(self.on_global_upload_started)
        self.transfer_manager.global_upload_progress.connect(self.on_global_upload_progress)
        self.transfer_manager.global_upload_finished.connect(self.on_global_upload_finished)

        # Connect direct upload manager signals if available
        if self.direct_upload_manager:
            self.direct_upload_manager.transfer_state_changed.connect(self.on_transfer_state_changed)

        # Restore pending sessions from disk after signals are connected
        self.transfer_manager.restore_pending_sessions()

        # Update summary to reflect restored sessions
        self.update_summary()

    @Slot(object)
    def on_transfer_state_changed(self, item: FileTransferItem):
        """Handle transfer state change"""
        # Use fileId as the key (hashable)
        item_key = item.fileId
        session_id = item.sessionId

        # Detect session type based on upload_source
        if session_id not in self.session_types and item.upload_source == "device":
            self.session_types[session_id] = "D2C"

        # Create session header if it doesn't exist
        if session_id not in self.session_headers:
            # Use item's started_at or current time for session timestamp
            timestamp = item.started_at if item.started_at else datetime.now()

            # Try to get recording duration from app state or pending uploads
            recording_duration_seconds = None
            if hasattr(self.transfer_manager, 'app_state') and self.transfer_manager.app_state.recording_session.sessionId == session_id:
                recording_duration_seconds = self.transfer_manager.app_state.recording_session.get_duration_seconds()
            else:
                # Check pending uploads for restored sessions
                pending_session = self.transfer_manager.pending_uploads_manager.get_session(session_id)
                if pending_session:
                    recording_duration_seconds = pending_session.recording_duration_seconds

            # Get session type (e.g., "D2C" for direct-to-cloud)
            session_type = self.session_types.get(session_id)

            session_header = SessionHeaderWidget(
                session_id,
                timestamp,
                0,
                recording_duration_seconds=recording_duration_seconds,
                get_session_dir_callback=self.transfer_manager.get_session_directory,
                session_type=session_type
            )
            session_header.toggled.connect(self.on_session_toggled)

            self.session_headers[session_id] = session_header
            self.items_layout.addWidget(session_header)

            # Collapse all other sessions before expanding this new one
            for other_session_id in list(self.session_expanded.keys()):
                if other_session_id != session_id:
                    self.session_expanded[other_session_id] = False
                    self.session_headers[other_session_id].set_expanded(False)
                    # Hide all items in the collapsed session
                    for file_id in self.session_items[other_session_id]:
                        if file_id in self.item_widgets:
                            self.item_widgets[file_id].setVisible(False)

            # Expand the new session
            self.session_expanded[session_id] = True
            session_header.set_expanded(True)

        # Create or update widget for this item
        if item_key not in self.item_widgets:
            # Create new widget
            widget = FileTransferItemWidget(item)
            widget.retry_clicked.connect(self.on_retry_item)
            widget.cancel_clicked.connect(self.on_cancel_item)

            self.item_widgets[item_key] = widget
            self.session_items[session_id].append(item_key)

            # Insert widget after session header
            header_index = self.items_layout.indexOf(self.session_headers[session_id])
            # Count how many items already in this session to know where to insert
            insert_index = header_index + 1 + len([fid for fid in self.session_items[session_id] if fid in self.item_widgets and fid != item_key])
            self.items_layout.insertWidget(insert_index, widget)

            # Show/hide based on expanded state
            widget.setVisible(self.session_expanded[session_id])
        else:
            # Update existing widget
            widget = self.item_widgets[item_key]
            widget.update_item(item)

        # Update summary
        self.update_summary()

    @Slot(int, int)
    def on_all_transfers_complete(self, succeeded: int, failed: int):
        """Handle all transfers complete"""
        self.update_summary()

    def update_summary(self):
        """Update button states"""
        # Update upload all pending button
        pending_count = len(self.transfer_manager.pending_uploads_manager.get_all_sessions())
        if pending_count > 0:
            summary = self.transfer_manager.pending_uploads_manager.get_summary_text()
            self.upload_all_pending_btn.setText(f"Upload All Pending ({summary})")
            self.upload_all_pending_btn.setEnabled(True)
        else:
            self.upload_all_pending_btn.setText("Upload All Pending")
            self.upload_all_pending_btn.setEnabled(False)

    def on_session_toggled(self, session_id: str, is_expanded: bool):
        """Handle session expand/collapse toggle"""
        self.session_expanded[session_id] = is_expanded

        # Show/hide all items in this session
        for file_id in self.session_items[session_id]:
            if file_id in self.item_widgets:
                self.item_widgets[file_id].setVisible(is_expanded)

    def on_retry_item(self, item: FileTransferItem):
        """Handle retry button click for an item"""
        self.transfer_manager.retry_transfer(item)

    def on_cancel_item(self, item: FileTransferItem):
        """Handle cancel button click for an item"""
        self.transfer_manager.cancel_transfer(item)

    def on_upload_all_pending(self):
        """Handle Upload All Pending button click"""
        import asyncio

        # Disable the button while uploading
        self.upload_all_pending_btn.setEnabled(False)

        async def do_upload():
            await self.transfer_manager.upload_all_pending_sessions()
            # Note: button state will be updated by update_summary() called from global_upload_finished

        # Schedule the coroutine with proper event loop integration
        asyncio.create_task(do_upload())

    @Slot()
    def on_global_upload_started(self):
        """Handle global upload started"""
        self.upload_progress_widget.setVisible(True)
        self.upload_progress_bar.setValue(0)
        self.upload_status_label.setText("Uploading to S3...")
        self.upload_details_label.setText("Preparing upload...")

    @Slot(int, int, int, str)
    def on_global_upload_progress(self, current_file: int, total_files: int, progress_percent: int, current_filename: str):
        """Handle global upload progress update"""
        self.upload_progress_bar.setValue(progress_percent)

        # Show both file progress and percentage
        self.upload_status_label.setText(f"Uploading to S3... {progress_percent}% ({current_file}/{total_files} files)")

        # Extract just the filename from the path
        from pathlib import Path
        filename = Path(current_filename).name
        self.upload_details_label.setText(f"Current: {filename}")

    @Slot(bool)
    def on_global_upload_finished(self, success: bool):
        """Handle global upload finished"""
        if success:
            self.upload_status_label.setText("Upload complete!")
            self.upload_progress_bar.setValue(100)
            self.upload_details_label.setText("All files uploaded successfully")
        else:
            self.upload_status_label.setText("Upload failed")
            self.upload_details_label.setText("Some files failed to upload")

        # Hide progress bar after a delay
        QTimer.singleShot(3000, lambda: self.upload_progress_widget.setVisible(False))

        # Update the UI to reflect changes
        self.update_summary()
