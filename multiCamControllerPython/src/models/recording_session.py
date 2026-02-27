"""Recording session management"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
from PySide6.QtCore import QObject, Signal as pyqtSignal
import uuid


@dataclass
class UploadProgress:
    """Track upload progress across multiple files"""

    current_file_index: int = 0
    total_files: int = 0
    current_file_progress: float = 0.0
    current_file_name: str = ""
    overall_progress: float = 0.0

    def update(self, file_index: int, total_files: int, file_progress: float, file_name: str):
        """Update progress values"""
        self.current_file_index = file_index
        self.total_files = total_files
        self.current_file_progress = file_progress
        self.current_file_name = file_name

        # Calculate overall progress
        files_completed = float(file_index)
        per_file_contribution = 100.0 / float(total_files) if total_files > 0 else 0
        current_file_contribution = per_file_contribution * (file_progress / 100.0)
        self.overall_progress = (files_completed * per_file_contribution) + current_file_contribution


class RecordingSession(QObject):
    """Manages a recording session across multiple devices"""

    recording_state_changed = pyqtSignal(bool)
    progress_updated = pyqtSignal(str, float)  # device_name, progress

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessionId = str(uuid.uuid4())
        self.isRecording = False
        self.recordingStartTime: Optional[datetime] = None
        self.recordingStopTime: Optional[datetime] = None
        self.recorderName: Optional[str] = None
        self.task: Optional[str] = None
        self.fileIds: Dict[str, str] = {}  # deviceName -> fileId
        self.downloadProgress: Dict[str, float] = {}
        self.uploadProgress: Optional[UploadProgress] = None

    def start_recording(self, recorder_name: str = "", task: str = ""):
        """Start a new recording session"""
        # Generate new session ID for each recording
        self.sessionId = str(uuid.uuid4())
        self.isRecording = True
        self.recordingStartTime = datetime.now()
        self.recordingStopTime = None
        self.recorderName = recorder_name
        self.task = task
        self.fileIds.clear()
        self.downloadProgress.clear()
        self.uploadProgress = None
        self.recording_state_changed.emit(True)

    def stop_recording(self, fileIds: Dict[str, str]):
        """Stop recording and save file IDs"""
        self.isRecording = False
        self.recordingStopTime = datetime.now()
        self.fileIds = fileIds
        self.recording_state_changed.emit(False)

    def reset_session(self):
        """Reset the session to initial state"""
        self.isRecording = False
        self.recordingStartTime = None
        self.recordingStopTime = None
        self.task = None
        self.fileIds.clear()
        self.downloadProgress.clear()
        self.uploadProgress = None
        self.sessionId = str(uuid.uuid4())
        self.recording_state_changed.emit(False)

    def get_duration_seconds(self) -> Optional[float]:
        """Get recording duration in seconds, or None if not available"""
        if self.recordingStartTime and self.recordingStopTime:
            delta = self.recordingStopTime - self.recordingStartTime
            return delta.total_seconds()
        return None
