"""Manages pending uploads queue with persistence"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from PySide6.QtCore import QObject, Signal as pyqtSignal

logger = logging.getLogger(__name__)


@dataclass
class PendingUploadSession:
    """Represents a session waiting to be uploaded"""

    session_id: str
    session_dir: str
    recorder_name: str
    recorded_at: str  # ISO format datetime
    file_count: int
    total_size_bytes: int
    recording_duration_seconds: Optional[float] = None  # Duration of recording in seconds

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PendingUploadSession":
        """Create from dictionary"""
        return cls(**data)


class PendingUploadsManager(QObject):
    """Manages pending uploads with JSON persistence"""

    pending_uploads_changed = pyqtSignal()  # Emitted when pending uploads list changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pending_sessions: List[PendingUploadSession] = []
        self._persistence_path = Path.home() / ".multicam" / "pending_uploads.json"
        self._ensure_persistence_dir()
        self.load()

    def _ensure_persistence_dir(self):
        """Ensure the persistence directory exists"""
        try:
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create persistence directory: {e}")

    def add_session(
        self,
        session_id: str,
        session_dir: str,
        recorder_name: str,
        recorded_at: datetime,
        recording_duration_seconds: Optional[float] = None,
    ) -> bool:
        """
        Add a session to the pending uploads queue.

        Args:
            session_id: Unique session identifier
            session_dir: Directory containing session files
            recorder_name: Name of the person who recorded
            recorded_at: Timestamp when recording started
            recording_duration_seconds: Duration of recording in seconds

        Returns:
            True if added successfully, False otherwise
        """
        try:
            # Check if session already exists
            if any(s.session_id == session_id for s in self.pending_sessions):
                logger.warning(f"Session {session_id} already in pending uploads queue")
                return False

            # Calculate total size and file count
            session_path = Path(session_dir)
            if not session_path.exists():
                logger.error(f"Session directory does not exist: {session_dir}")
                return False

            file_count = 0
            total_size = 0
            for item in session_path.rglob("*"):
                if item.is_file() and item.suffix.lower() != ".zip":
                    file_count += 1
                    total_size += item.stat().st_size

            # Create pending session
            pending_session = PendingUploadSession(
                session_id=session_id,
                session_dir=session_dir,
                recorder_name=recorder_name,
                recorded_at=recorded_at.isoformat(),
                file_count=file_count,
                total_size_bytes=total_size,
                recording_duration_seconds=recording_duration_seconds,
            )

            self.pending_sessions.append(pending_session)
            self.save()
            self.pending_uploads_changed.emit()

            logger.info(
                f"Added session {session_id} to pending uploads: {file_count} files, "
                f"{total_size / (1024 * 1024):.1f} MB"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to add session to pending uploads: {e}")
            return False

    def remove_session(self, session_id: str) -> bool:
        """
        Remove a session from the pending uploads queue.

        Args:
            session_id: Session to remove

        Returns:
            True if removed, False if not found
        """
        initial_count = len(self.pending_sessions)
        self.pending_sessions = [s for s in self.pending_sessions if s.session_id != session_id]

        if len(self.pending_sessions) < initial_count:
            self.save()
            self.pending_uploads_changed.emit()
            logger.info(f"Removed session {session_id} from pending uploads")
            return True

        return False

    def get_session(self, session_id: str) -> Optional[PendingUploadSession]:
        """Get a pending session by ID"""
        return next((s for s in self.pending_sessions if s.session_id == session_id), None)

    def get_all_sessions(self) -> List[PendingUploadSession]:
        """Get all pending sessions"""
        return self.pending_sessions.copy()

    def get_total_size(self) -> int:
        """Get total size of all pending uploads in bytes"""
        return sum(s.total_size_bytes for s in self.pending_sessions)

    def get_total_file_count(self) -> int:
        """Get total number of files across all pending sessions"""
        return sum(s.file_count for s in self.pending_sessions)

    def clear_all(self) -> bool:
        """Clear all pending uploads"""
        self.pending_sessions.clear()
        self.save()
        self.pending_uploads_changed.emit()
        logger.info("Cleared all pending uploads")
        return True

    def save(self) -> bool:
        """
        Save pending uploads to JSON file.

        Returns:
            True if successful, False otherwise
        """
        try:
            data = {
                "pending_sessions": [s.to_dict() for s in self.pending_sessions],
                "last_updated": datetime.now().isoformat(),
            }

            with open(self._persistence_path, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self.pending_sessions)} pending sessions")
            return True

        except Exception as e:
            logger.error(f"Failed to save pending uploads: {e}")
            return False

    def load(self) -> bool:
        """
        Load pending uploads from JSON file.

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self._persistence_path.exists():
                logger.info("No pending uploads file found, starting fresh")
                return True

            with open(self._persistence_path, "r") as f:
                data = json.load(f)

            self.pending_sessions = [
                PendingUploadSession.from_dict(s) for s in data.get("pending_sessions", [])
            ]

            logger.info(f"Loaded {len(self.pending_sessions)} pending sessions")

            # Verify that all session directories still exist
            self._verify_sessions()

            return True

        except Exception as e:
            logger.error(f"Failed to load pending uploads: {e}")
            return False

    def _verify_sessions(self):
        """Verify that all pending session directories still exist, remove those that don't"""
        initial_count = len(self.pending_sessions)
        valid_sessions = []

        for session in self.pending_sessions:
            if Path(session.session_dir).exists():
                valid_sessions.append(session)
            else:
                logger.warning(
                    f"Session directory no longer exists, removing from pending uploads: "
                    f"{session.session_dir}"
                )

        self.pending_sessions = valid_sessions

        if len(self.pending_sessions) < initial_count:
            self.save()
            logger.info(
                f"Removed {initial_count - len(self.pending_sessions)} invalid sessions"
            )

    def format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human-readable string"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def get_summary_text(self) -> str:
        """Get summary text for pending uploads"""
        count = len(self.pending_sessions)
        if count == 0:
            return "No pending uploads"

        total_size = self.get_total_size()
        size_str = self.format_size(total_size)

        session_word = "session" if count == 1 else "sessions"
        return f"{count} {session_word}, {size_str}"
