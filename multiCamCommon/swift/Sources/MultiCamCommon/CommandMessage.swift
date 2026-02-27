import Foundation

/// Command message sent to a MultiCam device
///
/// All commands are sent as JSON over TCP socket.
public struct CommandMessage: Codable {
    /// Command type to execute
    public let command: CommandType

    /// Unix timestamp in seconds (with fractional seconds)
    public let timestamp: TimeInterval

    /// ID of the device sending the command
    public let deviceId: String

    /// File name (required for GET_VIDEO and UPLOAD_TO_CLOUD commands)
    public let fileName: String?

    /// Presigned S3 URL for upload (required for UPLOAD_TO_CLOUD command with presigned URL auth)
    public let uploadUrl: String?

    /// S3 bucket name (required for UPLOAD_TO_CLOUD command with IAM credentials auth)
    public let s3Bucket: String?

    /// S3 object key/path (required for UPLOAD_TO_CLOUD command with IAM credentials auth)
    public let s3Key: String?

    /// AWS access key ID from STS (required for UPLOAD_TO_CLOUD command with IAM credentials auth)
    public let awsAccessKeyId: String?

    /// AWS secret access key from STS (required for UPLOAD_TO_CLOUD command with IAM credentials auth)
    public let awsSecretAccessKey: String?

    /// AWS session token from STS (required for UPLOAD_TO_CLOUD command with IAM credentials auth)
    public let awsSessionToken: String?

    /// AWS region (required for UPLOAD_TO_CLOUD command with IAM credentials auth)
    public let awsRegion: String?

    public init(
        command: CommandType,
        timestamp: TimeInterval,
        deviceId: String = "controller",
        fileName: String? = nil,
        uploadUrl: String? = nil,
        s3Bucket: String? = nil,
        s3Key: String? = nil,
        awsAccessKeyId: String? = nil,
        awsSecretAccessKey: String? = nil,
        awsSessionToken: String? = nil,
        awsRegion: String? = nil
    ) {
        self.command = command
        self.timestamp = timestamp
        self.deviceId = deviceId
        self.fileName = fileName
        self.uploadUrl = uploadUrl
        self.s3Bucket = s3Bucket
        self.s3Key = s3Key
        self.awsAccessKeyId = awsAccessKeyId
        self.awsSecretAccessKey = awsSecretAccessKey
        self.awsSessionToken = awsSessionToken
        self.awsRegion = awsRegion
    }

    // MARK: - Factory Methods

    /// Create a START_RECORDING command
    /// - Parameters:
    ///   - timestamp: Unix timestamp for scheduled recording (nil for immediate)
    ///   - deviceId: ID of the sending device
    /// - Returns: CommandMessage instance
    public static func startRecording(
        timestamp: TimeInterval? = nil,
        deviceId: String = "controller"
    ) -> CommandMessage {
        return CommandMessage(
            command: .startRecording,
            timestamp: timestamp ?? Date().timeIntervalSince1970,
            deviceId: deviceId
        )
    }

    /// Create a STOP_RECORDING command
    /// - Parameter deviceId: ID of the sending device
    /// - Returns: CommandMessage instance
    public static func stopRecording(deviceId: String = "controller") -> CommandMessage {
        return CommandMessage(
            command: .stopRecording,
            timestamp: Date().timeIntervalSince1970,
            deviceId: deviceId
        )
    }

    /// Create a DEVICE_STATUS command
    /// - Parameter deviceId: ID of the sending device
    /// - Returns: CommandMessage instance
    public static func deviceStatus(deviceId: String = "controller") -> CommandMessage {
        return CommandMessage(
            command: .deviceStatus,
            timestamp: Date().timeIntervalSince1970,
            deviceId: deviceId
        )
    }

    /// Create a GET_VIDEO command
    /// - Parameters:
    ///   - fileName: File name to download
    ///   - deviceId: ID of the sending device
    /// - Returns: CommandMessage instance
    public static func getVideo(fileName: String, deviceId: String = "controller") -> CommandMessage {
        return CommandMessage(
            command: .getVideo,
            timestamp: Date().timeIntervalSince1970,
            deviceId: deviceId,
            fileName: fileName
        )
    }

    /// Create a HEARTBEAT command
    /// - Parameter deviceId: ID of the sending device
    /// - Returns: CommandMessage instance
    public static func heartbeat(deviceId: String = "controller") -> CommandMessage {
        return CommandMessage(
            command: .heartbeat,
            timestamp: Date().timeIntervalSince1970,
            deviceId: deviceId
        )
    }

