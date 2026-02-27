import Foundation

/// Metadata for a single video file
public struct FileMetadata: Codable {
    /// Filename
    public let fileName: String

    /// File size in bytes
    public let fileSize: Int64

    /// File creation time (Unix timestamp)
    public let creationDate: TimeInterval

    /// File modification time (Unix timestamp)
    public let modificationDate: TimeInterval

    public init(
        fileName: String,
        fileSize: Int64,
        creationDate: TimeInterval,
        modificationDate: TimeInterval
    ) {
        self.fileName = fileName
        self.fileSize = fileSize
        self.creationDate = creationDate
        self.modificationDate = modificationDate
    }
}

/// Header for binary file transfer
///
/// This is sent as JSON before the binary file data in GET_VIDEO responses.
///
/// Binary protocol:
/// 1. Header size (4 bytes, big-endian uint32)
/// 2. JSON FileResponse header
/// 3. Binary file data
public struct FileResponse: Codable {
    /// Device that owns the file
    public let deviceId: String

    /// Filename
    public let fileName: String

    /// File size in bytes
    public let fileSize: Int64

    /// Status (typically "ready")
    public let status: String

    public init(
        deviceId: String,
        fileName: String,
        fileSize: Int64,
        status: String
    ) {
        self.deviceId = deviceId
        self.fileName = fileName
        self.fileSize = fileSize
        self.status = status
    }

    // MARK: - Serialization

    /// Serialize file response to JSON data
    /// - Returns: JSON data
    /// - Throws: Encoding error
    public func toJSON() throws -> Data {
        let encoder = JSONEncoder()
        return try encoder.encode(self)
    }

    /// Deserialize file response from JSON data
    /// - Parameter data: JSON data
    /// - Returns: FileResponse instance
    /// - Throws: Decoding error
    public static func fromJSON(_ data: Data) throws -> FileResponse {
        let decoder = JSONDecoder()
        return try decoder.decode(FileResponse.self, from: data)
    }
}

/// Response to LIST_FILES command
///
/// Note: This command may not be supported on all platforms.
public struct ListFilesResponse: Codable {
    /// Device ID
    public let deviceId: String

    /// Status (see DeviceStatus enum)
    public let status: String

    /// Response timestamp
    public let timestamp: TimeInterval

    /// List of available files
    public let files: [FileMetadata]

    public init(
        deviceId: String,
        status: String,
        timestamp: TimeInterval,
        files: [FileMetadata]
    ) {
        self.deviceId = deviceId
        self.status = status
        self.timestamp = timestamp
        self.files = files
    }

    // MARK: - Serialization

    /// Serialize list files response to JSON data
    /// - Returns: JSON data
    /// - Throws: Encoding error
    public func toJSON() throws -> Data {
        let encoder = JSONEncoder()
        return try encoder.encode(self)
    }

    /// Deserialize list files response from JSON data
    /// - Parameter data: JSON data
    /// - Returns: ListFilesResponse instance
    /// - Throws: Decoding error
    public static func fromJSON(_ data: Data) throws -> ListFilesResponse {
        let decoder = JSONDecoder()
        return try decoder.decode(ListFilesResponse.self, from: data)
    }
}

/// Response to STOP_RECORDING command
public struct StopRecordingResponse: Codable {
    /// Device ID
    public let deviceId: String

    /// Device status (typically "recording_stopped")
    public let status: String

    /// Response timestamp
    public let timestamp: TimeInterval

    /// File name of the recorded video
    public let fileName: String

    /// File size in bytes
    public let fileSize: Int64

    public init(
        deviceId: String,
        status: String,
        timestamp: TimeInterval,
        fileName: String,
        fileSize: Int64
    ) {
        self.deviceId = deviceId
        self.status = status
        self.timestamp = timestamp
        self.fileName = fileName
        self.fileSize = fileSize
    }

    // MARK: - Serialization

    /// Serialize response to JSON data
    /// - Returns: JSON data
    /// - Throws: Encoding error
    public func toJSON() throws -> Data {
        let encoder = JSONEncoder()
        return try encoder.encode(self)
    }

    /// Deserialize response from JSON data
    /// - Parameter data: JSON data
    /// - Returns: StopRecordingResponse instance
    /// - Throws: Decoding error
    public static func fromJSON(_ data: Data) throws -> StopRecordingResponse {
        let decoder = JSONDecoder()
        return try decoder.decode(StopRecordingResponse.self, from: data)
    }
}

/// Error response from a MultiCam device
public struct ErrorResponse: Codable {
    /// Device ID
    public let deviceId: String

    /// Error status (e.g., "file_not_found", "error")
    public let status: String

    /// Response timestamp
    public let timestamp: TimeInterval

    /// Human-readable error message
    public let message: String

    public init(
        deviceId: String,
        status: String,
        timestamp: TimeInterval,
        message: String
    ) {
        self.deviceId = deviceId
        self.status = status
        self.timestamp = timestamp
        self.message = message
    }

    // MARK: - Serialization

    /// Serialize response to JSON data
    /// - Returns: JSON data
    /// - Throws: Encoding error
    public func toJSON() throws -> Data {
        let encoder = JSONEncoder()
        return try encoder.encode(self)
    }

    /// Deserialize response from JSON data
    /// - Parameter data: JSON data
    /// - Returns: ErrorResponse instance
    /// - Throws: Decoding error
    public static func fromJSON(_ data: Data) throws -> ErrorResponse {
        let decoder = JSONDecoder()
        return try decoder.decode(ErrorResponse.self, from: data)
    }
}
