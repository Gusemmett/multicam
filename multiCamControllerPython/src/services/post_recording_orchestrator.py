"""Orchestrator for post-recording workflows - direct upload vs download & process"""

import logging
from typing import Dict

from PySide6.QtCore import QObject, Signal as pyqtSignal

from models.app_state import AppState
from services.direct_upload_manager import DirectUploadManager
from services.file_transfer_manager import FileTransferManager

logger = logging.getLogger(__name__)


class PostRecordingOrchestrator(QObject):
    """
    Orchestrates post-recording workflow based on settings.

    Two paths:
    1. Direct Upload (device → cloud): Fast, no processing
    2. Download & Process (device → controller → cloud): Syncing, encoding, RRD
    """

    # Signals
    workflow_started = pyqtSignal(str)  # workflow_type: "direct" or "download_and_process"
    workflow_completed = pyqtSignal(str, bool)  # workflow_type, success

    def __init__(
        self,
        app_state: AppState,
        direct_upload_manager: DirectUploadManager,
        file_transfer_manager: FileTransferManager,
        parent=None,
    ):
        super().__init__(parent)
        self.app_state = app_state
        self.direct_upload_manager = direct_upload_manager
        self.file_transfer_manager = file_transfer_manager

        # Connect signals from both managers
        self._connect_signals()

    def _connect_signals(self):
        """Connect signals from upload managers"""
        # Direct upload signals
        self.direct_upload_manager.all_uploads_complete.connect(
            lambda s, f: self._on_direct_upload_complete(s, f)
        )

        # File transfer signals
        self.file_transfer_manager.all_transfers_complete.connect(
            lambda s, f: self._on_download_process_complete(s, f)
        )

    async def handle_recording_stopped(
        self,
        file_names: Dict[str, str],
        session_id: str
    ):
        """
        Handle recording stopped event - choose workflow based on settings.

        Args:
            file_names: Dict mapping device_name -> file_name
            session_id: Recording session ID
        """
        if not file_names:
            logger.warning("No file names received from devices")
            return

        logger.info(f"Handling post-recording for {len(file_names)} files")
        logger.info(f"Upload method: {self.app_state.settings.upload_method}")

        # Choose workflow based on settings
        if self.app_state.settings.upload_method == "direct":
            await self._start_direct_upload_workflow(file_names, session_id)
        else:  # download_and_process
            await self._start_download_process_workflow(file_names, session_id)

    async def _start_direct_upload_workflow(
        self,
        file_names: Dict[str, str],
        session_id: str
    ):
        """
        Start direct upload workflow (device → cloud).

        Steps:
        1. Generate presigned S3 URLs
        2. Send UPLOAD_TO_CLOUD commands
        3. Poll DEVICE_STATUS
        4. Track progress
        """
        logger.info("Starting DIRECT UPLOAD workflow")
        self.workflow_started.emit("direct")

        # Check if S3 is enabled
        if not self.app_state.settings.upload_to_s3:
            logger.warning("S3 upload disabled, but using direct upload method")
            self.app_state.update_status(
                "Warning: Direct upload requires S3 to be enabled in settings"
            )
            self.workflow_completed.emit("direct", False)
            return

        # Start direct uploads
        success = await self.direct_upload_manager.start_direct_uploads(
            file_names=file_names,
            session_id=session_id
        )

        if success:
            # Note: No need to add session to recording history manually
            # DirectUploadManager will emit transfer_state_changed signals
            # which FileStatusWidget will use to create the session automatically

            # Upload metadata.json from controller
            logger.info("Uploading metadata.json for direct upload workflow")
            recording_session = self.app_state.recording_session
            metadata_success = await self.direct_upload_manager.upload_metadata_json(
                session_id=session_id,
                recorder_name=recording_session.recorderName,
                recording_start_time=recording_session.recordingStartTime,
                file_names=file_names,
                task=recording_session.task
            )

            if not metadata_success:
                logger.warning("Failed to upload metadata.json, but continuing with file uploads")

            self.app_state.update_status(
                f"Devices uploading {len(file_names)} files directly to cloud..."
            )
        else:
            logger.error("Failed to start direct uploads")
            self.app_state.update_status("Failed to start direct uploads")
            self.workflow_completed.emit("direct", False)

    async def _start_download_process_workflow(
        self,
        file_names: Dict[str, str],
        session_id: str
    ):
        """
        Start download & process workflow (device → controller → cloud).

        Steps:
        1. Download files from devices
        2. Unpack ZIPs
        3. Remux .mov files
        4. Sync videos (if multiple)
        5. Create RRD package
        6. Upload to S3 (if enabled)
        7. Cleanup
        """
        logger.info("Starting DOWNLOAD & PROCESS workflow")
        self.workflow_started.emit("download_and_process")

        self.app_state.update_status(
            f"Downloading and processing {len(file_names)} files..."
        )

        # Use existing FileTransferManager
        self.file_transfer_manager.add_transfer_items(file_names, session_id)

    def _on_direct_upload_complete(self, succeeded: int, failed: int):
        """Handle direct upload completion"""
        logger.info(f"Direct upload workflow complete: {succeeded} succeeded, {failed} failed")

        if failed == 0:
            self.app_state.update_status(
                f"All {succeeded} files uploaded directly to cloud!"
            )
            self.workflow_completed.emit("direct", True)
        else:
            self.app_state.update_status(
                f"Direct upload completed with errors: {succeeded} succeeded, {failed} failed"
            )
            self.workflow_completed.emit("direct", False)

    def _on_download_process_complete(self, succeeded: int, failed: int):
        """Handle download & process completion"""
        logger.info(f"Download & process workflow complete: {succeeded} succeeded, {failed} failed")

        if failed == 0:
            self.app_state.update_status(
                f"Downloaded and processed {succeeded} files!"
            )
            self.workflow_completed.emit("download_and_process", True)
        else:
            self.app_state.update_status(
                f"Processing completed with errors: {succeeded} succeeded, {failed} failed"
            )
            self.workflow_completed.emit("download_and_process", False)

    def cancel_current_workflow(self):
        """Cancel the currently running workflow"""
        logger.info("Cancelling current workflow")

        # Try to cancel both (only active one will do anything)
        self.direct_upload_manager.cancel_all()
        self.file_transfer_manager.cancel_all()

        self.app_state.update_status("Workflow cancelled")
