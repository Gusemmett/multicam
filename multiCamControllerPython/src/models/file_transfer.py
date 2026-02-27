"""File transfer tracking"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime


class TransferState(Enum):
    """State of a file transfer"""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PROCESSED_NOT_UPLOADED = "processed_not_uploaded"  # Downloaded and processed, waiting for manual upload
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class ErrorCategory(Enum):
    """Category of transfer error"""

    NETWORK = "network"  # Retryable network errors
    TIMEOUT = "timeout"  # Retryable timeout errors
    AUTH = "auth"  # Authentication/authorization errors
    NOT_FOUND = "not_found"  # File not found
    DISK_FULL = "disk_full"  # Storage full
    UNKNOWN = "unknown"  # Unknown error


@dataclass
class FileTransferItem:
    """Tracks a single file transfer (download + upload)"""

    deviceName: str
    fileId: str
    sessionId: str
    state: TransferState = TransferState.PENDING
    progress: float = 0.0
    localPath: Optional[str] = None
    s3Key: Optional[str] = None
    error: Optional[str] = None
    upload_source: Optional[str] = None  # "device" for direct-to-cloud, "local" for from downloaded files

    # Retry configuration
    max_retries: int = 3
    retry_count: int = 0
    last_retry_at: Optional[datetime] = None

    # Cancellation support
    is_cancelled: bool = False
    cancel_requested: bool = False

    # Transfer metrics
    download_speed: float = 0.0  # bytes per second
    upload_speed: float = 0.0  # bytes per second
    bytes_transferred: int = 0
    total_bytes: Optional[int] = None
    eta_seconds: Optional[float] = None

    # Error categorization
    error_category: Optional[ErrorCategory] = None

    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def state_icon(self) -> str:
        """Get text icon for current state"""
        icons = {
            TransferState.PENDING: "[PENDING]",
            TransferState.DOWNLOADING: "[DOWNLOADING]",
            TransferState.DOWNLOADED: "[DONE]",
            TransferState.PROCESSED_NOT_UPLOADED: "[PENDING UPLOAD]",
            TransferState.UPLOADING: "[UPLOADING]",
            TransferState.UPLOADED: "[UPLOADED]",
            TransferState.FAILED: "[FAILED]",
            TransferState.CANCELLED: "[CANCELLED]",
            TransferState.RETRYING: "[RETRY]",
        }
        return icons[self.state]

    @property
    def can_retry(self) -> bool:
        """Check if this transfer can be retried"""
        return (
            self.state == TransferState.FAILED
            and self.retry_count < self.max_retries
            and self.error_category in [ErrorCategory.NETWORK, ErrorCategory.TIMEOUT, ErrorCategory.UNKNOWN]
        )

    @property
    def is_active(self) -> bool:
        """Check if this transfer is currently active"""
        return self.state in [
            TransferState.DOWNLOADING,
            TransferState.UPLOADING,
            TransferState.RETRYING,
        ]

    @property
    def is_complete(self) -> bool:
        """Check if this transfer is complete (success or terminal failure)"""
        return self.state in [
            TransferState.UPLOADED,
            TransferState.CANCELLED,
        ] or (self.state == TransferState.FAILED and not self.can_retry)

    @property
    def current_speed(self) -> float:
        """Get current transfer speed based on state"""
        if self.state in [TransferState.DOWNLOADING, TransferState.RETRYING]:
            return self.download_speed
        elif self.state == TransferState.UPLOADING:
            return self.upload_speed
        return 0.0

    @property
    def speed_text(self) -> str:
        """Get formatted speed text"""
        speed = self.current_speed
        if speed == 0:
            return ""

        if speed < 1024:
            return f"{speed:.0f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.1f} MB/s"

    @property
    def eta_text(self) -> str:
        """Get formatted ETA text"""
        if self.eta_seconds is None or self.eta_seconds <= 0:
            return ""

        if self.eta_seconds < 60:
            return f"{int(self.eta_seconds)}s"
        elif self.eta_seconds < 3600:
            minutes = int(self.eta_seconds / 60)
            return f"{minutes}m"
        else:
            hours = int(self.eta_seconds / 3600)
            minutes = int((self.eta_seconds % 3600) / 60)
            return f"{hours}h {minutes}m"

    @property
    def overall_progress(self) -> float:
        """Get overall progress (0-100) for download phase (or 0-100 for special upload tasks)"""
        if self.state == TransferState.PENDING:
            return 0.0
        elif self.state in [TransferState.DOWNLOADING, TransferState.RETRYING]:
            # Download progress is 0-100%
            return self.progress
        elif self.state in [TransferState.DOWNLOADED, TransferState.PROCESSED_NOT_UPLOADED]:
            # Download complete
            return 100.0
        elif self.state == TransferState.UPLOADING:
            # For special "Upload to S3 Task" items, show upload progress 0-100%
            return self.progress
        elif self.state == TransferState.UPLOADED:
            return 100.0
        elif self.state in [TransferState.FAILED, TransferState.CANCELLED]:
            # Keep whatever progress was achieved
            return self.progress
        return 0.0

    @property
    def status_text(self) -> str:
        """Get human-readable status text"""
        # Special handling for Upload to S3 Task
        is_upload_task = self.fileId == "UPLOAD_SESSION_TO_S3"

        if self.state == TransferState.PENDING:
            return "Waiting for Processing" if not is_upload_task else "Waiting to Upload"
        elif self.state == TransferState.DOWNLOADING:
            return f"Downloading from Device {self.speed_text} {self.eta_text}".strip()
        elif self.state == TransferState.DOWNLOADED:
            return "Download Complete"
        elif self.state == TransferState.PROCESSED_NOT_UPLOADED:
            return "Ready to Upload (Manual Mode)"
        elif self.state == TransferState.UPLOADING:
            if is_upload_task:
                return f"Uploading Session Files to S3 {self.speed_text} {self.eta_text}".strip()
            elif self.upload_source == "device":
                return f"Uploading from Device to S3 {self.speed_text} {self.eta_text}".strip()
            elif self.upload_source == "local":
                return f"Uploading from Local to S3 {self.speed_text} {self.eta_text}".strip()
            else:
                return f"Uploading to Cloud {self.speed_text} {self.eta_text}".strip()
        elif self.state == TransferState.UPLOADED:
            return "Upload Complete" if is_upload_task else "Complete"
        elif self.state == TransferState.FAILED:
            retry_info = f" (Retry {self.retry_count}/{self.max_retries})" if self.retry_count > 0 else ""
            return f"Failed{retry_info}: {self.error}"
        elif self.state == TransferState.CANCELLED:
            return "Cancelled"
        elif self.state == TransferState.RETRYING:
            return f"Retrying Download (Attempt {self.retry_count + 1}/{self.max_retries})"
        return ""

    def request_cancel(self):
        """Request cancellation of this transfer"""
        self.cancel_requested = True

    def mark_cancelled(self):
        """Mark this transfer as cancelled"""
        self.is_cancelled = True
        self.state = TransferState.CANCELLED
        self.completed_at = datetime.now()

    def increment_retry(self):
        """Increment retry count and update timestamp"""
        self.retry_count += 1
        self.last_retry_at = datetime.now()
        self.state = TransferState.RETRYING
