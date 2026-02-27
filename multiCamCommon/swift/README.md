# MultiCam Common - Swift Package

Swift implementation of shared types and constants for the MultiCam synchronized recording API.

## Requirements

- iOS 16.0+ / macOS 13.0+
- Swift 5.9+

## Installation

### Swift Package Manager

Add this package to your `Package.swift`:

```swift
dependencies: [
    .package(url: "https://github.com/yourusername/multiCamCommon.git", from: "1.0.0")
]
```

Or in Xcode:
1. File → Add Package Dependencies
2. Enter the repository URL
3. Select version 1.0.0 or later

## Usage

### Importing

```swift
import MultiCamCommon
```

### Creating Commands

```swift
import Foundation

// Start recording immediately
let cmd = CommandMessage.startRecording()
let jsonData = try cmd.toJSON()

// Start recording at a scheduled time (3 seconds from now)
let syncTime = Date().timeIntervalSince1970 + 3.0
let scheduledCmd = CommandMessage.startRecording(timestamp: syncTime)

// Stop recording
let stopCmd = CommandMessage.stopRecording()

// Query device status
let statusCmd = CommandMessage.deviceStatus()

// Download a video file
let getVideoCmd = CommandMessage.getVideo(fileId: "device-id_1729000000123")

// List available files
let listCmd = CommandMessage.listFiles()

// Heartbeat
let heartbeatCmd = CommandMessage.heartbeat()
```

### Parsing Responses

```swift
// Parse a status response
let jsonString = """
{
    "deviceId": "device-123",
    "status": "ready",
    "timestamp": 1729000000.456,
    "isRecording": false
}
"""

let response = try StatusResponse.fromJSONString(jsonString)

print("Device: \(response.deviceId)")
print("Status: \(response.status)")
print("Recording: \(response.isRecording)")

// Check if status is successful
if let deviceStatus = response.deviceStatus {
    if deviceStatus.isSuccess {
        print("Operation successful!")
    }
}
```

### Working with Device Status

```swift
// Use status enum
if response.deviceStatus == .ready {
    print("Device is ready")
}

// Check for errors
if let status = response.deviceStatus, status.isError {
    print("Error: \(response.message ?? "Unknown error")")
}

// All available statuses
for status in DeviceStatus.allCases {
    print(status.rawValue)
}
```

### Constants

```swift
// Network constants
let port = MultiCamConstants.tcpPort                    // 8080
let serviceType = MultiCamConstants.serviceType         // "_multicam._tcp.local."
let ntpServer = MultiCamConstants.ntpServer             // "pool.ntp.org"

// Timing constants
let syncDelay = MultiCamConstants.syncDelay             // 3.0 seconds
let timeout = MultiCamConstants.commandTimeout          // 60.0 seconds

// Transfer constants
let chunkSize = MultiCamConstants.downloadChunkSize     // 8192 bytes

// Generate a file ID
let fileId = MultiCamConstants.generateFileId(deviceId: "iPhone-ABC123")
// Result: "iPhone-ABC123_1729000000123"
```

### Complete Example: Send Command to Device

```swift
import Foundation
import Network
import MultiCamCommon

func sendCommand(to host: String, command: CommandMessage) async throws -> StatusResponse {
    let connection = NWConnection(
        host: NWEndpoint.Host(host),
        port: NWEndpoint.Port(rawValue: MultiCamConstants.tcpPort)!,
        using: .tcp
    )

    return try await withCheckedThrowingContinuation { continuation in
        connection.stateUpdateHandler = { state in
            switch state {
            case .ready:
                // Send command
                let jsonData = try! command.toJSON()
                connection.send(content: jsonData, completion: .contentProcessed { error in
                    if let error = error {
                        continuation.resume(throwing: error)
                        return
                    }

                    // Receive response
                    connection.receive(minimumIncompleteLength: 1, maximumLength: 4096) { data, _, _, error in
                        if let error = error {
                            continuation.resume(throwing: error)
                            return
                        }

                        guard let data = data else {
                            continuation.resume(throwing: NSError(domain: "MultiCam", code: -1))
                            return
                        }

                        do {
                            let response = try StatusResponse.fromJSON(data)
                            continuation.resume(returning: response)
                        } catch {
                            continuation.resume(throwing: error)
                        }

                        connection.cancel()
                    }
                })

            case .failed(let error):
                continuation.resume(throwing: error)
                connection.cancel()

            default:
                break
            }
        }

        connection.start(queue: .global())
    }
}

// Usage
Task {
    let cmd = CommandMessage.startRecording()
    let response = try await sendCommand(to: "192.168.1.100", command: cmd)
    print("Status: \(response.status)")
    print("Recording: \(response.isRecording)")
}
```

