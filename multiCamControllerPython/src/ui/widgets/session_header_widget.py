"""Collapsible session header widget"""

from datetime import datetime
from typing import Callable, Optional
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal as pyqtSignal


class SessionHeaderWidget(QWidget):
    """Collapsible header for a recording session"""

    toggled = pyqtSignal(str, bool)  # sessionId, is_expanded

    def __init__(
        self,
        session_id: str,
        timestamp: datetime,
        file_count: int,
        recording_duration_seconds: Optional[float] = None,
        get_session_dir_callback: Optional[Callable[[str], Optional[str]]] = None,
        session_type: Optional[str] = None,  # e.g., "D2C" for direct-to-cloud
        parent=None
    ):
        super().__init__(parent)
        self.session_id = session_id
        self.timestamp = timestamp
        self.file_count = file_count
        self.recording_duration_seconds = recording_duration_seconds
        self.is_expanded = False  # Start collapsed by default
        self.get_session_dir_callback = get_session_dir_callback
        self.session_type = session_type
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI layout"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)

        # Set fixed height
        self.setMaximumHeight(35)
        self.setMinimumHeight(35)

        # Background color
        self.setStyleSheet("""
            SessionHeaderWidget {
                background-color: #f0f0f0;
                border-radius: 3px;
            }
        """)

        # Expand/collapse button (start with ▶ since collapsed by default)
        self.toggle_btn = QPushButton("▶")
        self.toggle_btn.setMaximumWidth(20)
        self.toggle_btn.setMaximumHeight(20)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-radius: 2px;
            }
        """)
        self.toggle_btn.clicked.connect(self.on_toggle)
        layout.addWidget(self.toggle_btn)

        # Session info label with ID, timestamp, and duration
        time_str = self.timestamp.strftime("%b %d, %I:%M %p")
        session_id_short = self.session_id[:8]

        # Format duration
        duration_str = ""
        if self.recording_duration_seconds is not None:
            total_seconds = int(self.recording_duration_seconds)
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            duration_str = f" - Duration: {minutes}:{seconds:02d}"

        # Add session type prefix if provided
        type_prefix = f"[{self.session_type}] " if self.session_type else ""

        self.label = QLabel(f"{type_prefix}ID: {session_id_short} - {time_str}{duration_str}")
        self.label.setStyleSheet("font-weight: bold; font-size: 11px; color: #333;")
        layout.addWidget(self.label)

        layout.addStretch()

        # Open folder button (only show if there's actually a directory)
        if self.get_session_dir_callback:
            session_dir = self.get_session_dir_callback(self.session_id)
            if session_dir:  # Only add button if directory exists
                self.open_btn = QPushButton("Open")
                self.open_btn.setMaximumWidth(60)
                self.open_btn.setMaximumHeight(22)
                self.open_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4a90e2;
                        color: white;
                        border: none;
                        border-radius: 3px;
                        font-size: 10px;
                        padding: 2px 8px;
                    }
                    QPushButton:hover {
                        background-color: #357abd;
                    }
                    QPushButton:pressed {
                        background-color: #2868a8;
                    }
                """)
                self.open_btn.clicked.connect(self.on_open_folder)
                layout.addWidget(self.open_btn)

    def on_toggle(self):
        """Toggle expand/collapse state"""
        self.is_expanded = not self.is_expanded
        self.toggle_btn.setText("▼" if self.is_expanded else "▶")
        self.toggled.emit(self.session_id, self.is_expanded)

    def set_expanded(self, expanded: bool):
        """Set the expanded state without emitting signal"""
        self.is_expanded = expanded
        self.toggle_btn.setText("▼" if expanded else "▶")

    def on_open_folder(self):
        """Open the session folder in Finder/Explorer"""
        if self.get_session_dir_callback:
            from utils.file_utils import open_folder_in_explorer

            session_dir = self.get_session_dir_callback(self.session_id)
            if session_dir:
                open_folder_in_explorer(session_dir)
            else:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Could not find session directory for {self.session_id}")
