import Foundation

/// Upload item status values
public enum UploadStatus: String, Codable, CaseIterable {
    /// Upload is queued and waiting
    case queued = "queued"

    /// Upload is currently in progress
    case uploading = "uploading"

    /// Upload completed successfully
    case completed = "completed"

    /// Upload failed (see error field)
    case failed = "failed"
}

/// Upload item with progress information
///
/// Represents a single file upload in the device's upload queue.
public struct UploadItem: Codable {
    /// Filename
    public let fileName: String

    /// Total file size in bytes
    public let fileSize: Int64

    /// Bytes uploaded so far
    public let bytesUploaded: Int64

    /// Upload progress percentage (0-100)
    public let uploadProgress: Double

    /// Current upload speed in bytes per second
    public let uploadSpeed: Int64

    /// Upload status (queued, uploading, completed, failed)
    public let status: String

    /// Presigned S3 URL for upload (only present when using presigned URL auth)
    public let uploadUrl: String?

    /// Error message if upload failed
    public let error: String?

    public init(
        fileName: String,
        fileSize: Int64,
        bytesUploaded: Int64,
        uploadProgress: Double,
        uploadSpeed: Int64,
        status: String,
        uploadUrl: String? = nil,
        error: String? = nil
    ) {
        self.fileName = fileName
        self.fileSize = fileSize
        self.bytesUploaded = bytesUploaded
        self.uploadProgress = uploadProgress
        self.uploadSpeed = uploadSpeed
        self.status = status
        self.uploadUrl = uploadUrl
        self.error = error
    }

    /// Get the status as an UploadStatus enum value
    public var uploadStatus: UploadStatus? {
        return UploadStatus(rawValue: status)
    }
}
