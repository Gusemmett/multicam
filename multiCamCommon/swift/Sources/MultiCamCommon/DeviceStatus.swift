import Foundation

/// Device status values used in API responses
///
/// All status values use lowercase snake_case for consistency across platforms.
public enum DeviceStatus: String, Codable, CaseIterable {
    /// Device is idle and ready for commands
    case ready = "ready"

    /// Currently recording video
    case recording = "recording"

    /// Recording stop in progress
    case stopping = "stopping"

    /// Error state (check message field for details)
    case error = "error"

    /// Future recording has been scheduled and accepted
    case scheduledRecordingAccepted = "scheduled_recording_accepted"

    /// Recording completed successfully
    case recordingStopped = "recording_stopped"

    /// Command acknowledged
    case commandReceived = "command_received"

    /// Device clock not synchronized via NTP
    case timeNotSynchronized = "time_not_synchronized"

    /// Requested file does not exist
    case fileNotFound = "file_not_found"

    /// Currently uploading file to cloud
    case uploading = "uploading"

    /// Upload added to queue
    case uploadQueued = "upload_queued"

    /// Upload completed successfully (file auto-deleted)
    case uploadCompleted = "upload_completed"

    /// Upload failed (check message field for error)
    case uploadFailed = "upload_failed"

    /// Check if a status indicates a successful operation
    public var isSuccess: Bool {
        switch self {
        case .ready, .recording, .scheduledRecordingAccepted,
             .commandReceived, .recordingStopped, .stopping,
             .uploading, .uploadQueued, .uploadCompleted:
            return true
        case .error, .timeNotSynchronized, .fileNotFound, .uploadFailed:
            return false
        }
    }

    /// Check if a status indicates an error
    public var isError: Bool {
        return !isSuccess
    }
}
