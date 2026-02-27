"""Main application window"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QLineEdit,
    QScrollArea,
    QComboBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
import asyncio
import logging

from typing import Optional
from multicam_common import CommandMessage, DeviceStatus

from models.app_state import AppState
from models.update_info import ReleaseInfo, UpdateProgress, UpdateState
from services.device_discovery import DeviceDiscovery
from services.device_communication import DeviceCommunication
from services.s3_manager import S3Manager
from services.file_transfer_manager import FileTransferManager
from services.direct_upload_manager import DirectUploadManager
from services.post_recording_orchestrator import PostRecordingOrchestrator
from services.device_status_manager import DeviceStatusManager
from services.update_manager import UpdateManager
from ui.widgets.file_status_widget import FileStatusWidget
from ui.widgets.device_status_widget import DeviceStatusWidget
from ui.dialogs.update_dialog import (
    UpdateAvailableDialog,
    UpdateProgressDialog,
    UpdateReadyDialog,
)
from utils.constants import TASK_OPTIONS

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, update_manager: Optional[UpdateManager] = None):
        super().__init__()

        # Update manager (optional, for auto-update functionality)
        self.update_manager = update_manager
        self._progress_dialog: Optional[UpdateProgressDialog] = None

        # Initialize services
        self.app_state = AppState()
        self.device_discovery = DeviceDiscovery(self.app_state)
        self.device_communication = DeviceCommunication()
        self.s3_manager = S3Manager(
            bucket_name=self.app_state.s3_bucket_name, region=self.app_state.s3_region
        )
        self.file_transfer_manager = FileTransferManager(
            self.app_state, self.device_communication, self.s3_manager
        )
        self.device_status_manager = DeviceStatusManager(
            self.app_state, self.device_communication, poll_interval=5.0
        )
        self.direct_upload_manager = DirectUploadManager(
            self.app_state, self.device_communication, self.s3_manager, self.device_status_manager
        )
        self.post_recording_orchestrator = PostRecordingOrchestrator(
            self.app_state, self.direct_upload_manager, self.file_transfer_manager
        )

        # Device widgets dictionary
        self.device_widgets = {}

        # Countdown timer
        self.countdown_seconds = 0
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.on_countdown_tick)

        # Recording duration timer
        self.recording_timer = QTimer()
        self.recording_timer.timeout.connect(self.on_recording_timer_tick)

        # Setup UI
        self.setup_ui()
        self.create_menu_bar()

        # Connect signals
        self.connect_signals()

        # Auto-start discovery
        self.device_discovery.start_discovery()

        # Start status polling after event loop is running
        QTimer.singleShot(100, self.device_status_manager.start_polling)

        # Check if update is already available (check started in main.py)
        if self.update_manager and self.update_manager.state == UpdateState.AVAILABLE:
            # Update was found before window was created, show dialog
            QTimer.singleShot(500, self._show_pending_update)

    def setup_ui(self):
        """Setup the main UI layout"""
        self.setWindowTitle("MultiCam Controller")
        self.setMinimumSize(900, 600)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)

        # Header
        header = self.create_header()
        main_layout.addWidget(header)

        # Content area
        content_layout = QHBoxLayout()

        # Left column - Device List
        left_group = QGroupBox("Devices")
        left_layout = QVBoxLayout()

        # Device container with scroll area
        self.device_container = QWidget()
        self.device_container_layout = QVBoxLayout(self.device_container)
        self.device_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.device_container_layout.setSpacing(5)
        self.device_container_layout.setContentsMargins(5, 5, 5, 5)

        scroll_area = QScrollArea()
        scroll_area.setWidget(self.device_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        left_layout.addWidget(scroll_area)

        # Discovery button
        self.discovery_btn = QPushButton("Start Discovery")
        self.discovery_btn.clicked.connect(self.on_start_discovery)
        left_layout.addWidget(self.discovery_btn)

        # Manual add button
        manual_btn = QPushButton("+ Manual Device")
        manual_btn.clicked.connect(self.on_add_manual_device)
        left_layout.addWidget(manual_btn)

        left_group.setLayout(left_layout)
        content_layout.addWidget(left_group, stretch=1)

        # Right column
        right_layout = QVBoxLayout()

        # Recording controls
        recording_group = self.create_recording_controls()
        right_layout.addWidget(recording_group)

        # Recording history
        recording_history_group = QGroupBox("Recording History")
        recording_history_layout = QVBoxLayout()
        self.file_status_widget = FileStatusWidget(self.file_transfer_manager, self.direct_upload_manager)
        recording_history_layout.addWidget(self.file_status_widget)
        recording_history_group.setLayout(recording_history_layout)
        right_layout.addWidget(recording_history_group, stretch=1)

        content_layout.addLayout(right_layout, stretch=1)

        main_layout.addLayout(content_layout)

    def create_header(self) -> QWidget:
        """Create header widget"""
        header = QWidget()
        layout = QVBoxLayout(header)

        title = QLabel("MultiCam Controller")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel("Control Multi-Cam enabled")
        subtitle.setStyleSheet("color: gray;")
        layout.addWidget(subtitle)

        return header

    def create_recording_controls(self) -> QGroupBox:
        """Create recording controls widget"""
        group = QGroupBox("Recording Controls")
        layout = QVBoxLayout()

        # Info label
        self.recording_info_label = QLabel()
        self.recording_info_label.setStyleSheet("color: gray; font-size: 11px;")
        self.update_recording_info_label()
        layout.addWidget(self.recording_info_label)

        # Recorder name input
        recorder_label = QLabel("Recorder Name:")
        layout.addWidget(recorder_label)

        self.recorder_name_input = QLineEdit()
        self.recorder_name_input.setPlaceholderText("Enter recorder name (min 2 characters)")
        self.recorder_name_input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Allow losing focus on click
        self.recorder_name_input.textChanged.connect(self.on_recorder_name_changed)
        self.recorder_name_input.returnPressed.connect(self.on_recorder_name_enter)
        layout.addWidget(self.recorder_name_input)

        # Task selection dropdown
        task_label = QLabel("Task:")
        layout.addWidget(task_label)

        self.task_combo = QComboBox()
        self.task_combo.addItem("-- Select Task --", "")  # Placeholder with empty value
        for value, display_name in TASK_OPTIONS:
            self.task_combo.addItem(display_name, value)
        self.task_combo.currentIndexChanged.connect(self.on_task_changed)
        layout.addWidget(self.task_combo)

        # Buttons
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Recording")
        self.start_btn.clicked.connect(self.on_start_recording)
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setEnabled(False)  # Disabled by default until name is entered
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Recording")
        self.stop_btn.clicked.connect(self.on_stop_recording)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)

        # Recording duration timer label
        self.recording_duration_label = QLabel("")
        self.recording_duration_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3;")
        self.recording_duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recording_duration_label.setMinimumHeight(30)
        layout.addWidget(self.recording_duration_label)

        # Countdown label
        self.countdown_label = QLabel("")
        self.countdown_label.setStyleSheet("font-size: 20px; font-weight: bold; color: red;")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setMinimumHeight(40)
        layout.addWidget(self.countdown_label)

        group.setLayout(layout)
        return group

    def create_menu_bar(self):
        """Create menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Devices menu
        devices_menu = menubar.addMenu("&Devices")

        discover_action = QAction("&Discover Devices", self)
        discover_action.setShortcut("Ctrl+D")
        discover_action.triggered.connect(self.on_start_discovery)
        devices_menu.addAction(discover_action)

        add_manual_action = QAction("&Add Manual Device", self)
        add_manual_action.setShortcut("Ctrl+M")
        add_manual_action.triggered.connect(self.on_add_manual_device)
        devices_menu.addAction(add_manual_action)

        # Settings menu
        settings_menu = menubar.addMenu("&Settings")

        preferences_action = QAction("&Preferences...", self)
        preferences_action.setShortcut("Ctrl+,")
        preferences_action.triggered.connect(self.on_open_settings)
        settings_menu.addAction(preferences_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        self.check_updates_action = QAction("Check for &Updates...", self)
        self.check_updates_action.triggered.connect(self.on_check_for_updates)
        help_menu.addAction(self.check_updates_action)

    def connect_signals(self):
        """Connect signals between components"""
        self.app_state.status_changed.connect(self.on_status_changed)
        self.app_state.devices_changed.connect(self.update_device_list)
        self.app_state.recording_session.recording_state_changed.connect(
            self.on_recording_state_changed
        )
        self.app_state.settings_changed.connect(self.on_settings_changed)
        self.device_status_manager.device_status_updated.connect(self.on_device_status_updated)

        # Update manager signals
        if self.update_manager:
            self.update_manager.update_available.connect(self.on_update_available)
            self.update_manager.update_progress.connect(self.on_update_progress)
            self.update_manager.update_ready.connect(self.on_update_ready)
            self.update_manager.update_error.connect(self.on_update_error)

    def update_device_list(self):
        """Update the device list display"""
        # Remove widgets for devices no longer discovered
        for device_name in list(self.device_widgets.keys()):
            if device_name not in [d.name for d in self.app_state.discovered_devices]:
                widget = self.device_widgets.pop(device_name)
                self.device_container_layout.removeWidget(widget)
                widget.deleteLater()

        # Add widgets for new devices
        for device in self.app_state.discovered_devices:
            if device.name not in self.device_widgets:
                widget = DeviceStatusWidget(device)
                self.device_widgets[device.name] = widget
                self.device_container_layout.addWidget(widget)

                # Initialize with cached status if available
                status = self.device_status_manager.get_latest_status(device.name)
                if status:
                    widget.update_status(status)

        # Update start button state when device list changes
        self.update_start_button_state()

    def on_device_status_updated(self, device_name: str, status):
        """Handle device status update"""
        if device_name in self.device_widgets:
            self.device_widgets[device_name].update_status(status)
        # Update start button state since device readiness may have changed
        self.update_start_button_state()

    def on_status_changed(self, message: str):
        """Handle status message changes"""
        # Status bar removed - only logging status messages now
        logger.info(f"Status: {message}")

    def on_start_discovery(self):
        """Start device discovery"""
        self.device_discovery.start_discovery()
        self.discovery_btn.setText("Discovering...")
        self.discovery_btn.setEnabled(False)

        # Re-enable after timeout
        QTimer.singleShot(12000, lambda: self.discovery_btn.setEnabled(True))
        QTimer.singleShot(12000, lambda: self.discovery_btn.setText("Start Discovery"))

    def on_add_manual_device(self):
        """Add a manual device (simplified - hardcoded for now)"""
        # TODO: Show dialog to get IP and port
        from PySide6.QtWidgets import QInputDialog

        ip, ok = QInputDialog.getText(self, "Add Manual Device", "Enter IP address:")
        if ok and ip:
            port, ok = QInputDialog.getInt(self, "Add Manual Device", "Enter port:", 8080, 1, 65535)
            if ok:
                self.device_discovery.add_manual_device(ip, port)

    def on_open_settings(self):
        """Open settings dialog"""
        from ui.dialogs import SettingsDialog

        dialog = SettingsDialog(self.app_state.settings, self)
        if dialog.exec():
            old_bucket = self.app_state.settings.s3_bucket

            # Settings were saved, update app state
            self.app_state.update_settings(dialog.settings)
            logger.info("Settings updated")

            # Check if bucket changed - reinitialize S3Manager
            if old_bucket != dialog.settings.s3_bucket:
                from utils.constants import S3_BUCKET_DISPLAY_NAMES
                bucket_name = S3_BUCKET_DISPLAY_NAMES.get(dialog.settings.s3_bucket, "Unknown")
                logger.info(f"S3 bucket changed from {old_bucket} to {dialog.settings.s3_bucket}")

                # Reinitialize S3Manager with new bucket
                self.s3_manager = S3Manager(
                    bucket_name=self.app_state.s3_bucket_name,
                    region=self.app_state.s3_region
                )
                # Update managers that depend on S3Manager
                self.file_transfer_manager.s3_manager = self.s3_manager
                self.direct_upload_manager.s3_manager = self.s3_manager

                self.app_state.update_status(f"S3 bucket changed to: {bucket_name}")

            # Update UI to reflect new settings
            self.update_recording_info_label()

    def update_start_button_state(self):
        """Update start button enabled state based on current conditions"""
        has_valid_name = len(self.recorder_name_input.text().strip()) >= 2
        has_task_selected = bool(self.task_combo.currentData())
        has_devices = len(self.app_state.discovered_devices) > 0
        is_not_recording = not self.app_state.recording_session.isRecording
        all_devices_ready = self.device_status_manager.are_all_devices_ready()
        self.start_btn.setEnabled(
            has_valid_name and has_task_selected and has_devices and is_not_recording and all_devices_ready
        )

    def on_recorder_name_changed(self, text: str):
        """Handle recorder name input changes"""
        self.update_start_button_state()

    def on_task_changed(self, index: int):
        """Handle task selection changes"""
        self.update_start_button_state()

    def on_recorder_name_enter(self):
        """Handle Enter key pressed in recorder name input"""
        # Clear focus from the text input
        self.recorder_name_input.clearFocus()

    def on_start_recording(self):
        """Start recording on all devices"""
        if not self.app_state.discovered_devices:
            self.app_state.update_status("No devices available. Discover devices first.")
            return

        # Get recorder name and task
        recorder_name = self.recorder_name_input.text().strip()
        task = self.task_combo.currentData()

        self.app_state.update_status("Starting recording...")
        self.app_state.recording_session.start_recording(recorder_name, task)

        # Update UI
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # Start countdown using delay from settings
        self.countdown_seconds = int(self.app_state.settings.recording_delay)
        self.countdown_timer.start(1000)

        # Send command
        asyncio.create_task(self.execute_recording_start())

    def on_countdown_tick(self):
        """Handle countdown timer tick"""
        if self.countdown_seconds > 0:
            self.countdown_label.setText(f"Recording starts in {self.countdown_seconds}...")
            self.countdown_seconds -= 1
        else:
            self.countdown_timer.stop()
            self.countdown_label.setText("")
            # Start the recording duration timer once countdown finishes
            self.recording_timer.start(1000)

    def on_recording_timer_tick(self):
        """Handle recording timer tick - updates the elapsed recording time"""
        if self.app_state.recording_session.isRecording and self.app_state.recording_session.recordingStartTime:
            from datetime import datetime
            elapsed = datetime.now() - self.app_state.recording_session.recordingStartTime
            total_seconds = int(elapsed.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            if hours > 0:
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                time_str = f"{minutes:02d}:{seconds:02d}"
            
            self.recording_duration_label.setText(f"Recording: {time_str}")
        else:
            self.recording_timer.stop()
            self.recording_duration_label.setText("")

    async def execute_recording_start(self):
        """Execute the recording start command"""
        try:
            logger.info(f"Starting recording on {len(self.app_state.discovered_devices)} devices")

            command = CommandMessage.start_recording()
            results = await self.device_communication.send_command_to_all_devices(
                self.app_state.discovered_devices, command, sync_delay=self.app_state.settings.recording_delay
            )

            # Count successful responses
            success_count = sum(1 for response in results.values() if DeviceStatus.is_success(response.status))

            logger.info(f"Recording start results: {success_count}/{len(results)} successful")

            if success_count > 0:
                self.app_state.update_status(f"Recording... Started on {success_count} device(s)")
            else:
                self.app_state.update_status("Failed to start recording")
                self.app_state.recording_session.reset_session()
                self.start_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)

        except Exception as e:
            logger.error(f"Recording start exception: {e}")
            self.app_state.update_status(f"Recording start failed: {str(e)}")
            self.app_state.recording_session.reset_session()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def on_stop_recording(self):
        """Stop recording on all devices"""
        # Stop recording timer and clear display immediately
        self.recording_timer.stop()
        self.recording_duration_label.setText("")

        # Disable stop button immediately (start button already disabled)
        self.stop_btn.setEnabled(False)

        asyncio.create_task(self.execute_recording_stop())

    async def execute_recording_stop(self):
        """Execute the recording stop command"""
        try:
            self.app_state.update_status("Stopping recording...")

            command = CommandMessage.stop_recording()
            results = await self.device_communication.send_command_to_all_devices(
                self.app_state.discovered_devices, command
            )

            # Extract file names from responses (STOP_RECORDING now returns fileName)
            file_ids = {}
            for device_name, response in results.items():
                # Try to get fileName from StopRecordingResponse
                file_name = getattr(response, 'fileName', None)
                logger.debug(f"Processing response from {device_name}: fileName={file_name}")
                if file_name:
                    file_ids[device_name] = file_name
                    logger.info(f"Got file name from {device_name}: {file_name}")
                else:
                    logger.warning(f"No fileName in response from {device_name}")

            self.app_state.recording_session.stop_recording(file_ids)

            if file_ids:
                self.app_state.update_status(
                    f"Recording stopped. {len(file_ids)} files received."
                )

                # Use orchestrator to handle post-recording workflow
                await self.post_recording_orchestrator.handle_recording_stopped(
                    file_ids, self.app_state.recording_session.sessionId
                )
            else:
                self.app_state.update_status("Recording stopped, but no files returned.")

        except Exception as e:
            logger.error(f"Recording stop exception: {e}")
            self.app_state.update_status(f"Recording stop failed: {str(e)}")

        finally:
            # Re-enable start button
            self.start_btn.setEnabled(True)

    def on_recording_state_changed(self, is_recording: bool):
        """Handle recording state changes"""
        self.update_start_button_state()
        self.stop_btn.setEnabled(is_recording)

    def on_settings_changed(self):
        """Handle settings changes"""
        logger.info("Settings changed, updating UI")
        self.update_recording_info_label()

    def update_recording_info_label(self):
        """Update the recording info label with current settings"""
        delay = self.app_state.settings.recording_delay
        self.recording_info_label.setText(f"Synchronized recording with {delay:.1f}-second delay")

    # Update management methods
    def on_check_for_updates(self):
        """Manually check for updates"""
        if self.update_manager:
            self.update_manager.check_for_updates_async()

    def _show_pending_update(self):
        """Show update dialog for an update that was found before window was created"""
        if self.update_manager and self.update_manager.latest_release:
            self.on_update_available(self.update_manager.latest_release)

    def on_update_available(self, release: ReleaseInfo):
        """Handle update available signal"""
        current_version = self.update_manager.current_version

        dialog = UpdateAvailableDialog(current_version, release, self)
        if dialog.exec() and dialog.download_requested:
            # User wants to download
            self._progress_dialog = UpdateProgressDialog(release, self)
            self._progress_dialog.show()
            self.update_manager.download_update(release)

    def on_update_progress(self, progress: UpdateProgress):
        """Handle download progress update"""
        if self._progress_dialog:
            self._progress_dialog.update_progress(progress)

    def on_update_ready(self, new_app_path: str):
        """Handle update ready signal"""
        if self._progress_dialog:
            self._progress_dialog.set_complete()
            self._progress_dialog.close()
            self._progress_dialog = None

        # Show ready dialog
        version = self.update_manager.latest_release.version if self.update_manager.latest_release else "Unknown"
        dialog = UpdateReadyDialog(version, self)
        if dialog.exec() and dialog.restart_requested:
            # Apply update and restart
            self.update_manager.apply_and_restart()

    def on_update_error(self, error: str):
        """Handle update error"""
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(self, "Update Error", f"An error occurred during update:\n\n{error}")

    def closeEvent(self, event):
        """Handle window close"""
        # Stop discovery
        if self.app_state.is_discovering:
            self.device_discovery.stop_discovery()

        # Stop status polling
        self.device_status_manager.stop_polling()

        # Cleanup update manager
        if self.update_manager:
            self.update_manager.cleanup()

        event.accept()
