# MultiCam Common API

> Shared types, constants, and protocol documentation for the MultiCam synchronized recording API

This repository contains the common API language and documentation for MultiCam applications across multiple platforms (iOS, Android, Python). It provides a single source of truth for the protocol specification and platform-specific implementations of shared types.

## Overview

MultiCam is a synchronized multi-device camera recording system that enables precise coordination of video capture across multiple devices using:

- **TCP/IP Communication**: JSON messages over port 8080
- **mDNS Discovery**: Automatic device discovery via Bonjour/mDNS
- **NTP Time Synchronization**: Clock alignment for frame-accurate recording
- **Binary File Transfer**: Efficient video file downloads

## Repository Structure

```
multiCamCommon/
├── specification/           # Protocol documentation
│   ├── multicam-api.yaml   # OpenAPI 3.0 specification
│   ├── PROTOCOL.md         # Binary protocol details
│   └── IMPLEMENTATION_DIFFERENCES.md
├── python/                  # Python package
│   ├── multicam_common/    # Package source
│   ├── setup.py
│   └── README.md
├── swift/                   # Swift package
│   ├── Sources/MultiCamCommon/
│   ├── Package.swift
│   └── README.md
├── java/                    # Java/Android package
│   ├── src/main/java/com/multicam/common/
│   ├── build.gradle
│   └── README.md
├── CRITICAL_DIFFERENCES.md  # Action items for standardization
└── README.md               # This file
```

## Platform Implementations

### Python Package

```bash
cd python
pip install -e .
```

```python
from multicam_common import CommandMessage, StatusResponse, DeviceStatus

# Create a command
cmd = CommandMessage.start_recording()
print(cmd.to_json())

# Parse a response
response = StatusResponse.from_json(json_string)
if DeviceStatus.is_success(response.status):
    print("Success!")
```

[See Python README](python/README.md) for complete documentation.

### Swift Package

```swift
// Package.swift
dependencies: [
    .package(url: "https://github.com/yourusername/multiCamCommon.git", from: "1.0.0")
]
```

```swift
import MultiCamCommon

// Create a command
let cmd = CommandMessage.startRecording()
let jsonData = try cmd.toJSON()

// Parse a response
let response = try StatusResponse.fromJSON(data)
if response.deviceStatus?.isSuccess == true {
    print("Success!")
}
```

[See Swift README](swift/README.md) for complete documentation.

### Java Package

```gradle
dependencies {
    implementation 'com.multicam:multicam-common:1.0.0'
}
```

```java
import com.multicam.common.*;

// Create a command
CommandMessage cmd = CommandMessage.startRecording();
String json = cmd.toJson();

// Parse a response
StatusResponse response = StatusResponse.fromJson(jsonString);
if (response.getDeviceStatus().isSuccess()) {
    System.out.println("Success!");
}
```

[See Java README](java/README.md) for complete documentation.

## Quick Start

### 1. Discover Devices (mDNS)

All MultiCam devices advertise themselves via mDNS with service type `_multicam._tcp.local.`.

**Python:**
```python
from zeroconf import ServiceBrowser, Zeroconf

zeroconf = Zeroconf()
browser = ServiceBrowser(zeroconf, "_multicam._tcp.local.", handlers=[on_service_discovered])
```

**Swift:**
```swift
let browser = NWBrowser(for: .bonjourWithTXTRecord(type: "_multicam._tcp", domain: nil), using: .tcp)
```

**Java:**
```java
JmDNS jmdns = JmDNS.create();
jmdns.addServiceListener("_multicam._tcp.local.", listener);
```

### 2. Send a Command

**Python:**
```python
import socket
from multicam_common import CommandMessage, TCP_PORT

cmd = CommandMessage.start_recording()
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((device_ip, TCP_PORT))
sock.sendall(cmd.to_bytes())
```

**Swift:**
```swift
let cmd = CommandMessage.startRecording()
let connection = NWConnection(
    host: NWEndpoint.Host(deviceIP),
    port: NWEndpoint.Port(rawValue: MultiCamConstants.tcpPort)!,
    using: .tcp
)
connection.send(content: try cmd.toJSON(), completion: .contentProcessed { _ in })
```

**Java:**
```java
CommandMessage cmd = CommandMessage.startRecording();
Socket socket = new Socket(deviceIp, Constants.TCP_PORT);
socket.getOutputStream().write(cmd.toBytes());
```

### 3. Synchronized Multi-Device Recording

