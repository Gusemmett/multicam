"""Direct device-to-cloud upload management using multicam_common protocol"""

import asyncio
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtCore import QObject, Signal as pyqtSignal

from multicam_common import CommandMessage, StatusResponse, UploadItem, DeviceStatus

from models.device import MultiCamDevice
from models.app_state import AppState
from models.file_transfer import FileTransferItem, TransferState
from services.device_communication import DeviceCommunication
from services.s3_manager import S3Manager
from services.metadata_manager import MetadataManager
from services.device_status_manager import DeviceStatusManager

logger = logging.getLogger(__name__)

# Authentication method for device uploads
# Set to True to use IAM credentials (via STS AssumeRole)
# Set to False to use presigned S3 URLs (original method)
USE_IAM_CREDENTIALS = True


@dataclass
class DeviceUploadState:
    """Track upload state for a single device"""

    device_name: str
    file_name: str
    upload_url: str
    status: str = "pending"  # pending, uploading, completed, failed
    progress: float = 0.0  # 0-100
    upload_speed: int = 0  # bytes/sec
    bytes_uploaded: int = 0
    total_bytes: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class DirectUploadManager(QObject):
    """
    Manages direct device-to-cloud uploads.

    Workflow:
    1. Generate presigned S3 URLs for each device
    2. Send UPLOAD_TO_CLOUD command to devices
    3. Poll DEVICE_STATUS every 2 seconds
    4. Track progress and emit signals for UI
    5. Handle completion/errors
    """

    # Signals
    upload_state_changed = pyqtSignal(DeviceUploadState)  # Per-device state update (legacy)
    transfer_state_changed = pyqtSignal(FileTransferItem)  # New signal compatible with FileStatusWidget
    all_uploads_complete = pyqtSignal(int, int)  # succeeded, failed
    upload_started = pyqtSignal()
    upload_finished = pyqtSignal(bool)  # success

    def __init__(
        self,
        app_state: AppState,
        device_comm: DeviceCommunication,
        s3_manager: S3Manager,
        device_status_manager: DeviceStatusManager,
        parent=None,
    ):
        super().__init__(parent)
        self.app_state = app_state
        self.device_comm = device_comm
        self.s3_manager = s3_manager
        self.device_status_manager = device_status_manager

        self.upload_states: Dict[str, DeviceUploadState] = {}
        self.transfer_items: Dict[str, FileTransferItem] = {}  # New: track FileTransferItem objects
        self.current_session_id: Optional[str] = None  # Track current session
        self.is_uploading = False
        self.poll_interval = 2.0  # seconds
        self._poll_task: Optional[asyncio.Task] = None

    def _create_or_update_transfer_item(self, state: DeviceUploadState, state_key: str) -> FileTransferItem:
        """Convert DeviceUploadState to FileTransferItem (or update existing)"""
        # Use file_name as fileId for direct uploads
        file_id = f"{state.device_name}:{state.file_name}"

        # Map DeviceUploadState status to TransferState
        transfer_state_map = {
            "pending": TransferState.PENDING,
            "uploading": TransferState.UPLOADING,
            "completed": TransferState.UPLOADED,
            "failed": TransferState.FAILED,
        }
        transfer_state = transfer_state_map.get(state.status, TransferState.PENDING)

        # Get or create FileTransferItem
        if state_key in self.transfer_items:
            item = self.transfer_items[state_key]
            # Update existing item
            item.state = transfer_state
            item.progress = state.progress
            item.upload_speed = state.upload_speed
            item.bytes_transferred = state.bytes_uploaded
            item.total_bytes = state.total_bytes if state.total_bytes > 0 else None
            item.error = state.error
            item.started_at = state.started_at
            item.completed_at = state.completed_at
            # Calculate ETA
            if state.upload_speed > 0 and state.total_bytes > state.bytes_uploaded:
                remaining_bytes = state.total_bytes - state.bytes_uploaded
                item.eta_seconds = remaining_bytes / state.upload_speed
            else:
                item.eta_seconds = None
        else:
            # Create new FileTransferItem
            item = FileTransferItem(
                deviceName=state.device_name,
                fileId=file_id,
                sessionId=self.current_session_id or "",
                state=transfer_state,
                progress=state.progress,
                s3Key=state.upload_url if state.upload_url.startswith("s3://") else None,
                error=state.error,
                upload_speed=state.upload_speed,
                bytes_transferred=state.bytes_uploaded,
                total_bytes=state.total_bytes if state.total_bytes > 0 else None,
                started_at=state.started_at,
                completed_at=state.completed_at,
                upload_source="device"  # Mark as direct-to-cloud upload
            )
            # Calculate ETA
            if state.upload_speed > 0 and state.total_bytes > state.bytes_uploaded:
                remaining_bytes = state.total_bytes - state.bytes_uploaded
                item.eta_seconds = remaining_bytes / state.upload_speed
            else:
                item.eta_seconds = None

            self.transfer_items[state_key] = item

        return item

    async def start_direct_uploads(
        self,
        file_names: Dict[str, str],
        session_id: str
    ) -> bool:
        """
        Start direct uploads from devices to S3.

        Devices can queue multiple uploads, so this can be called multiple times.

        Args:
            file_names: Dict mapping device_name -> file_name
            session_id: Recording session ID

        Returns:
            True if upload commands sent successfully, False otherwise
        """
        logger.info(f"Adding {len(file_names)} files to direct upload queue")

        # Store session ID
        self.current_session_id = session_id

        # Start polling if not already running
        should_start_polling = not self.is_uploading
        self.is_uploading = True

        if should_start_polling:
            self.upload_started.emit()

        try:
            # Step 1: Generate authentication (presigned URLs or IAM credentials) for uploads
            upload_commands = []

            # If using IAM credentials, generate them once for all devices
            iam_credentials = None
            if USE_IAM_CREDENTIALS:
                logger.info("Using IAM credentials authentication for uploads")
                iam_credentials = self.s3_manager.assume_role_for_upload()
                if not iam_credentials:
                    logger.error("Failed to assume IAM role for uploads")
                    self.is_uploading = False
                    self.upload_finished.emit(False)
                    return False
                logger.info("Successfully obtained IAM credentials for uploads")
            else:
                logger.info("Using presigned URL authentication for uploads")

            for device_name, file_name in file_names.items():
                # Find device
                device = next(
                    (d for d in self.app_state.discovered_devices if d.name == device_name),
                    None
                )

                if not device:
                    logger.error(f"Device {device_name} not found")
                    continue

                # Get device type from cached status
                device_type = None
                cached_status = self.device_status_manager.get_latest_status(device_name)
                if cached_status and cached_status.deviceType:
                    device_type = cached_status.deviceType
                    logger.info(f"Device {device.display_name} type: {device_type}")
                else:
                    logger.warning(f"No device type available for {device.display_name}, using default (exo)")

                # Create upload command based on authentication method
                command = None
                upload_url = ""

                if USE_IAM_CREDENTIALS:
                    # Generate S3 key for this upload with device folder
                    session_folder = self.s3_manager._generate_session_folder(session_id)
                    device_folder = self.s3_manager._get_device_folder(device_type)
                    s3_key = f"{session_folder}{device_folder}/{file_name}"
                    
                    logger.info(f"S3 upload path for {device.display_name}: {s3_key}")

                    # Create UPLOAD_TO_CLOUD command with IAM credentials
                    command = CommandMessage.upload_to_cloud_with_iam(
                        file_name=file_name,
                        s3_bucket=self.s3_manager.bucket_name,
                        s3_key=s3_key,
                        aws_access_key_id=iam_credentials['AccessKeyId'],
                        aws_secret_access_key=iam_credentials['SecretAccessKey'],
                        aws_session_token=iam_credentials['SessionToken'],
                        aws_region=self.s3_manager.region
                    )
                    upload_url = f"s3://{self.s3_manager.bucket_name}/{s3_key}"
                else:
                    # Generate presigned URL with device type
                    # Note: file_name now includes extension from device
                    presigned_url = self.s3_manager.generate_presigned_upload_url(
                        file_id=file_name,
                        session_id=session_id,
                        device_name=device.display_name,
                        device_type=device_type,
                        expires_in=3600  # 1 hour
                    )

                    if not presigned_url:
                        logger.error(f"Failed to generate presigned URL for {device_name}")
                        # Track as failed
                        state_key = f"{device_name}:{file_name}"
                        self.upload_states[state_key] = DeviceUploadState(
                            device_name=device_name,
                            file_name=file_name,
                            upload_url="",
                            status="failed",
                            error="Failed to generate presigned URL"
                        )
                        self.upload_state_changed.emit(self.upload_states[state_key])
                        # Also emit new signal
                        transfer_item = self._create_or_update_transfer_item(self.upload_states[state_key], state_key)
                        self.transfer_state_changed.emit(transfer_item)
                        continue

                    # Create UPLOAD_TO_CLOUD command with presigned URL
                    command = CommandMessage.upload_to_cloud(
                        file_name=file_name,
                        upload_url=presigned_url
                    )
                    upload_url = presigned_url

                # Initialize upload state (or update existing)
                # Use file_name as part of the key to allow multiple uploads per device
                state_key = f"{device_name}:{file_name}"
                self.upload_states[state_key] = DeviceUploadState(
                    device_name=device_name,
                    file_name=file_name,
                    upload_url=upload_url,
                    status="pending"
                )

                upload_commands.append((device, command, device_name))

            # Step 2: Send UPLOAD_TO_CLOUD commands to all devices
            if not upload_commands:
                logger.error("No valid upload commands to send")
                self.is_uploading = False
                self.upload_finished.emit(False)
                return False

            # Send commands concurrently
            logger.info(f"Sending UPLOAD_TO_CLOUD to {len(upload_commands)} devices")
            send_tasks = []
            for device, command, device_name in upload_commands:
                # Extract file_name from command
                file_name = command.fileName
                task = self._send_upload_command(device, command, device_name, file_name)
                send_tasks.append(task)

            results = await asyncio.gather(*send_tasks, return_exceptions=True)

            # Check for errors
            success_count = sum(1 for r in results if r is True)
            logger.info(f"Upload commands sent: {success_count}/{len(results)} successful")

            if success_count == 0:
                logger.error("Failed to send any upload commands")
                self.is_uploading = False
                self.upload_finished.emit(False)
                return False

            # Step 3: Start polling upload status (if not already polling)
            if should_start_polling:
                self._poll_task = asyncio.create_task(self._poll_upload_status())

            return True

        except Exception as e:
            logger.error(f"Failed to start direct uploads: {e}")
            self.is_uploading = False
            self.upload_finished.emit(False)
            return False

    async def _send_upload_command(
        self,
        device: MultiCamDevice,
        command: CommandMessage,
        device_name: str,
        file_name: str
    ) -> bool:
        """Send UPLOAD_TO_CLOUD command to a single device"""
        try:
            logger.info(f"Sending UPLOAD_TO_CLOUD to {device.display_name}: {file_name}")
            response = await self.device_comm.send_command(device, command)

            state_key = f"{device_name}:{file_name}"
            if DeviceStatus.is_success(response.status):
                logger.info(f"Upload command accepted by {device.display_name}")
                # Update state
                state = self.upload_states.get(state_key)
                if state:
                    state.status = "uploading"
                    state.started_at = datetime.now()
                    self.upload_state_changed.emit(state)
                    # Also emit new signal
                    transfer_item = self._create_or_update_transfer_item(state, state_key)
                    self.transfer_state_changed.emit(transfer_item)
                return True
            else:
                logger.error(f"Upload command rejected by {device.display_name}: {response.status}")
                # Mark as failed
                state = self.upload_states.get(state_key)
                if state:
                    state.status = "failed"
                    # Try to get error message from ErrorResponse or use status field
                    state.error = getattr(response, 'message', None) or response.status
                    self.upload_state_changed.emit(state)
                    # Also emit new signal
                    transfer_item = self._create_or_update_transfer_item(state, state_key)
                    self.transfer_state_changed.emit(transfer_item)
                return False

        except Exception as e:
            logger.error(f"Failed to send upload command to {device.display_name}: {e}")
            # Mark as failed
            state_key = f"{device_name}:{file_name}"
            state = self.upload_states.get(state_key)
            if state:
                state.status = "failed"
                state.error = str(e)
                self.upload_state_changed.emit(state)
                # Also emit new signal
                transfer_item = self._create_or_update_transfer_item(state, state_key)
                self.transfer_state_changed.emit(transfer_item)
            return False

    async def _poll_upload_status(self):
        """Poll upload status from all devices every 2 seconds"""
        logger.info("Starting upload status polling")

        try:
            while self.is_uploading:
                # Check if all uploads are done
                all_done = all(
                    state.status in ["completed", "failed"]
                    for state in self.upload_states.values()
                )

                if all_done:
                    logger.info("All uploads complete, stopping poll")
                    break

                # Query status from each device that has active uploads
                status_tasks = []
                # Get unique device names that have active uploads
                active_devices = set(
                    state.device_name for state in self.upload_states.values()
                    if state.status not in ["completed", "failed"]
                )

                for device_name in active_devices:
                    # Find device
                    device = next(
                        (d for d in self.app_state.discovered_devices if d.name == device_name),
                        None
                    )
                    if device:
                        task = self._query_device_upload_status(device, device_name)
                        status_tasks.append(task)

                if status_tasks:
                    await asyncio.gather(*status_tasks, return_exceptions=True)

                # Wait before next poll
                await asyncio.sleep(self.poll_interval)

            # All done - emit completion signal
            succeeded = sum(1 for s in self.upload_states.values() if s.status == "completed")
            failed = sum(1 for s in self.upload_states.values() if s.status == "failed")

            logger.info(f"Direct uploads finished: {succeeded} succeeded, {failed} failed")
            self.is_uploading = False
            self.all_uploads_complete.emit(succeeded, failed)
            self.upload_finished.emit(failed == 0)

        except Exception as e:
            logger.error(f"Error in upload status polling: {e}")
            self.is_uploading = False
            self.upload_finished.emit(False)

    async def _query_device_upload_status(
        self,
        device: MultiCamDevice,
        device_name: str
    ):
        """Query upload status from a single device"""
        try:
            # Send DEVICE_STATUS command (replaces UPLOAD_STATUS)
            command = CommandMessage.device_status()
            response = await self.device_comm.send_command(device, command)

            # Update all states for this device
            # Find all upload states for this device
            device_states = {key: state for key, state in self.upload_states.items()
                           if state.device_name == device_name and state.status not in ["completed", "failed"]}

            for state_key, state in device_states.items():
                # Check upload queue for our file
                found = False
                for upload_item in response.uploadQueue:
                    if upload_item.fileName == state.file_name:
                        found = True
                        # Update progress
                        state.progress = upload_item.uploadProgress
                        state.upload_speed = upload_item.uploadSpeed
                        state.bytes_uploaded = upload_item.bytesUploaded
                        state.total_bytes = upload_item.fileSize

                        # Update status
                        if upload_item.status == "completed":
                            state.status = "completed"
                            state.completed_at = datetime.now()
                            logger.info(f"Upload completed for {device_name}: {state.file_name}")
                            self.upload_state_changed.emit(state)
                            # Also emit new signal
                            transfer_item = self._create_or_update_transfer_item(state, state_key)
                            self.transfer_state_changed.emit(transfer_item)
                        elif upload_item.status == "failed":
                            state.status = "failed"
                            state.error = upload_item.error or "Upload failed on device"
                            logger.error(f"Upload failed for {device_name}: {state.error}")
                            self.upload_state_changed.emit(state)
                            # Also emit new signal
                            transfer_item = self._create_or_update_transfer_item(state, state_key)
                            self.transfer_state_changed.emit(transfer_item)
                        else:
                            # uploading or queued
                            state.status = "uploading"
                            self.upload_state_changed.emit(state)
                            # Also emit new signal
                            transfer_item = self._create_or_update_transfer_item(state, state_key)
                            self.transfer_state_changed.emit(transfer_item)
                        break

                # Check failed upload queue for our file if not found in active queue
                if not found:
                    for failed_item in response.failedUploadQueue:
                        if failed_item.fileName == state.file_name:
                            found = True
                            state.status = "failed"
                            state.error = failed_item.error or "Upload failed on device"
                            logger.error(f"Upload failed for {device_name}: {state.error}")
                            self.upload_state_changed.emit(state)
                            # Also emit new signal
                            transfer_item = self._create_or_update_transfer_item(state, state_key)
                            self.transfer_state_changed.emit(transfer_item)
                            break

                # If not found in either queue, the upload must have completed successfully
                # (device removes completed uploads from both queues)
                if not found:
                    state.status = "completed"
                    state.progress = 100.0
                    state.completed_at = datetime.now()
                    logger.info(f"Upload completed for {device_name}: {state.file_name} (inferred from removal from queue)")
                    self.upload_state_changed.emit(state)
                    # Also emit new signal
                    transfer_item = self._create_or_update_transfer_item(state, state_key)
                    self.transfer_state_changed.emit(transfer_item)

        except Exception as e:
            logger.error(f"Failed to query upload status from {device.display_name}: {e}")

    async def upload_metadata_json(
        self,
        session_id: str,
        recorder_name: Optional[str],
        recording_start_time: Optional[datetime],
        file_names: Optional[Dict[str, str]] = None,
        task: Optional[str] = None
    ) -> bool:
        """
        Upload metadata.json file to S3 for the direct upload workflow.

        This creates a temporary metadata.json file on the controller and uploads it
        to the session folder in S3 alongside device uploads.

        Args:
            session_id: Recording session ID
            recorder_name: Name of the person/device recording
            recording_start_time: When the recording started
            file_names: Optional dict mapping device_name -> file_name
            task: Task being performed during recording

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Creating metadata.json for session {session_id}")

            # Create temporary metadata file
            temp_metadata_path = MetadataManager.create_temp_metadata_file(
                session_id=session_id,
                recorder_name=recorder_name,
                recording_start_time=recording_start_time,
                file_names=file_names,
                openweather_api_key=self.app_state.settings.openweather_api_key,
                task=task
            )

            if not temp_metadata_path:
                logger.error("Failed to create temporary metadata.json")
                return False

            # Upload to S3
            logger.info(f"Uploading metadata.json to S3 for session {session_id}...")
            logger.info(f"S3 bucket: {self.app_state.settings.s3_bucket}")
            logger.info(f"Metadata file path: {temp_metadata_path}")
            
            result = await self.s3_manager.upload_files(
                file_paths=[str(temp_metadata_path)],
                session_id=session_id
            )

            # Clean up temporary file
            try:
                temp_metadata_path.unlink()
                logger.info(f"Cleaned up temporary metadata file: {temp_metadata_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary metadata file: {e}")

            if result.success:
                logger.info(f"✓ Successfully uploaded metadata.json to S3 for session {session_id}")
                return True
            else:
                logger.error(f"✗ Failed to upload metadata.json to S3 for session {session_id}")
                logger.error(f"S3 upload status: FAILED - {result.error}")
                return False

        except Exception as e:
            logger.error(f"Error uploading metadata.json: {e}")
            return False

    def cancel_all(self):
        """Cancel all pending uploads"""
        logger.info("Cancelling all direct uploads")
        self.is_uploading = False

        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

        # Mark all pending/uploading as cancelled
        for state_key, state in self.upload_states.items():
            if state.status in ["pending", "uploading"]:
                state.status = "failed"
                state.error = "Cancelled by user"
                self.upload_state_changed.emit(state)
                # Also emit new signal
                transfer_item = self._create_or_update_transfer_item(state, state_key)
                self.transfer_state_changed.emit(transfer_item)
