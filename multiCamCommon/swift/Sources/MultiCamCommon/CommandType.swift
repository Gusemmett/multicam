import Foundation

/// Available command types for the MultiCam API
public enum CommandType: String, Codable, CaseIterable {
    /// Start video recording (immediate or scheduled)
    case startRecording = "START_RECORDING"

    /// Stop current recording and return file ID
    case stopRecording = "STOP_RECORDING"

    /// Query current device status
    case deviceStatus = "DEVICE_STATUS"

    /// Download video file (binary protocol)
    case getVideo = "GET_VIDEO"

    /// Health check ping
    case heartbeat = "HEARTBEAT"

    /// List available video files (may not be supported on all platforms)
    case listFiles = "LIST_FILES"

    /// Upload video file to cloud using presigned S3 URL
    case uploadToCloud = "UPLOAD_TO_CLOUD"
}