    /// Create a LIST_FILES command
    ///
    /// Note: This command may not be supported on all platforms (e.g., Android).
    /// - Parameter deviceId: ID of the sending device
    /// - Returns: CommandMessage instance
    public static func listFiles(deviceId: String = "controller") -> CommandMessage {
        return CommandMessage(
            command: .listFiles,
            timestamp: Date().timeIntervalSince1970,
            deviceId: deviceId
        )
    }

    /// Create an UPLOAD_TO_CLOUD command
    ///
    /// Uploads the specified file to cloud storage using a presigned S3 URL.
    /// File will be automatically deleted from device after successful upload.
    /// - Parameters:
    ///   - fileName: File name to upload
    ///   - uploadUrl: Presigned S3 URL for upload
    ///   - deviceId: ID of the sending device
    /// - Returns: CommandMessage instance
    public static func uploadToCloud(
        fileName: String,
        uploadUrl: String,
        deviceId: String = "controller"
    ) -> CommandMessage {
        return CommandMessage(
            command: .uploadToCloud,
            timestamp: Date().timeIntervalSince1970,
            deviceId: deviceId,
            fileName: fileName,
            uploadUrl: uploadUrl
        )
    }

    /// Create an UPLOAD_TO_CLOUD command with IAM credentials authentication
    ///
    /// Uploads the specified file to cloud storage using AWS IAM credentials from STS AssumeRole.
    /// File will be automatically deleted from device after successful upload.
    /// - Parameters:
    ///   - fileName: File name to upload
    ///   - s3Bucket: S3 bucket name
    ///   - s3Key: S3 object key/path
    ///   - awsAccessKeyId: AWS access key ID from STS
    ///   - awsSecretAccessKey: AWS secret access key from STS
    ///   - awsSessionToken: AWS session token from STS
    ///   - awsRegion: AWS region (e.g., "us-east-1")
    ///   - deviceId: ID of the sending device
    /// - Returns: CommandMessage instance
    public static func uploadToCloudWithIAM(
        fileName: String,
        s3Bucket: String,
        s3Key: String,
        awsAccessKeyId: String,
        awsSecretAccessKey: String,
        awsSessionToken: String,
        awsRegion: String,
        deviceId: String = "controller"
    ) -> CommandMessage {
        return CommandMessage(
            command: .uploadToCloud,
            timestamp: Date().timeIntervalSince1970,
            deviceId: deviceId,
            fileName: fileName,
            uploadUrl: nil,
            s3Bucket: s3Bucket,
            s3Key: s3Key,
            awsAccessKeyId: awsAccessKeyId,
            awsSecretAccessKey: awsSecretAccessKey,
            awsSessionToken: awsSessionToken,
            awsRegion: awsRegion
        )
    }

    // MARK: - Serialization

    /// Serialize command to JSON data
    /// - Returns: JSON data
    /// - Throws: Encoding error
    public func toJSON() throws -> Data {
        let encoder = JSONEncoder()
        return try encoder.encode(self)
    }

    /// Serialize command to JSON string
    /// - Returns: JSON string
    /// - Throws: Encoding error
    public func toJSONString() throws -> String {
        let data = try toJSON()
        guard let string = String(data: data, encoding: .utf8) else {
            throw NSError(domain: "MultiCamCommon", code: -1, userInfo: [
                NSLocalizedDescriptionKey: "Failed to convert JSON data to string"
            ])
        }
        return string
    }

    /// Deserialize command from JSON data
    /// - Parameter data: JSON data
    /// - Returns: CommandMessage instance
    /// - Throws: Decoding error
    public static func fromJSON(_ data: Data) throws -> CommandMessage {
        let decoder = JSONDecoder()
        return try decoder.decode(CommandMessage.self, from: data)
    }

    /// Deserialize command from JSON string
    /// - Parameter string: JSON string
    /// - Returns: CommandMessage instance
    /// - Throws: Decoding error
    public static func fromJSONString(_ string: String) throws -> CommandMessage {
        guard let data = string.data(using: .utf8) else {
            throw NSError(domain: "MultiCamCommon", code: -1, userInfo: [
                NSLocalizedDescriptionKey: "Failed to convert string to data"
            ])
        }
        return try fromJSON(data)
    }
}