### File Transfer Example

```swift
import Foundation

func downloadVideo(from host: String, fileId: String, to outputURL: URL) async throws {
    // Connect to device
    let connection = NWConnection(
        host: NWEndpoint.Host(host),
        port: NWEndpoint.Port(rawValue: MultiCamConstants.tcpPort)!,
        using: .tcp
    )

    // Send GET_VIDEO command
    let cmd = CommandMessage.getVideo(fileId: fileId)
    let jsonData = try cmd.toJSON()

    // ... (receive header size, JSON header, binary data)
    // See PROTOCOL.md for complete binary protocol implementation
}
```

## API Reference

### Command Types

```swift
enum CommandType {
    case startRecording    // Start video recording
    case stopRecording     // Stop current recording
    case deviceStatus      // Query device status
    case getVideo          // Download video file
    case heartbeat         // Health check
    case listFiles         // List available files
}
```

### Device Statuses

```swift
enum DeviceStatus {
    case ready                          // Device idle and ready
    case recording                      // Currently recording
    case stopping                       // Recording stop in progress
    case error                          // Error state
    case scheduledRecordingAccepted    // Future recording scheduled
    case recordingStopped              // Recording completed
    case commandReceived               // Command acknowledged
    case timeNotSynchronized           // Device clock not synced
    case fileNotFound                  // Requested file doesn't exist
}
```

### Data Structures

#### CommandMessage

Request message sent to device.

**Properties:**
- `command: CommandType` - Command to execute
- `timestamp: TimeInterval` - Unix timestamp
- `deviceId: String` - Sender device ID
- `fileId: String?` - File ID (for GET_VIDEO)

**Methods:**
- `toJSON() -> Data` - Serialize to JSON data
- `toJSONString() -> String` - Serialize to JSON string
- `fromJSON(_ data: Data) -> CommandMessage` - Deserialize

#### StatusResponse

Response from device.

**Properties:**
- `deviceId: String` - Device ID
- `status: String` - Status value
- `timestamp: TimeInterval` - Response timestamp
- `isRecording: Bool` - Recording state
- `message: String?` - Status message
- `fileId: String?` - File ID (after stop)
- `fileSize: Int64?` - File size (bytes)

**Methods:**
- `fromJSON(_ data: Data) -> StatusResponse` - Deserialize
- `toJSON() -> Data` - Serialize

#### FileResponse

Header for binary file transfer.

**Properties:**
- `deviceId: String` - Device ID
- `fileId: String` - File ID
- `fileName: String` - Filename
- `fileSize: Int64` - File size (bytes)
- `status: String` - Status

#### FileMetadata

Metadata for a file.

**Properties:**
- `fileId: String` - File ID
- `fileName: String` - Filename
- `fileSize: Int64` - File size (bytes)
- `creationDate: TimeInterval` - Creation timestamp
- `modificationDate: TimeInterval` - Modification timestamp

#### ListFilesResponse

Response to LIST_FILES command.

**Properties:**
- `deviceId: String` - Device ID
- `status: String` - Status
- `timestamp: TimeInterval` - Response timestamp
- `files: [FileMetadata]` - File list

## Protocol Documentation

For detailed protocol documentation, see:
- [OpenAPI Specification](../specification/multicam-api.yaml)
- [Binary Protocol](../specification/PROTOCOL.md)
- [Implementation Differences](../specification/IMPLEMENTATION_DIFFERENCES.md)

## License

MIT License

## Related Projects

- [multiCam](../../multiCam) - iOS implementation (Swift)
- [multiCamAndroid](../../multiCamAndroid) - Android implementation (Java)
- [multiCamControllerPython](../../multiCamControllerPython) - Python controller (PySide6)
