"""Mode selection dialog for choosing between Recording and Syncing modes"""

import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PySide6.QtCore import Qt, Signal

logger = logging.getLogger(__name__)


class ModeSelectionDialog(QDialog):
    """Dialog for selecting application mode: Recording or Syncing"""

    # Signals
    recording_mode_selected = Signal()
    syncing_mode_selected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_mode = None
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI layout"""
        self.setWindowTitle("MultiCam Controller - Select Mode")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(40, 40, 40, 40)

        # Title
        title_label = QLabel("Welcome to MultiCam Controller")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("Please select a mode to continue:")
        subtitle_label.setStyleSheet("font-size: 14px; color: gray;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(subtitle_label)

        # Add spacing
        main_layout.addSpacing(30)

        # Recording button
        recording_btn = QPushButton("Recording Mode")
        recording_btn.setMinimumHeight(100)
        recording_btn.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                font-weight: bold;
                background-color: #4CAF50;
                color: white;
                border: 2px solid #45a049;
                border-radius: 8px;
                padding: 20px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        recording_btn.clicked.connect(self.on_recording_selected)
        main_layout.addWidget(recording_btn)

        # Recording description
        recording_desc = QLabel(
            "Control multiple cameras, start recordings,\n"
            "and manage file transfers from devices"
        )
        recording_desc.setStyleSheet("color: gray; font-size: 12px;")
        recording_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(recording_desc)

        # Add spacing between buttons
        main_layout.addSpacing(20)

        # Syncing button
        syncing_btn = QPushButton("Video Syncing")
        syncing_btn.setMinimumHeight(100)
        syncing_btn.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                font-weight: bold;
                background-color: #2196F3;
                color: white;
                border: 2px solid #0b7dda;
                border-radius: 8px;
                padding: 20px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
            QPushButton:pressed {
                background-color: #0969c3;
            }
        """)
        syncing_btn.clicked.connect(self.on_syncing_selected)
        main_layout.addWidget(syncing_btn)

        # Syncing description
        syncing_desc = QLabel(
            "Synchronize and process recorded videos,\n"
            "including ego camera footage"
        )
        syncing_desc.setStyleSheet("color: gray; font-size: 12px;")
        syncing_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(syncing_desc)

        # Add stretch to center content
        main_layout.addStretch()

    def on_recording_selected(self):
        """Handle recording mode selection"""
        logger.info("Recording mode selected")
        self.selected_mode = "recording"
        self.recording_mode_selected.emit()
        self.accept()

    def on_syncing_selected(self):
        """Handle syncing mode selection"""
        logger.info("Syncing mode selected")
        self.selected_mode = "syncing"
        self.syncing_mode_selected.emit()
        self.accept()

    def closeEvent(self, event):
        """Handle dialog close event"""
        if self.selected_mode is None:
            logger.info("Mode selection dialog closed without selection")
            # If no mode was selected, reject the dialog
            self.reject()
        event.accept()