```python
import time
from multicam_common import CommandMessage

# Calculate future sync timestamp (3 seconds from now)
sync_time = time.time() + 3.0

# Send START_RECORDING to all devices with the same timestamp
for device in devices:
    cmd = CommandMessage.start_recording(timestamp=sync_time)
    send_command(device, cmd)

# All devices start recording at precisely sync_time

# Wait for recording duration
time.sleep(30)

# Stop all devices
for device in devices:
    cmd = CommandMessage.stop_recording()
    response = send_command(device, cmd)
    file_ids[device.name] = response.fileId
```

### 4. Cloud Upload (Recommended)

Instead of downloading videos to the controller, you can upload directly from devices to cloud storage:

**Python:**
```python
import boto3
from multicam_common import CommandMessage

# Generate presigned S3 URLs for each device
s3_client = boto3.client('s3')
for device in devices:
    file_id = file_ids[device.name]
    s3_key = f"recordings/{device.name}/{file_id}.mp4"

    # Generate presigned URL (valid for 1 hour)
    upload_url = s3_client.generate_presigned_url(
        'put_object',
        Params={'Bucket': 'my-bucket', 'Key': s3_key},
        ExpiresIn=3600
    )

    # Tell device to upload directly to S3
    cmd = CommandMessage.upload_to_cloud(file_id, upload_url)
    send_command(device, cmd)

# Monitor upload progress
import time
while True:
    all_done = True
    for device in devices:
        status_cmd = CommandMessage.upload_status()
        status = send_command(device, status_cmd)

        if status.currentUpload or status.uploadQueue:
            all_done = False
            if status.currentUpload:
                print(f"{device.name}: {status.currentUpload.uploadProgress:.1f}%")

    if all_done:
        break
    time.sleep(2)

print("All uploads complete!")
```

**Swift:**
```swift
// Upload to cloud
let uploadCmd = CommandMessage.uploadToCloud(
    fileId: fileId,
    uploadUrl: presignedS3Url
)
try await sendCommand(device, uploadCmd)

// Monitor progress
let statusCmd = CommandMessage.uploadStatus()
let status = try await sendCommand(device, statusCmd)
if let upload = status.currentUpload {
    print("Upload progress: \(upload.uploadProgress)%")
}
```

**Java:**
```java
// Upload to cloud
CommandMessage uploadCmd = CommandMessage.uploadToCloud(fileId, presignedS3Url);
sendCommand(device, uploadCmd);

// Monitor progress
CommandMessage statusCmd = CommandMessage.uploadStatus();
UploadTypes.UploadStatusResponse status =
    UploadTypes.UploadStatusResponse.fromJson(sendCommand(device, statusCmd));
if (status.currentUpload != null) {
    System.out.println("Progress: " + status.currentUpload.uploadProgress + "%");
}
```

**Benefits of Cloud Upload:**
- No controller bandwidth needed
- Devices auto-delete files after successful upload
- Can record and upload simultaneously
- Progress monitoring with upload queue

