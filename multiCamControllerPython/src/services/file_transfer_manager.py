"""File transfer orchestration (download + upload)"""

from PySide6.QtCore import QObject, Signal as pyqtSignal
from typing import Dict, List, Optional
from pathlib import Path
import asyncio
import logging
from datetime import datetime
import time

from multicam_common import CommandMessage, DeviceStatus

from models.file_transfer import FileTransferItem, TransferState, ErrorCategory
from models.app_state import AppState
from services.device_communication import DeviceCommunication
from services.s3_manager import S3Manager
from services.video_sync_service import VideoSyncService
from services.pending_uploads_manager import PendingUploadsManager
from services.metadata_manager import MetadataManager
from utils.file_utils import get_unpacked_path, process_mov_files
from utils.constants import RESOLUTION_DIMENSIONS

logger = logging.getLogger(__name__)


class FileTransferManager(QObject):
    """Manages downloading files from devices and uploading to S3"""

    transfer_state_changed = pyqtSignal(object)  # FileTransferItem
    all_transfers_complete = pyqtSignal(int, int)  # succeeded, failed
    global_upload_progress = pyqtSignal(int, int, int, str)  # current_file, total_files, progress_percent, current_filename
    global_upload_started = pyqtSignal()  # Emitted when global upload starts
    global_upload_finished = pyqtSignal(bool)  # Emitted when global upload finishes (success/failure)

    def __init__(
        self,
        app_state: AppState,
        device_comm: DeviceCommunication,
        s3_manager: S3Manager,
        parent=None,
    ):
        super().__init__(parent)
        self.app_state = app_state
        self.device_comm = device_comm
        self.s3_manager = s3_manager
        self.pending_uploads_manager = PendingUploadsManager(parent)
        self.transfer_queue: List[FileTransferItem] = []
        self.is_processing = False
        self.is_paused = False
        self.parent_widget = parent  # Store parent for dialog
        self.session_directories: Dict[str, str] = {}  # Map session_id to directory path

        # Note: restore_pending_sessions() will be called by the UI after signals are connected

    def add_transfer_items(self, fileIds: Dict[str, str], sessionId: str):
        """Add transfer items to the queue"""
        for deviceName, fileId in fileIds.items():
            item = FileTransferItem(
                deviceName=deviceName,
                fileId=fileId,
                sessionId=sessionId,
                max_retries=self.app_state.settings.max_download_retries
            )
            self.transfer_queue.append(item)
            self.transfer_state_changed.emit(item)

        # Auto-start processing
        if not self.is_processing:
            asyncio.create_task(self.start_processing())

    def add_direct_upload_session(self, fileIds: Dict[str, str], sessionId: str):
        """
        Add a direct upload session to recording history.
        These are placeholder entries to show sessions that were uploaded directly from devices.
        """
        for deviceName, fileId in fileIds.items():
            item = FileTransferItem(
                deviceName=deviceName,
                fileId=fileId,
                sessionId=sessionId,
                state=TransferState.UPLOADED,  # Mark as already uploaded
                progress=100.0,
                started_at=datetime.now(),
                completed_at=datetime.now()
            )
            self.transfer_queue.append(item)
            self.transfer_state_changed.emit(item)
        
        logger.info(f"Added {len(fileIds)} direct upload entries to recording history")

    async def start_processing(self):
        """Process all transfers in queue"""
        if self.is_processing:
            logger.warning("Transfer processing already in progress")
            return

        self.is_processing = True
        logger.info(f"Processing {len(self.transfer_queue)} transfers")

        succeeded = 0
        failed = 0

        # Track items processed in this run
        processed_items = []
        current_session_ids = set()

        for item in self.transfer_queue:
            # Check for pause
            while self.is_paused:
                await asyncio.sleep(0.5)

            # Process pending or retrying transfers
            if item.state in [TransferState.PENDING, TransferState.RETRYING]:
                # Track this item and its session
                processed_items.append(item)
                current_session_ids.add(item.sessionId)

                # Download file
                success = await self._download_file(item)
                if success:
                    succeeded += 1
                elif item.state == TransferState.CANCELLED:
                    # Don't count cancelled as failed
                    pass
                else:
                    failed += 1

        # Get downloaded files ONLY from the sessions we just processed
        downloaded_files = [
            item.localPath
            for item in processed_items
            if item.state == TransferState.DOWNLOADED and item.localPath
        ]

        logger.info(f"Found {len(downloaded_files)} downloaded files from {len(current_session_ids)} session(s)")

        # Store session directories for all processed sessions
        for session_id in current_session_ids:
            # Find the first downloaded file for this session
            for item in processed_items:
                if item.sessionId == session_id and item.state == TransferState.DOWNLOADED and item.localPath:
                    file_path = Path(item.localPath)
                    # Determine session directory (always use parent)
                    session_dir = file_path.parent

                    # Store it
                    self.session_directories[session_id] = str(session_dir)
                    logger.info(f"Stored session directory for {session_id}: {session_dir}")
                    break  # Only need one file from this session

        if downloaded_files:
            # Process downloaded files - unpack any ZIP files
            processed_paths = []
            for file_path in downloaded_files:
                # This will unpack if it's a ZIP, or return original path if not
                # Pass the setting to determine whether to delete ZIP files after unpacking
                unpacked_path = get_unpacked_path(
                    file_path,
                    delete_zip_after_unpack=self.app_state.settings.delete_zip_after_unpack
                )
                processed_paths.append(unpacked_path)

            # Post-process: Remux any .mov files to .mp4 (if codecs are compatible)
            logger.info("Checking for .mov files to remux to .mp4...")
            for processed_path in processed_paths:
                process_mov_files(processed_path)

            # Show video sync UI if we have multiple videos/directories
            if len(processed_paths) > 1:
                logger.info(f"Opening video sync UI for {len(processed_paths)} items")
                # Determine codec and resolution from settings
                codec = "av1" if self.app_state.settings.reencode_to_av1 else "h264"
                max_resolution = self._get_max_resolution_tuple(self.app_state.settings.max_video_resolution)

                synced_files = await VideoSyncService.sync_videos(
                    processed_paths,
                    output_dir=None,  # Use temp directory or same location
                    codec=codec,
                    max_resolution=max_resolution,
                    parent_widget=self.parent_widget
                )
                # Note: sync_videos now handles RRD packaging internally
                # synced_files contains the paths that were synced (videos have been replaced in-place)

            # Determine the session directory to upload (use first session)
            # Get session directory from first downloaded file
            first_file = downloaded_files[0]
            first_path = Path(first_file)

            # Determine session directory (always use parent)
            session_dir = first_path.parent

            logger.info(f"Uploading entire session directory: {session_dir}")

            # Create metadata.json file in session directory
            metadata_path = session_dir / "metadata.json"
            recording_session = self.app_state.recording_session

            # Build file_names dict from processed items
            file_names_dict = {
                item.deviceName: item.fileId
                for item in processed_items
                if item.state == TransferState.DOWNLOADED
            }

            metadata = MetadataManager.create_metadata(
                session_id=recording_session.sessionId,
                recorder_name=recording_session.recorderName,
                recording_start_time=recording_session.recordingStartTime,
                file_names=file_names_dict,
                openweather_api_key=self.app_state.settings.openweather_api_key,
                task=recording_session.task
            )

            logger.info(f"Saving metadata.json to local file: {metadata_path}")
            save_success = MetadataManager.save_metadata_to_file(metadata, metadata_path)
            if save_success:
                logger.info(f"✓ Successfully saved metadata.json locally")
            else:
                logger.error(f"✗ Failed to save metadata.json locally")

            # Collect all files in session directory, excluding .zip files
            files_to_upload = []
            for item in session_dir.rglob("*"):
                if item.is_file() and item.suffix.lower() != ".zip":
                    files_to_upload.append(str(item))

            logger.info(f"Found {len(files_to_upload)} files to upload (excluding .zip files)")

            # Check upload mode and S3 settings
            if self.app_state.settings.upload_to_s3:
                if self.app_state.settings.upload_mode == "manual":
                    # Manual mode: add to pending uploads queue
                    logger.info("Manual upload mode: adding session to pending uploads queue")

                    # Get the first session from processed items
                    first_session_id = list(current_session_ids)[0] if current_session_ids else "unknown"

                    # Add to pending uploads manager
                    recording_session = self.app_state.recording_session
                    self.pending_uploads_manager.add_session(
                        session_id=first_session_id,
                        session_dir=str(session_dir),
                        recorder_name=recording_session.recorderName or "Unknown",
                        recorded_at=recording_session.recordingStartTime or datetime.now(),
                        recording_duration_seconds=recording_session.get_duration_seconds()
                    )

                    # Mark all items in this session as PROCESSED_NOT_UPLOADED
                    for item in processed_items:
                        if item.state == TransferState.DOWNLOADED:
                            item.state = TransferState.PROCESSED_NOT_UPLOADED
                            self.transfer_state_changed.emit(item)

                else:
                    # Immediate mode: upload right away
                    logger.info("Immediate upload mode: uploading to S3 now")

                    # Get the first session ID from processed items
                    first_session_id = list(current_session_ids)[0] if current_session_ids else None

                    # Upload files using global progress tracking
                    await self._upload_files_with_global_progress(files_to_upload, session_id=first_session_id)
            else:
                logger.info("S3 upload disabled in settings, skipping upload")

        # Clean up completed items from the queue (only from sessions we just processed)
        # Keep PROCESSED_NOT_UPLOADED items so they show up in the pending uploads filter
        initial_queue_size = len(self.transfer_queue)
        self.transfer_queue = [
            item for item in self.transfer_queue
            if item.sessionId not in current_session_ids or item.state in [
                TransferState.PENDING,
                TransferState.RETRYING,
                TransferState.PROCESSED_NOT_UPLOADED
            ]
        ]
        removed_count = initial_queue_size - len(self.transfer_queue)
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} completed transfer items from queue")

        self.is_processing = False
        self.all_transfers_complete.emit(succeeded, failed)
        logger.info(f"Transfer processing complete: {succeeded} succeeded, {failed} failed")

    async def _download_file(self, item: FileTransferItem) -> bool:
        """Download a single file with retry logic"""
        while item.retry_count <= item.max_retries:
            # Check for cancellation
            if item.cancel_requested:
                item.mark_cancelled()
                self.transfer_state_changed.emit(item)
                logger.info(f"Download cancelled: {item.fileId}")
                return False

            try:
                # Apply backoff delay if this is a retry
                if item.retry_count > 0:
                    delay = self._calculate_backoff_delay(item.retry_count - 1)
                    logger.info(f"Waiting {delay}s before retry {item.retry_count}/{item.max_retries}")
                    await asyncio.sleep(delay)

                # Set started timestamp on first attempt
                if item.started_at is None:
                    item.started_at = datetime.now()

                # Update state
                if item.retry_count == 0:
                    item.state = TransferState.DOWNLOADING
                else:
                    item.state = TransferState.RETRYING

                self.transfer_state_changed.emit(item)

                # Find device
                device = next(
                    (d for d in self.app_state.discovered_devices if d.name == item.deviceName), None
                )

                if not device:
                    raise ValueError(f"Device {item.deviceName} not found")

                # Download file with progress tracking
                command = CommandMessage.get_video(file_name=item.fileId)
                start_time = time.time()
                last_bytes = 0

                def progress_callback(progress: float):
                    # Check for cancellation during download
                    if item.cancel_requested:
                        raise asyncio.CancelledError("Download cancelled by user")

                    # Update progress
                    item.progress = progress * 100

                    # Calculate speed and ETA (rough estimate)
                    elapsed = time.time() - start_time
                    if elapsed > 0 and item.total_bytes:
                        current_bytes = int(item.total_bytes * progress)
                        item.bytes_transferred = current_bytes
                        item.download_speed = (current_bytes - last_bytes) / elapsed if elapsed > 0 else 0

                        # Calculate ETA
                        if item.download_speed > 0:
                            remaining_bytes = item.total_bytes - current_bytes
                            item.eta_seconds = remaining_bytes / item.download_speed

                    self.transfer_state_changed.emit(item)

                response = await self.device_comm.send_command(
                    device,
                    command,
                    progress_callback=progress_callback,
                    session_id=item.sessionId,
                    downloads_directory=self.app_state.settings.downloads_directory or None
                )

                # For GET_VIDEO, file path is stored in response.status field
                if response.status and "/" in response.status:  # Heuristic: status contains a file path
                    item.localPath = response.status
                    item.state = TransferState.DOWNLOADED
                    item.progress = 100.0
                    item.download_speed = 0.0
                    item.eta_seconds = None
                    self.transfer_state_changed.emit(item)
                    logger.info(f"Downloaded {item.fileId} from {item.deviceName}")
                    return True
                else:
                    raise ValueError(f"Download failed: {response.error}")

            except asyncio.CancelledError:
                item.mark_cancelled()
                self.transfer_state_changed.emit(item)
                logger.info(f"Download cancelled: {item.fileId}")
                return False

            except Exception as e:
                # Categorize error
                item.error_category = self._categorize_error(e)
                item.error = str(e)

                logger.error(
                    f"Failed to download {item.fileId} (attempt {item.retry_count + 1}/{item.max_retries + 1}): {e}"
                )

                # Check if we should retry
                if item.retry_count < item.max_retries and item.error_category in [
                    ErrorCategory.NETWORK,
                    ErrorCategory.TIMEOUT,
                    ErrorCategory.UNKNOWN,
                ]:
                    # Increment retry count and try again
                    item.increment_retry()
                    self.transfer_state_changed.emit(item)
                    logger.info(f"Will retry {item.fileId} (attempt {item.retry_count + 1}/{item.max_retries + 1})")
                    continue
                else:
                    # No more retries or non-retryable error
                    item.state = TransferState.FAILED
                    item.completed_at = datetime.now()
                    self.transfer_state_changed.emit(item)
                    return False

        # Exhausted all retries
        item.state = TransferState.FAILED
        item.completed_at = datetime.now()
        self.transfer_state_changed.emit(item)
        return False

    async def _upload_files_with_global_progress(self, file_paths: List[str], session_id: Optional[str] = None) -> bool:
        """Upload files to S3 with global progress tracking (no individual upload task)"""
        try:
            # Log metadata file if present
            metadata_files = [f for f in file_paths if "metadata.json" in f]
            if metadata_files:
                logger.info(f"Preparing to upload {len(metadata_files)} metadata.json file(s) to S3")
                for metadata_file in metadata_files:
                    logger.info(f"Metadata file included in upload: {metadata_file}")
            
            # Emit start signal
            self.global_upload_started.emit()
            
            logger.info(f"Starting S3 upload for session {session_id}")
            logger.info(f"Total files to upload: {len(file_paths)}")
            logger.info(f"S3 bucket: {self.app_state.settings.s3_bucket}")
            logger.info(f"Delete after upload: {self.app_state.settings.delete_after_upload}")

            # Upload to S3 in a thread pool to prevent blocking the main event loop
            def progress_callback(index: int, total: int, progress: float, file_name: str):
                # Calculate overall progress
                overall_progress = int(((index + (progress / 100.0)) / total) * 100.0)

                # Emit global progress signal (signals are thread-safe in Qt)
                self.global_upload_progress.emit(index + 1, total, overall_progress, file_name)

            # Get session directory for preserving structure
            session_directory = self.get_session_directory(session_id) if session_id else None
            
            # Create a synchronous wrapper to run in thread pool
            def sync_upload():
                # Run the async upload in a new event loop in the thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    if self.app_state.settings.delete_after_upload:
                        result = loop.run_until_complete(
                            self.s3_manager.upload_and_cleanup(
                                file_paths, 
                                progress_callback=progress_callback, 
                                session_id=session_id,
                                base_directory=session_directory
                            )
                        )
                    else:
                        result = loop.run_until_complete(
                            self.s3_manager.upload_files(
                                file_paths, 
                                progress_callback=progress_callback, 
                                session_id=session_id,
                                base_directory=session_directory
                            )
                        )
                    return result
                finally:
                    loop.close()

            # Run the blocking upload in a thread pool executor
            main_loop = asyncio.get_event_loop()
            result = await main_loop.run_in_executor(None, sync_upload)

            if result.success:
                logger.info(f"✓ S3 upload SUCCESS for session {session_id}")
                logger.info(f"Uploaded {result.uploaded_count} files to S3 (including metadata.json)")
                logger.info(f"S3 upload status: SUCCESS")
                self.global_upload_finished.emit(True)
                return True
            else:
                logger.error(f"✗ S3 upload FAILED for session {session_id}")
                logger.error(f"Upload failed: {result.error}")
                logger.error(f"S3 upload status: FAILED - {result.error}")
                self.global_upload_finished.emit(False)
                return False

        except Exception as e:
            logger.error(f"✗ S3 upload FAILED for session {session_id}")
            logger.error(f"S3 upload failed with exception: {e}")
            logger.error(f"S3 upload status: FAILED - {str(e)}")
            self.global_upload_finished.emit(False)
            return False

    def cancel_all(self):
        """Cancel all pending transfers"""
        for item in self.transfer_queue:
            if item.is_active or item.state == TransferState.PENDING:
                item.mark_cancelled()
                self.transfer_state_changed.emit(item)
        self.is_processing = False
        logger.info("All transfers cancelled")

    def cancel_transfer(self, item: FileTransferItem):
        """Cancel a specific transfer"""
        if item in self.transfer_queue:
            item.request_cancel()
            logger.info(f"Cancellation requested for {item.fileId}")

    def retry_transfer(self, item: FileTransferItem):
        """Retry a failed transfer"""
        if item.state == TransferState.FAILED and item.can_retry:
            item.increment_retry()
            item.error = None
            item.progress = 0.0
            self.transfer_state_changed.emit(item)
            logger.info(f"Retrying transfer {item.fileId} (attempt {item.retry_count})")

            # Start processing if not already running
            if not self.is_processing:
                asyncio.create_task(self.start_processing())

    def pause_processing(self):
        """Pause transfer processing"""
        self.is_paused = True
        logger.info("Transfer processing paused")

    def resume_processing(self):
        """Resume transfer processing"""
        self.is_paused = False
        logger.info("Transfer processing resumed")

        # Restart processing if there are pending transfers
        if not self.is_processing:
            asyncio.create_task(self.start_processing())

    @staticmethod
    def _categorize_error(error: Exception) -> ErrorCategory:
        """Categorize error for retry decision"""
        error_str = str(error).lower()

        if "timeout" in error_str or "timed out" in error_str:
            return ErrorCategory.TIMEOUT
        elif "connection" in error_str or "network" in error_str or "unreachable" in error_str:
            return ErrorCategory.NETWORK
        elif "auth" in error_str or "permission" in error_str or "forbidden" in error_str:
            return ErrorCategory.AUTH
        elif "not found" in error_str or "404" in error_str:
            return ErrorCategory.NOT_FOUND
        elif "disk full" in error_str or "no space" in error_str:
            return ErrorCategory.DISK_FULL
        else:
            return ErrorCategory.UNKNOWN

    @staticmethod
    def _get_max_resolution_tuple(resolution_str: str) -> Optional[tuple[int, int]]:
        """Convert resolution string to tuple for FFmpeg"""
        return RESOLUTION_DIMENSIONS.get(resolution_str, (1280, 720))

    def get_session_directory(self, session_id: str) -> Optional[str]:
        """Get the directory path for a given session ID"""
        # First check the persistent mapping
        if session_id in self.session_directories:
            return self.session_directories[session_id]

        # Fallback: find any item in the transfer queue for this session that has a local path
        for item in self.transfer_queue:
            if item.sessionId == session_id and item.localPath:
                # Get the parent directory of the downloaded file (always use parent)
                file_path = Path(item.localPath)
                session_dir = file_path.parent

                # Store it for future use
                self.session_directories[session_id] = str(session_dir)
                return str(session_dir)
        return None

    @staticmethod
    def _calculate_backoff_delay(retry_count: int) -> float:
        """Calculate exponential backoff delay in seconds"""
        # Exponential backoff: 1s, 2s, 4s, 8s, etc.
        base_delay = 1.0
        max_delay = 10.0
        delay = min(base_delay * (2 ** retry_count), max_delay)
        return delay

    async def upload_session(self, session_id: str) -> bool:
        """
        Upload a specific pending session to S3.

        Args:
            session_id: ID of the session to upload

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get the pending session
            pending_session = self.pending_uploads_manager.get_session(session_id)
            if not pending_session:
                logger.error(f"Session {session_id} not found in pending uploads")
                return False

            session_dir = Path(pending_session.session_dir)
            if not session_dir.exists():
                logger.error(f"Session directory does not exist: {session_dir}")
                self.pending_uploads_manager.remove_session(session_id)
                return False

            # Collect all files in session directory (excluding .zip files)
            files_to_upload = []
            for item in session_dir.rglob("*"):
                if item.is_file() and item.suffix.lower() != ".zip":
                    files_to_upload.append(str(item))

            logger.info(f"Uploading session {session_id}: {len(files_to_upload)} files")

            # Upload files using global progress tracking
            success = await self._upload_files_with_global_progress(files_to_upload, session_id=session_id)

            # Check if upload was successful
            if success:
                # Remove from pending uploads
                self.pending_uploads_manager.remove_session(session_id)

                # Update any PROCESSED_NOT_UPLOADED items for this session
                for item in self.transfer_queue:
                    if item.sessionId == session_id and item.state == TransferState.PROCESSED_NOT_UPLOADED:
                        item.state = TransferState.UPLOADED
                        self.transfer_state_changed.emit(item)

                logger.info(f"Successfully uploaded session {session_id}")
                return True
            else:
                logger.error(f"Failed to upload session {session_id}")
                return False

        except Exception as e:
            logger.error(f"Error uploading session {session_id}: {e}")
            return False

    async def upload_all_pending_sessions(self) -> tuple[int, int]:
        """
        Upload all pending sessions to S3 with cumulative progress tracking.
        Each session is uploaded to its own folder in S3.

        Returns:
            Tuple of (succeeded_count, failed_count)
        """
        pending_sessions = self.pending_uploads_manager.get_all_sessions()
        logger.info(f"Uploading {len(pending_sessions)} pending sessions")

        if not pending_sessions:
            return (0, 0)

        # Collect all files from all sessions and track session info
        all_files_to_upload = []
        session_file_mapping = {}  # Map session_id to (files, start_index)

        current_index = 0
        for session in pending_sessions:
            session_dir = Path(session.session_dir)
            if not session_dir.exists():
                logger.warning(f"Session directory does not exist: {session_dir}")
                continue

            # Collect files for this session
            session_files = []
            for item in session_dir.rglob("*"):
                if item.is_file() and item.suffix.lower() != ".zip":
                    session_files.append(str(item))

            session_file_mapping[session.session_id] = (session_files, current_index)
            all_files_to_upload.extend(session_files)
            current_index += len(session_files)

        if not all_files_to_upload:
            logger.warning("No files to upload")
            return (0, 0)

        total_files = len(all_files_to_upload)
        logger.info(f"Total files to upload across all sessions: {total_files}")

        # Emit start signal
        self.global_upload_started.emit()

        succeeded = 0
        failed = 0

        # Upload each session separately to maintain folder structure
        uploaded_file_count = 0
        for session in pending_sessions:
            if session.session_id not in session_file_mapping:
                continue

            session_files, start_index = session_file_mapping[session.session_id]
            if not session_files:
                continue

            logger.info(f"Uploading session {session.session_id}: {len(session_files)} files")

            try:
                # Create progress callback that tracks cumulative progress
                def make_progress_callback(session_start_index, session_file_count):
                    def progress_callback(index: int, total: int, progress: float, file_name: str):
                        # Calculate cumulative file index across all sessions
                        cumulative_index = session_start_index + index
                        # Calculate cumulative progress
                        overall_progress = int(((cumulative_index + (progress / 100.0)) / total_files) * 100.0)

                        # Emit global progress signal with cumulative values (signals are thread-safe)
                        self.global_upload_progress.emit(cumulative_index + 1, total_files, overall_progress, file_name)
                    return progress_callback

                # Create a synchronous wrapper to run in thread pool
                def sync_upload():
                    # Run the async upload in a new event loop in the thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        if self.app_state.settings.delete_after_upload:
                            result = loop.run_until_complete(
                                self.s3_manager.upload_and_cleanup(
                                    session_files,
                                    progress_callback=make_progress_callback(start_index, len(session_files)),
                                    session_id=session.session_id,
                                    base_directory=session.session_dir
                                )
                            )
                        else:
                            result = loop.run_until_complete(
                                self.s3_manager.upload_files(
                                    session_files,
                                    progress_callback=make_progress_callback(start_index, len(session_files)),
                                    session_id=session.session_id,
                                    base_directory=session.session_dir
                                )
                            )
                        return result
                    finally:
                        loop.close()

                # Run the blocking upload in a thread pool executor
                main_loop = asyncio.get_event_loop()
                result = await main_loop.run_in_executor(None, sync_upload)

                if result.success:
                    logger.info(f"Successfully uploaded session {session.session_id}")

                    # Remove from pending uploads
                    self.pending_uploads_manager.remove_session(session.session_id)

                    # Update any PROCESSED_NOT_UPLOADED items for this session
                    for item in self.transfer_queue:
                        if item.sessionId == session.session_id and item.state == TransferState.PROCESSED_NOT_UPLOADED:
                            item.state = TransferState.UPLOADED
                            self.transfer_state_changed.emit(item)

                    succeeded += 1
                    uploaded_file_count += len(session_files)
                else:
                    logger.error(f"Failed to upload session {session.session_id}: {result.error}")
                    failed += 1

            except Exception as e:
                logger.error(f"Exception uploading session {session.session_id}: {e}")
                failed += 1

        # Emit finished signal
        if failed == 0:
            self.global_upload_finished.emit(True)
        else:
            self.global_upload_finished.emit(False)

        logger.info(f"Batch upload complete: {succeeded} sessions succeeded, {failed} sessions failed")
        return (succeeded, failed)

    def restore_pending_sessions(self):
        """Restore pending upload sessions from disk and populate the UI"""
        pending_sessions = self.pending_uploads_manager.get_all_sessions()

        if not pending_sessions:
            logger.info("No pending sessions to restore")
            return

        logger.info(f"Restoring {len(pending_sessions)} pending sessions from disk")

        for session in pending_sessions:
            session_dir = Path(session.session_dir)

            # Verify the session directory still exists
            if not session_dir.exists():
                logger.warning(f"Session directory no longer exists: {session_dir}, removing from pending")
                self.pending_uploads_manager.remove_session(session.session_id)
                continue

            # Store the session directory mapping
            self.session_directories[session.session_id] = str(session_dir)

            # Find all files in the session directory
            session_files = []
            for item in session_dir.rglob("*"):
                if item.is_file() and item.suffix.lower() != ".zip":
                    session_files.append(item)

            # Create FileTransferItem objects for each file
            # We'll create one item per unique device/file in the session
            # Since we don't have device info, we'll create a single placeholder item
            if session_files:
                # Create a single representative item for the session
                first_file = session_files[0]
                transfer_item = FileTransferItem(
                    deviceName="Restored",  # Placeholder device name
                    fileId=f"restored_{session.session_id}",
                    sessionId=session.session_id,
                    state=TransferState.PROCESSED_NOT_UPLOADED,
                    localPath=str(first_file)
                )
                transfer_item.started_at = datetime.fromisoformat(session.recorded_at)
                transfer_item.progress = 100.0  # Files are already downloaded

                # Add to transfer queue
                self.transfer_queue.append(transfer_item)

                # Emit signal to update UI
                self.transfer_state_changed.emit(transfer_item)

                logger.info(f"Restored pending session: {session.session_id} with {len(session_files)} files")

        logger.info(f"Finished restoring {len(pending_sessions)} pending sessions")
