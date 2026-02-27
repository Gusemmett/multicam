import Foundation

/// Network and protocol constants for MultiCam API
public enum MultiCamConstants {
    // MARK: - Network Configuration

    /// TCP port for device server
    public static let tcpPort: UInt16 = 8080

    /// mDNS service type for device discovery
    public static let serviceType = "_multicam._tcp.local."

    // MARK: - NTP Configuration

    /// NTP server for time synchronization
    public static let ntpServer = "pool.ntp.org"

    /// NTP protocol port
    public static let ntpPort: UInt16 = 123

    /// Maximum acceptable NTP round-trip time in seconds
    public static let maxAcceptableRTT: TimeInterval = 0.5

    // MARK: - Synchronization

    /// Default delay for synchronized recording start (seconds)
    public static let syncDelay: TimeInterval = 3.0

    // MARK: - Timeouts

    /// Command timeout in seconds
    public static let commandTimeout: TimeInterval = 60.0

    /// Download stall timeout in seconds (10 minutes)
    public static let downloadStallTimeout: TimeInterval = 600.0

    // MARK: - Transfer Configuration

    /// Chunk size for file downloads (bytes)
    public static let downloadChunkSize = 8192

    // MARK: - File ID Format

    /// File ID format pattern
    ///
    /// Example: Mountain-A1B2C3D4_1729000000123
    public static let fileIdFormat = "{deviceId}_{timestamp}"

    /// Generate a file ID for the current device and time
    /// - Parameter deviceId: Device identifier
    /// - Returns: File ID string
    public static func generateFileId(deviceId: String) -> String {
        let timestamp = Int64(Date().timeIntervalSince1970 * 1000)
        return "\(deviceId)_\(timestamp)"
    }
}
