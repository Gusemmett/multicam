"""
Command and response message types for MultiCam API.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
import json
import time


class CommandType(str, Enum):
    """
    Available command types for the MultiCam API.
    """

    START_RECORDING = "START_RECORDING"
    """Start video recording (immediate or scheduled)"""

    STOP_RECORDING = "STOP_RECORDING"
    """Stop current recording and return file ID"""

    DEVICE_STATUS = "DEVICE_STATUS"
    """Query current device status"""

    GET_VIDEO = "GET_VIDEO"
    """Download video file (binary protocol)"""

    HEARTBEAT = "HEARTBEAT"
    """Health check ping"""

    LIST_FILES = "LIST_FILES"
    """List available video files (may not be supported on all platforms)"""

    UPLOAD_TO_CLOUD = "UPLOAD_TO_CLOUD"
    """Upload video file to cloud using presigned S3 URL"""


@dataclass
class CommandMessage:
    """
    Command message sent to a MultiCam device.

    All commands are sent as JSON over TCP socket.
    """

    command: CommandType
    """Command type to execute"""

    timestamp: float
    """Unix timestamp in seconds (with fractional seconds)"""

    deviceId: str = "controller"
    """ID of the device sending the command"""

    fileName: Optional[str] = None
    """File name (required for GET_VIDEO and UPLOAD_TO_CLOUD commands)"""

    uploadUrl: Optional[str] = None
    """Presigned S3 URL for upload (required for UPLOAD_TO_CLOUD command with presigned URL auth)"""

    s3Bucket: Optional[str] = None
    """S3 bucket name (required for UPLOAD_TO_CLOUD command with IAM credentials auth)"""

    s3Key: Optional[str] = None
    """S3 object key/path (required for UPLOAD_TO_CLOUD command with IAM credentials auth)"""

    awsAccessKeyId: Optional[str] = None
    """AWS access key ID from STS (required for UPLOAD_TO_CLOUD command with IAM credentials auth)"""

    awsSecretAccessKey: Optional[str] = None
    """AWS secret access key from STS (required for UPLOAD_TO_CLOUD command with IAM credentials auth)"""

    awsSessionToken: Optional[str] = None
    """AWS session token from STS (required for UPLOAD_TO_CLOUD command with IAM credentials auth)"""

    awsRegion: Optional[str] = None
    """AWS region (required for UPLOAD_TO_CLOUD command with IAM credentials auth)"""

    def to_json(self) -> str:
        """
        Serialize command to JSON string.

        Returns:
            JSON string representation
        """
        data = {
            "command": self.command.value if isinstance(self.command, CommandType) else self.command,
            "timestamp": self.timestamp,
            "deviceId": self.deviceId,
            "fileName": self.fileName,
            "uploadUrl": self.uploadUrl,
            "s3Bucket": self.s3Bucket,
            "s3Key": self.s3Key,
            "awsAccessKeyId": self.awsAccessKeyId,
            "awsSecretAccessKey": self.awsSecretAccessKey,
            "awsSessionToken": self.awsSessionToken,
            "awsRegion": self.awsRegion,
        }
        return json.dumps(data)

    def to_bytes(self) -> bytes:
        """
        Serialize command to UTF-8 encoded bytes.

        Returns:
            UTF-8 encoded JSON bytes
        """
        return self.to_json().encode('utf-8')

    @classmethod
    def from_json(cls, json_str: str) -> 'CommandMessage':
        """
        Deserialize command from JSON string.

        Args:
            json_str: JSON string to parse

        Returns:
            CommandMessage instance
        """
        data = json.loads(json_str)
        return cls(
            command=CommandType(data['command']),
            timestamp=data['timestamp'],
            deviceId=data.get('deviceId', 'controller'),
            fileName=data.get('fileName'),
            uploadUrl=data.get('uploadUrl'),
            s3Bucket=data.get('s3Bucket'),
            s3Key=data.get('s3Key'),
            awsAccessKeyId=data.get('awsAccessKeyId'),
            awsSecretAccessKey=data.get('awsSecretAccessKey'),
            awsSessionToken=data.get('awsSessionToken'),
            awsRegion=data.get('awsRegion'),
        )

    @classmethod
    def start_recording(cls, timestamp: Optional[float] = None, device_id: str = "controller") -> 'CommandMessage':
        """
        Create a START_RECORDING command.

        Args:
            timestamp: Unix timestamp for scheduled recording (None for immediate)
            device_id: ID of the sending device

        Returns:
            CommandMessage instance
        """
        return cls(
            command=CommandType.START_RECORDING,
            timestamp=timestamp or time.time(),
            deviceId=device_id,
        )

    @classmethod
    def stop_recording(cls, device_id: str = "controller") -> 'CommandMessage':
        """
        Create a STOP_RECORDING command.

        Args:
            device_id: ID of the sending device

        Returns:
            CommandMessage instance
        """
        return cls(
            command=CommandType.STOP_RECORDING,
            timestamp=time.time(),
            deviceId=device_id,
        )

    @classmethod
    def device_status(cls, device_id: str = "controller") -> 'CommandMessage':
        """
        Create a DEVICE_STATUS command.

        Args:
            device_id: ID of the sending device

        Returns:
            CommandMessage instance
        """
        return cls(
            command=CommandType.DEVICE_STATUS,
            timestamp=time.time(),
            deviceId=device_id,
        )

    @classmethod
    def get_video(cls, file_name: str, device_id: str = "controller") -> 'CommandMessage':
        """
        Create a GET_VIDEO command.

        Args:
            file_name: File name to download
            device_id: ID of the sending device

        Returns:
            CommandMessage instance
        """
        return cls(
            command=CommandType.GET_VIDEO,
            timestamp=time.time(),
            deviceId=device_id,
            fileName=file_name,
        )

    @classmethod
    def heartbeat(cls, device_id: str = "controller") -> 'CommandMessage':
        """
        Create a HEARTBEAT command.

        Args:
            device_id: ID of the sending device

        Returns:
            CommandMessage instance
        """
        return cls(
            command=CommandType.HEARTBEAT,
            timestamp=time.time(),
            deviceId=device_id,
        )

    @classmethod
    def list_files(cls, device_id: str = "controller") -> 'CommandMessage':
        """
        Create a LIST_FILES command.

        Note: This command may not be supported on all platforms (e.g., Android).

        Args:
            device_id: ID of the sending device

        Returns:
            CommandMessage instance
        """
        return cls(
            command=CommandType.LIST_FILES,
            timestamp=time.time(),
            deviceId=device_id,
        )

    @classmethod
    def upload_to_cloud(cls, file_name: str, upload_url: str, device_id: str = "controller") -> 'CommandMessage':
        """
        Create an UPLOAD_TO_CLOUD command.

        Uploads the specified file to cloud storage using a presigned S3 URL.
        File will be automatically deleted from device after successful upload.

        Args:
            file_name: File name to upload
            upload_url: Presigned S3 URL for upload
            device_id: ID of the sending device

        Returns:
            CommandMessage instance
        """
        return cls(
            command=CommandType.UPLOAD_TO_CLOUD,
            timestamp=time.time(),
            deviceId=device_id,
            fileName=file_name,
            uploadUrl=upload_url,
        )

    @classmethod
    def upload_to_cloud_with_iam(cls, file_name: str, s3_bucket: str, s3_key: str,
                                 aws_access_key_id: str, aws_secret_access_key: str,
                                 aws_session_token: str, aws_region: str,
                                 device_id: str = "controller") -> 'CommandMessage':
        """
        Create an UPLOAD_TO_CLOUD command with IAM credentials authentication.

        Uploads the specified file to cloud storage using AWS IAM credentials from STS AssumeRole.
        File will be automatically deleted from device after successful upload.

        Args:
            file_name: File name to upload
            s3_bucket: S3 bucket name
            s3_key: S3 object key/path
            aws_access_key_id: AWS access key ID from STS
            aws_secret_access_key: AWS secret access key from STS
            aws_session_token: AWS session token from STS
            aws_region: AWS region (e.g., "us-east-1")
            device_id: ID of the sending device

        Returns:
            CommandMessage instance
        """
        return cls(
            command=CommandType.UPLOAD_TO_CLOUD,
            timestamp=time.time(),
            deviceId=device_id,
            fileName=file_name,
            s3Bucket=s3_bucket,
            s3Key=s3_key,
            awsAccessKeyId=aws_access_key_id,
            awsSecretAccessKey=aws_secret_access_key,
            awsSessionToken=aws_session_token,
            awsRegion=aws_region,
        )


@dataclass
class StatusResponse:
    """
    Status response from a MultiCam device.
    """

    deviceId: str
    """Unique identifier of the responding device"""

    status: str
    """Device status (see DeviceStatus enum for standard values)"""

    timestamp: float
    """Unix timestamp when response was generated"""

    batteryLevel: Optional[float] = None
    """Battery percentage (0.0-100.0), null if unavailable"""

    deviceType: Optional[str] = None
    """Type of device (e.g., "iOS", "Android", "Desktop"), null if unavailable"""

    uploadQueue: List['UploadItem'] = field(default_factory=list)
    """Upload queue (includes in-progress and queued uploads)"""

    failedUploadQueue: List['UploadItem'] = field(default_factory=list)
    """Failed upload queue"""

    @classmethod
    def from_json(cls, json_str: str) -> 'StatusResponse':
        """
        Deserialize response from JSON string.

        Args:
            json_str: JSON string to parse

        Returns:
            StatusResponse instance
        """
        data = json.loads(json_str)
        upload_queue = [UploadItem.from_dict(item) for item in data.get('uploadQueue', [])]
        failed_upload_queue = [UploadItem.from_dict(item) for item in data.get('failedUploadQueue', [])]

        return cls(
            deviceId=data['deviceId'],
            status=data['status'],
            timestamp=data['timestamp'],
            batteryLevel=data.get('batteryLevel'),
            deviceType=data.get('deviceType'),
            uploadQueue=upload_queue,
            failedUploadQueue=failed_upload_queue,
        )

    def to_json(self) -> str:
        """
        Serialize response to JSON string.

        Returns:
            JSON string representation
        """
        data = {
            'deviceId': self.deviceId,
            'status': self.status,
            'timestamp': self.timestamp,
            'batteryLevel': self.batteryLevel,
            'deviceType': self.deviceType,
            'uploadQueue': [asdict(item) for item in self.uploadQueue],
            'failedUploadQueue': [asdict(item) for item in self.failedUploadQueue],
        }
        return json.dumps(data)


@dataclass
class StopRecordingResponse:
    """
    Response to STOP_RECORDING command.
    """

    deviceId: str
    """Device ID"""

    status: str
    """Device status (typically 'recording_stopped')"""

    timestamp: float
    """Response timestamp"""

    fileName: str
    """File name of the recorded video"""

    fileSize: int
    """File size in bytes"""

    @classmethod
    def from_json(cls, json_str: str) -> 'StopRecordingResponse':
        """
        Deserialize response from JSON string.

        Args:
            json_str: JSON string to parse

        Returns:
            StopRecordingResponse instance
        """
        data = json.loads(json_str)
        return cls(
            deviceId=data['deviceId'],
            status=data['status'],
            timestamp=data['timestamp'],
            fileName=data['fileName'],
            fileSize=data['fileSize'],
        )

    def to_json(self) -> str:
        """
        Serialize response to JSON string.

        Returns:
            JSON string representation
        """
        return json.dumps(asdict(self))


@dataclass
class ErrorResponse:
    """
    Error response from a MultiCam device.
    """

    deviceId: str
    """Device ID"""

    status: str
    """Error status (e.g., 'file_not_found', 'error')"""

    timestamp: float
    """Response timestamp"""

    message: str
    """Human-readable error message"""

    @classmethod
    def from_json(cls, json_str: str) -> 'ErrorResponse':
        """
        Deserialize response from JSON string.

        Args:
            json_str: JSON string to parse

        Returns:
            ErrorResponse instance
        """
        data = json.loads(json_str)
        return cls(
            deviceId=data['deviceId'],
            status=data['status'],
            timestamp=data['timestamp'],
            message=data['message'],
        )

    def to_json(self) -> str:
        """
        Serialize response to JSON string.

        Returns:
            JSON string representation
        """
        return json.dumps(asdict(self))


@dataclass
class FileMetadata:
    """
    Metadata for a single video file.
    """

    fileName: str
    """Filename"""

    fileSize: int
    """File size in bytes"""

    creationDate: float
    """File creation time (Unix timestamp)"""

    modificationDate: float
    """File modification time (Unix timestamp)"""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileMetadata':
        """
        Create FileMetadata from dictionary.

        Args:
            data: Dictionary with file metadata

        Returns:
            FileMetadata instance
        """
        return cls(
            fileName=data['fileName'],
            fileSize=data['fileSize'],
            creationDate=data['creationDate'],
            modificationDate=data['modificationDate'],
        )


@dataclass
class FileResponse:
    """
    Header for binary file transfer.

    This is sent as JSON before the binary file data in GET_VIDEO responses.

    Binary protocol:
    1. Header size (4 bytes, big-endian uint32)
    2. JSON FileResponse header
    3. Binary file data
    """

    deviceId: str
    """Device that owns the file"""

    fileName: str
    """Filename"""

    fileSize: int
    """File size in bytes"""

    status: str
    """Status (typically 'ready')"""

    @classmethod
    def from_json(cls, json_str: str) -> 'FileResponse':
        """
        Deserialize file response from JSON string.

        Args:
            json_str: JSON string to parse

        Returns:
            FileResponse instance
        """
        data = json.loads(json_str)
        return cls(
            deviceId=data['deviceId'],
            fileName=data['fileName'],
            fileSize=data['fileSize'],
            status=data['status'],
        )

    def to_json(self) -> str:
        """
        Serialize file response to JSON string.

        Returns:
            JSON string representation
        """
        return json.dumps(asdict(self))


@dataclass
class ListFilesResponse:
    """
    Response to LIST_FILES command.

    Note: This command may not be supported on all platforms.
    """

    deviceId: str
    """Device ID"""

    status: str
    """Status (see DeviceStatus enum)"""

    timestamp: float
    """Response timestamp"""

    files: List[FileMetadata] = field(default_factory=list)
    """List of available files"""

    @classmethod
    def from_json(cls, json_str: str) -> 'ListFilesResponse':
        """
        Deserialize list files response from JSON string.

        Args:
            json_str: JSON string to parse

        Returns:
            ListFilesResponse instance
        """
        data = json.loads(json_str)
        files = [FileMetadata.from_dict(f) for f in data.get('files', [])]
        return cls(
            deviceId=data['deviceId'],
            status=data['status'],
            timestamp=data['timestamp'],
            files=files,
        )

    def to_json(self) -> str:
        """
        Serialize list files response to JSON string.

        Returns:
            JSON string representation
        """
        data = {
            'deviceId': self.deviceId,
            'status': self.status,
            'timestamp': self.timestamp,
            'files': [asdict(f) for f in self.files],
        }
        return json.dumps(data)


class UploadStatus(str, Enum):
    """Upload item status values."""

    QUEUED = "queued"
    """Upload is queued and waiting"""

    UPLOADING = "uploading"
    """Upload is currently in progress"""

    COMPLETED = "completed"
    """Upload completed successfully"""

    FAILED = "failed"
    """Upload failed (see error field)"""


@dataclass
class UploadItem:
    """
    Upload item with progress information.

    Represents a single file upload in the device's upload queue.
    """

    fileName: str
    """Filename"""

    fileSize: int
    """Total file size in bytes"""

    bytesUploaded: int
    """Bytes uploaded so far"""

    uploadProgress: float
    """Upload progress percentage (0-100)"""

    uploadSpeed: int
    """Current upload speed in bytes per second"""

    status: str
    """Upload status (queued, uploading, completed, failed)"""

    uploadUrl: Optional[str] = None
    """Presigned S3 URL for upload (only present when using presigned URL auth)"""

    error: Optional[str] = None
    """Error message if upload failed"""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UploadItem':
        """
        Create UploadItem from dictionary.

        Args:
            data: Dictionary with upload item data

        Returns:
            UploadItem instance
        """
        return cls(
            fileName=data['fileName'],
            fileSize=data['fileSize'],
            bytesUploaded=data['bytesUploaded'],
            uploadProgress=data['uploadProgress'],
            uploadSpeed=data['uploadSpeed'],
            status=data['status'],
            uploadUrl=data.get('uploadUrl'),
            error=data.get('error'),
        )