```

## API Commands

| Command | Description | Returns |
|---------|-------------|---------|
| `START_RECORDING` | Start recording (immediate or scheduled) | StatusResponse |
| `STOP_RECORDING` | Stop recording and get file ID | StatusResponse with fileId |
| `DEVICE_STATUS` | Query device status | StatusResponse |
| `GET_VIDEO` | Download video file | Binary file transfer |
| `HEARTBEAT` | Health check ping | StatusResponse |
| `LIST_FILES` | List available files | ListFilesResponse |
| `UPLOAD_TO_CLOUD` | Upload file to cloud (presigned S3 URL) | StatusResponse |
| `UPLOAD_STATUS` | Get upload progress and queue | UploadStatusResponse |

## Device Statuses

| Status | Meaning |
|--------|---------|
| `ready` | Device idle and ready |
| `recording` | Currently recording |
| `stopping` | Recording stop in progress |
| `scheduled_recording_accepted` | Future recording scheduled |
| `recording_stopped` | Recording completed |
| `uploading` | Currently uploading to cloud |
| `upload_queued` | Upload added to queue |
| `upload_completed` | Upload finished (file auto-deleted) |
| `upload_failed` | Upload failed |
| `time_not_synchronized` | Device clock not synced via NTP |
| `file_not_found` | Requested file doesn't exist |
| `error` | Error state (check message field) |

## Protocol Documentation

### Core Specifications

- **[OpenAPI Specification](specification/multicam-api.yaml)** - Complete API definition
- **[Protocol Documentation](specification/PROTOCOL.md)** - Binary protocol, message formats, synchronization
- **[Implementation Differences](specification/IMPLEMENTATION_DIFFERENCES.md)** - Platform variations and details
- **[Critical Differences](CRITICAL_DIFFERENCES.md)** - Action items for standardization

### Message Format

All commands are JSON over TCP:

```json
{
  "command": "START_RECORDING",
  "timestamp": 1729000000.123,
  "deviceId": "controller",
  "fileId": null
}
```

Response format:

```json
{
  "deviceId": "device-uuid",
  "status": "ready",
  "timestamp": 1729000000.456,
  "isRecording": false,
  "message": "Recording started",
  "fileId": null,
  "fileSize": null
}
```

### Binary File Transfer

For `GET_VIDEO` command:

```
[4 bytes: header size (big-endian)]
[JSON header: FileResponse]
[Binary file data]
```

See [PROTOCOL.md](specification/PROTOCOL.md) for complete details.

## Network Constants

| Constant | Value |
|----------|-------|
| TCP Port | 8080 |
| Service Type | `_multicam._tcp.local.` |
| NTP Server | `pool.ntp.org` |
| Max RTT | 500ms |
| Sync Delay | 3.0 seconds |
| Command Timeout | 60.0 seconds |

## Platform Support

| Platform | Status | Implementation | Package |
|----------|--------|----------------|---------|
| **iOS** | ✅ Production | Swift | [multiCam](../multiCam) |
| **Android** | ⚠️ Partial | Java | [multiCamAndroid](../multiCamAndroid) |
| **Python Controller** | ✅ Production | Python + PySide6 | [multiCamControllerPython](../multiCamControllerPython) |

## Known Issues & Standardization

See [CRITICAL_DIFFERENCES.md](CRITICAL_DIFFERENCES.md) for critical compatibility issues that need to be addressed:

### High Priority Issues

1. **LIST_FILES not implemented in Android** - Android missing 6th command
2. **Status value inconsistency** - iOS uses `"ready"`, Android uses `"Ready"`
3. **Missing message field in Android** - No human-readable error messages
4. **No FileMetadata in Android** - Cannot get file info without downloading
5. **File ID format differs** - iOS: `video_123.mov`, Android: `device_123.mp4`

Estimated effort to fix: **21-29 hours**

## Development

### Testing Protocol Compliance

Each platform implementation should:

1. Use standardized status values (lowercase snake_case)
2. Include all 6 commands (especially LIST_FILES)
3. Support FileMetadata structure
4. Use consistent file ID format: `{deviceId}_{timestamp}`
5. Include `message` field in all responses

### Adding a New Platform

To add support for a new platform:

1. Implement all message types from [specification/multicam-api.yaml](specification/multicam-api.yaml)
2. Follow the protocol defined in [specification/PROTOCOL.md](specification/PROTOCOL.md)
3. Use language-specific package from this repo as reference
4. Add integration tests with existing platforms

## Contributing

1. **Specification Changes**: Update [specification/multicam-api.yaml](specification/multicam-api.yaml) first
2. **Language Packages**: Keep Python, Swift, and Java implementations in sync
3. **Documentation**: Update relevant README files
4. **Testing**: Add tests for new features

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- **Major**: Breaking protocol changes
- **Minor**: New commands or fields (backward compatible)
- **Patch**: Bug fixes and documentation

Current version: **1.1.0**

### Changelog

**v1.1.0** - Cloud Upload Support
- Added `UPLOAD_TO_CLOUD` command for direct cloud uploads
- Added `UPLOAD_STATUS` command for monitoring uploads
- New device statuses: `uploading`, `upload_queued`, `upload_completed`, `upload_failed`
- Files automatically deleted after successful upload

**v1.0.0** - Initial Release
- Core recording commands
- mDNS discovery
- NTP time synchronization
- Binary file transfer

## License

MIT License

## Related Projects

- [multiCam](../multiCam) - iOS camera application (Swift)
- [multiCamAndroid](../multiCamAndroid) - Android camera application (Java)
- [multiCamControllerPython](../multiCamControllerPython) - Desktop controller (Python/PySide6)

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/multiCamCommon/issues)
- **Documentation**: See [specification/](specification/) directory
- **Examples**: Check individual package READMEs

---

**MultiCam** - Synchronized Multi-Device Recording
