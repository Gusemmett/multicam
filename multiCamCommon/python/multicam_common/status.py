"""
Device status and type enumerations for MultiCam API.
"""

from enum import Enum


class DeviceType(str, Enum):
    """
    Device type values used in API responses.
    """

    IOS_IPHONE = "iOS:iPhone"
    """iOS device (iPhone)"""

    ANDROID_PHONE = "Android:Phone"
    """Android phone device"""

    ANDROID_QUEST = "Android:Quest"
    """Android Quest VR headset"""

    OAK = "Oak"
    """OAK camera device"""


class DeviceStatus(str, Enum):
    """
    Device status values used in API responses.

    All status values use lowercase snake_case for consistency.
    """

    READY = "ready"
    """Device is idle and ready for commands"""

    RECORDING = "recording"
    """Currently recording video"""

    STOPPING = "stopping"
    """Recording stop in progress"""

    ERROR = "error"
    """Error state (check message field for details)"""

    SCHEDULED_RECORDING_ACCEPTED = "scheduled_recording_accepted"
    """Future recording has been scheduled and accepted"""

    RECORDING_STOPPED = "recording_stopped"
    """Recording completed successfully"""

    COMMAND_RECEIVED = "command_received"
    """Command acknowledged"""

    TIME_NOT_SYNCHRONIZED = "time_not_synchronized"
    """Device clock not synchronized via NTP"""

    FILE_NOT_FOUND = "file_not_found"
    """Requested file does not exist"""

    UPLOADING = "uploading"
    """Currently uploading file to cloud"""

    UPLOAD_QUEUED = "upload_queued"
    """Upload added to queue"""

    UPLOAD_COMPLETED = "upload_completed"
    """Upload completed successfully (file auto-deleted)"""

    UPLOAD_FAILED = "upload_failed"
    """Upload failed (check message field for error)"""

    CAMERA_DISCONNECTED = "camera_disconnected"
    """OAK camera is not connected via USB"""

    @classmethod
    def is_success(cls, status: str) -> bool:
        """
        Check if a status string indicates a successful operation.

        Args:
            status: Status string to check

        Returns:
            True if status indicates success, False otherwise
        """
        success_statuses = {
            cls.READY.value,
            cls.RECORDING.value,
            cls.SCHEDULED_RECORDING_ACCEPTED.value,
            cls.COMMAND_RECEIVED.value,
            cls.RECORDING_STOPPED.value,
            cls.STOPPING.value,
            cls.UPLOADING.value,
            cls.UPLOAD_QUEUED.value,
            cls.UPLOAD_COMPLETED.value,
        }
        return status.lower() in success_statuses

    @classmethod
    def is_error(cls, status: str) -> bool:
        """
        Check if a status string indicates an error.

        Args:
            status: Status string to check

        Returns:
            True if status indicates an error, False otherwise
        """
        error_statuses = {
            cls.ERROR.value,
            cls.TIME_NOT_SYNCHRONIZED.value,
            cls.FILE_NOT_FOUND.value,
            cls.UPLOAD_FAILED.value,
            cls.CAMERA_DISCONNECTED.value,
        }
        return status.lower() in error_statuses
