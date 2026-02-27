"""MultiCam Controller - Main entry point"""

import sys
import os
import asyncio
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer
from qasync import QEventLoop
import logging

from ui.main_window import MainWindow
from ui.dialogs.mode_selection_dialog import ModeSelectionDialog
from ui.syncing_main_window import SyncingMainWindow
from models.app_settings import AppSettings
from services.update_manager import UpdateManager
from services.embedded_server_manager import EmbeddedServerManager
from utils.logger import setup_logging


def main():
    """Main application entry point"""
    # Check for debug mode from environment variable
    debug_mode = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    log_level = logging.DEBUG if debug_mode else logging.INFO

    # Setup logging
    setup_logging(log_level=log_level)
    logger = logging.getLogger(__name__)

    if debug_mode:
        logger.debug("DEBUG MODE ENABLED - Request/Response logging active")

    logger.info("Starting MultiCam Controller")

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("MultiCam Controller")
    app.setOrganizationName("MultiCam")

    # Setup asyncio event loop with qasync
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Load application settings
    settings = AppSettings.load()
    logger.info(f"Settings loaded: {settings}")

    # Create update manager early so update check starts immediately
    update_manager = UpdateManager()
    # Start checking for updates in the background
    update_manager.check_for_updates_async()

    # Start embedded OAK server (runs in background, auto-detects camera)
    embedded_server = EmbeddedServerManager()

    async def start_embedded_server():
        """Start the embedded OAK server."""
        try:
            success = await embedded_server.start_server(port=8080)
            if success:
                logger.info("Embedded OAK server started successfully")
            else:
                logger.warning("Embedded OAK server failed to start (DepthAI may not be available)")
        except Exception as e:
            logger.warning(f"Could not start embedded OAK server: {e}")

    # Schedule the server to start once the Qt event loop is running
    # QTimer.singleShot(0, ...) runs on the next Qt event loop iteration
    # which is after loop.run_forever() has started
    def schedule_server_start():
        asyncio.ensure_future(start_embedded_server())

    QTimer.singleShot(500, schedule_server_start)  # Delay to ensure Qt/asyncio loop is running

    # Setup shutdown handler
    async def cleanup_embedded_server():
        """Stop the embedded server on app quit."""
        logger.info("Shutting down embedded OAK server...")
        await embedded_server.stop_server()

    def on_app_quit():
        """Handle application quit."""
        asyncio.ensure_future(cleanup_embedded_server())

    app.aboutToQuit.connect(on_app_quit)

    # Show mode selection dialog
    mode_dialog = ModeSelectionDialog()
    result = mode_dialog.exec()

    # Check if user cancelled the dialog
    if result != mode_dialog.DialogCode.Accepted or mode_dialog.selected_mode is None:
        logger.info("Mode selection cancelled, exiting application")
        sys.exit(0)

    # Handle selected mode
    window = None

    if mode_dialog.selected_mode == "recording":
        logger.info("Starting in Recording mode")
        # Create and show main window
        window = MainWindow(update_manager=update_manager)
        window.show()

    elif mode_dialog.selected_mode == "syncing":
        logger.info("Starting in Syncing mode")
        # Create and show syncing main window
        window = SyncingMainWindow(settings, update_manager=update_manager)
        window.show()

    else:
        logger.error(f"Unknown mode selected: {mode_dialog.selected_mode}")
        QMessageBox.critical(
            None,
            "Error",
            f"Unknown mode selected: {mode_dialog.selected_mode}"
        )
        sys.exit(1)

    # Run event loop
    with loop:
        sys.exit(loop.run_forever())


if __name__ == "__main__":
    main()
