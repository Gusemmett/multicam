"""Main window for video syncing workflow"""

import logging
from typing import Optional
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QMessageBox
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction

from models.app_settings import AppSettings
from models.update_info import ReleaseInfo, UpdateProgress, UpdateState
from services.update_manager import UpdateManager
from ui.syncing_setup_window import SyncingSetupWindow
from ui.syncing_orchestrator import SyncingOrchestrator
from ui.dialogs.update_dialog import (
    UpdateAvailableDialog,
    UpdateProgressDialog,
    UpdateReadyDialog,
)

logger = logging.getLogger(__name__)


class SyncingMainWindow(QMainWindow):
    """Main window that manages the entire syncing workflow"""

    def __init__(self, settings: AppSettings, update_manager: Optional[UpdateManager] = None, parent=None):
        super().__init__(parent)
        self.settings = settings

        # Update manager (optional, for auto-update functionality)
        self.update_manager = update_manager
        self._progress_dialog: Optional[UpdateProgressDialog] = None

        # Create orchestrator as child of this window
        self.orchestrator = SyncingOrchestrator(settings, parent=self)

        # Setup UI
        self.setup_ui()
        self.create_menu_bar()

        # Connect orchestrator signals
        self.orchestrator.workflow_completed.connect(self.on_workflow_completed)
        self.orchestrator.workflow_cancelled.connect(self.on_workflow_cancelled)

        # Connect update manager signals
        if self.update_manager:
            self.update_manager.update_available.connect(self.on_update_available)
            self.update_manager.update_progress.connect(self.on_update_progress)
            self.update_manager.update_ready.connect(self.on_update_ready)
            self.update_manager.update_error.connect(self.on_update_error)

            # Check if update is already available (check started in main.py)
            if self.update_manager.state == UpdateState.AVAILABLE:
                # Update was found before window was created, show dialog
                QTimer.singleShot(500, self._show_pending_update)

    def setup_ui(self):
        """Setup the main UI layout"""
        self.setWindowTitle("Video Syncing")
        self.setMinimumSize(700, 600)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create and add setup window as widget (not standalone window)
        self.setup_widget = SyncingSetupWindow(
            last_video_folder=self.settings.last_video_sync_folder,
            last_s3_path=self.settings.last_s3_sync_path,
            parent=self
        )

        # Give orchestrator reference to setup widget
        self.orchestrator.set_setup_widget(self.setup_widget)

        # Connect setup completion signal to orchestrator
        self.setup_widget.setup_complete.connect(self.orchestrator.on_setup_complete)

        main_layout.addWidget(self.setup_widget)

        logger.info("SyncingMainWindow initialized")

    def create_menu_bar(self):
        """Create menu bar"""
        menubar = self.menuBar()

        # Help menu
        help_menu = menubar.addMenu("&Help")

        self.check_updates_action = QAction("Check for &Updates...", self)
        self.check_updates_action.triggered.connect(self.on_check_for_updates)
        help_menu.addAction(self.check_updates_action)

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

        QMessageBox.warning(self, "Update Error", f"An error occurred during update:\n\n{error}")

    def on_workflow_completed(self):
        """Handle workflow completion - reset for next sync"""
        logger.info("Workflow completed, ready for next sync")
        # Reset the setup widget for next use
        self.setup_widget.reset_for_next_sync()

    def on_workflow_cancelled(self):
        """Handle workflow cancellation"""
        logger.info("Workflow cancelled")
        # Reset the setup widget
        self.setup_widget.reset_for_next_sync()

    def closeEvent(self, event):
        """Handle window close event"""
        logger.info("SyncingMainWindow closing")
        # Clean up orchestrator and any active workflows
        if hasattr(self.orchestrator, 's3_workflow') and self.orchestrator.s3_workflow:
            self.orchestrator.s3_workflow.cleanup_temp_files()

        # Cleanup update manager
        if self.update_manager:
            self.update_manager.cleanup()

        event.accept()
