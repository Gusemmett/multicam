"""Device communication via TCP"""

import asyncio
import struct
import json
import logging
from pathlib import Path
from typing import Dict, Callable, Optional, Union

from PySide6.QtCore import QObject, Signal as pyqtSignal

from multicam_common import CommandMessage, StatusResponse, StopRecordingResponse, ErrorResponse, CommandType, TCP_PORT
from multicam_common import COMMAND_TIMEOUT, DOWNLOAD_CHUNK_SIZE

from models.device import MultiCamDevice
from utils.constants import DOWNLOADS_DIR_NAME, DOWNLOAD_STALL_TIMEOUT

logger = logging.getLogger(__name__)


class DeviceCommunication(QObject):
    """Handles TCP communication with devices"""

    command_sent = pyqtSignal(str, str)  # device_name, command
    response_received = pyqtSignal(str, StatusResponse)  # device_name, response
    download_progress = pyqtSignal(str, float)  # file_name, progress

    async def send_command(
        self,
        device: MultiCamDevice,
        command: CommandMessage,
        progress_callback: Optional[Callable[[float], None]] = None,
        session_id: Optional[str] = None,
        downloads_directory: Optional[str] = None,
    ) -> Union[StatusResponse, StopRecordingResponse, ErrorResponse]:
        """Send a command to a single device"""

        try:
            # Validate port
            if not (0 < device.port <= 65535):
                raise ValueError(f"Invalid port: {device.port}")

            # Connect to device
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(device.ip, device.port), timeout=COMMAND_TIMEOUT
            )

            try:
                # Send command
                logger.debug(f"Sending {command.command} to {device.display_name}")

                # Debug: Log full request
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"REQUEST to {device.display_name} ({device.ip}:{device.port}):")
                    logger.debug(f"   Command JSON: {command.to_json()}")

                writer.write(command.to_bytes())
                await writer.drain()

                self.command_sent.emit(device.name, command.command)

                # Handle response based on command type
                if command.command == CommandType.GET_VIDEO:
                    # Handle file download
                    file_path = await self._handle_file_download(
                        reader, writer, command.fileName, progress_callback, session_id, downloads_directory
                    )
                    # Create a StatusResponse for successful download
                    # Note: Store file path in status field as a workaround since message field is deprecated
                    response = StatusResponse(
                        deviceId=device.id,
                        status=file_path,  # Store file path here temporarily
                        timestamp=0.0,  # Not used for downloads
                        batteryLevel=None,
                        uploadQueue=[],
                        failedUploadQueue=[]
                    )
                else:
                    # Handle JSON response
                    response = await self._handle_json_response(reader, command.command, device.id)

                self.response_received.emit(device.name, response)
                return response

            finally:
                writer.close()
                await writer.wait_closed()

        except asyncio.TimeoutError:
            logger.error(f"Timeout communicating with {device.display_name}")
            raise
        except Exception as e:
            logger.error(f"Communication error with {device.display_name}: {e}")
            raise

    async def _handle_json_response(
        self, reader: asyncio.StreamReader, command: CommandType, device_id: str
    ) -> Union[StatusResponse, StopRecordingResponse, ErrorResponse]:
        """Handle JSON response from device and parse appropriate response type"""

        # Read response (up to 64KB)
        response_data = await asyncio.wait_for(reader.read(65536), timeout=COMMAND_TIMEOUT)

        if not response_data:
            raise ValueError("Empty response received")

        response_text = response_data.decode("utf-8").strip()

        # Debug: Log full response
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"RESPONSE for {command}:")
            logger.debug(f"   Raw data: {response_text}")
            logger.debug(f"   Length: {len(response_data)} bytes")

        # Try to parse as JSON
        try:
            response_json = json.loads(response_text)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"   Parsed as JSON: {response_json}")

            # Determine response type based on status field
            status = response_json.get('status', '')

            if status == 'recording_stopped':
                # Parse as StopRecordingResponse
                return StopRecordingResponse.from_json(response_text)
            elif 'fileName' in response_json and 'fileSize' in response_json:
                # Also parse as StopRecordingResponse if it has the structure
                return StopRecordingResponse.from_json(response_text)
            elif status in ['file_not_found', 'error'] or 'message' in response_json:
                # Parse as ErrorResponse
                return ErrorResponse.from_json(response_text)
            else:
                # Default to StatusResponse
                return StatusResponse.from_json(response_text)
        except json.JSONDecodeError:
            # Plain text responses are not supported in the new API
            # Devices should return proper JSON responses
            logger.error(f"Received plain text response (not valid JSON): {response_text}")
            raise ValueError(f"Device returned non-JSON response: {response_text}")

    async def _handle_file_download(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        file_name: str,
        progress_callback: Optional[Callable[[float], None]] = None,
        session_id: Optional[str] = None,
        downloads_directory: Optional[str] = None,
    ) -> str:
        """Handle binary file download"""

        logger.info(f"Starting file download for {file_name}")

        # Read header size (4 bytes, big-endian uint32)
        header_size_data = await reader.readexactly(4)
        header_size = struct.unpack(">I", header_size_data)[0]
        logger.info(f"Header size: {header_size} bytes")

        # Read header JSON
        header_data = await reader.readexactly(header_size)
        header_info = json.loads(header_data.decode("utf-8"))

        file_name = header_info["fileName"]
        file_size = header_info["fileSize"]

        logger.info(
            f"File: {file_name}, Size: {file_size} bytes ({file_size / 1024 / 1024:.2f} MB)"
        )

        # Debug: Log file download header
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"FILE DOWNLOAD HEADER: {header_info}")

        # Determine base downloads directory from settings or use default
        if downloads_directory:
            base_downloads_dir = Path(downloads_directory)
            logger.info(f"Using custom downloads directory: {base_downloads_dir}")
        else:
            base_downloads_dir = Path.home() / "Downloads" / DOWNLOADS_DIR_NAME
            logger.info(f"Using default downloads directory: {base_downloads_dir}")

        if session_id:
            # Create session-specific subdirectory
            downloads_dir = base_downloads_dir / session_id
            logger.info(f"Using session directory: {session_id}")
        else:
            # Fallback to base directory if no session ID
            downloads_dir = base_downloads_dir

        downloads_dir.mkdir(parents=True, exist_ok=True)

        local_path = downloads_dir / file_name

        # Download file data
        bytes_received = 0

        with open(local_path, "wb") as f:
            while bytes_received < file_size:
                remaining = file_size - bytes_received
                chunk_size = min(DOWNLOAD_CHUNK_SIZE, remaining)

                # Read chunk with stall timeout
                chunk = await asyncio.wait_for(
                    reader.read(chunk_size), timeout=DOWNLOAD_STALL_TIMEOUT
                )

                if not chunk:
                    raise ValueError("Connection closed during download")

                f.write(chunk)
                bytes_received += len(chunk)

                # Update progress
                progress = bytes_received / file_size
                if progress_callback:
                    progress_callback(progress)

                self.download_progress.emit(file_name, progress * 100)

        logger.info(f"File downloaded: {local_path}")
        return str(local_path)

    async def send_command_to_all_devices(
        self,
        devices: list[MultiCamDevice],
        command: CommandMessage,
        sync_delay: float = 0.0,
    ) -> Dict[str, Union[StatusResponse, StopRecordingResponse, ErrorResponse]]:
        """Send command to all devices concurrently"""

        # For START_RECORDING, calculate future timestamp
        if command.command == CommandType.START_RECORDING and sync_delay > 0:
            import time

            sync_timestamp = time.time() + sync_delay
            command = CommandMessage(
                command=command.command,
                timestamp=sync_timestamp,
                deviceId=command.deviceId,
                fileName=getattr(command, 'fileName', None),
            )
            logger.info(
                f"Broadcasting synchronized {command.command.value} to {len(devices)} device(s)"
            )
            logger.info(f"Scheduled start time: {sync_timestamp} (in {sync_delay} seconds)")

        # Send commands concurrently
        tasks = [self.send_command(device, command) for device in devices]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build results dictionary
        response_dict = {}
        for device, result in zip(devices, results):
            if isinstance(result, Exception):
                logger.error(f"Error from {device.name}: {result}")
                import time
                # Create error response using new API
                response_dict[device.name] = StatusResponse(
                    deviceId=device.id,
                    status="error",
                    timestamp=time.time(),
                    batteryLevel=None,
                    uploadQueue=[],
                    failedUploadQueue=[]
                )
            else:
                logger.info(f"Response from {device.name}: {result.status}")
                response_dict[device.name] = result

        return response_dict
