import Foundation

/// Status response from a MultiCam device
public struct StatusResponse: Codable {
    /// Unique identifier of the responding device
    public let deviceId: String

    /// Device status (see DeviceStatus enum for standard values)
    public let status: String

    /// Unix timestamp when response was generated
    public let timestamp: TimeInterval

    /// Battery percentage (0.0-100.0), nil if unavailable
    public let batteryLevel: Double?

    /// Type of device (e.g., "iOS", "Android", "Desktop"), nil if unavailable
    public let deviceType: String?

    /// Upload queue (includes in-progress and queued uploads)
    public let uploadQueue: [UploadItem]

    /// Failed upload queue
    public let failedUploadQueue: [UploadItem]

    public init(
        deviceId: String,
        status: String,
        timestamp: TimeInterval,
        batteryLevel: Double? = nil,
        deviceType: String? = nil,
        uploadQueue: [UploadItem] = [],
        failedUploadQueue: [UploadItem] = []
    ) {
        self.deviceId = deviceId
        self.status = status
        self.timestamp = timestamp
        self.batteryLevel = batteryLevel
        self.deviceType = deviceType
        self.uploadQueue = uploadQueue
        self.failedUploadQueue = failedUploadQueue
    }

    /// Get the status as a DeviceStatus enum value
    public var deviceStatus: DeviceStatus? {
        return DeviceStatus(rawValue: status)
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
    /// - Returns: StatusResponse instance
    /// - Throws: Decoding error
    public static func fromJSON(_ data: Data) throws -> StatusResponse {
        let decoder = JSONDecoder()
        return try decoder.decode(StatusResponse.self, from: data)
    }

    /// Deserialize response from JSON string
    /// - Parameter string: JSON string
    /// - Returns: StatusResponse instance
    /// - Throws: Decoding error
    public static func fromJSONString(_ string: String) throws -> StatusResponse {
        guard let data = string.data(using: .utf8) else {
            throw NSError(domain: "MultiCamCommon", code: -1, userInfo: [
                NSLocalizedDescriptionKey: "Failed to convert string to data"
            ])
        }
        return try fromJSON(data)
    }
}
