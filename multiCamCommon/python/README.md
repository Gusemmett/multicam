# MultiCam Common - Python Package

Python implementation of shared types and constants for the MultiCam synchronized recording API.

## Installation

### From PyPI (when published)

```bash
pip install multicam-common
```

### From Source

```bash
cd python
pip install -e .
```

## Usage

### Importing

```python
from multicam_common import (
    CommandType,
    CommandMessage,
    StatusResponse,
    DeviceStatus,
    TCP_PORT,
    SERVICE_TYPE,
)
```

### Creating Commands

```python
import time

# Start recording immediately
cmd = CommandMessage.start_recording()
print(cmd.to_json())
# {"command": "START_RECORDING", "timestamp": 1729000000.123, "deviceId": "controller", "fileId": null}

# Start recording at a scheduled time (3 seconds from now)
sync_time = time.time() + 3.0
cmd = CommandMessage.start_recording(timestamp=sync_time)

# Stop recording
cmd = CommandMessage.stop_recording()

# Query device status
cmd = CommandMessage.device_status()

# Download a video file
cmd = CommandMessage.get_video(file_id="device-id_1729000000123")

# List available files
cmd = CommandMessage.list_files()

# Heartbeat
cmd = CommandMessage.heartbeat()
```

### Parsing Responses

```python
# Parse a status response
json_response = '{"deviceId": "device-123", "status": "ready", "timestamp": 1729000000.456, "isRecording": false}'
response = StatusResponse.from_json(json_response)

print(f"Device: {response.deviceId}")
print(f"Status: {response.status}")
print(f"Recording: {response.isRecording}")

# Check if status is successful
if DeviceStatus.is_success(response.status):
    print("Operation successful!")
```

### Working with Device Status

```python
from multicam_common import DeviceStatus

# Use status enum
if response.status == DeviceStatus.READY.value:
    print("Device is ready")

# Check for errors
if DeviceStatus.is_error(response.status):
    print(f"Error: {response.message}")

# All available statuses
print(list(DeviceStatus))
# [DeviceStatus.READY, DeviceStatus.RECORDING, DeviceStatus.STOPPING, ...]
```

### Constants

```python
from multicam_common import (
    TCP_PORT,              # 8080
    SERVICE_TYPE,          # "_multicam._tcp.local."
    NTP_SERVER,            # "pool.ntp.org"
    SYNC_DELAY,            # 3.0 seconds
    COMMAND_TIMEOUT,       # 60.0 seconds
    DOWNLOAD_CHUNK_SIZE,   # 8192 bytes
)

# Use in your networking code
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((device_ip, TCP_PORT))
sock.sendall(cmd.to_bytes())
```

### Complete Example: Send Command to Device

```python
import socket
import time
from multicam_common import CommandMessage, StatusResponse, TCP_PORT

def send_command(device_ip: str, command: CommandMessage) -> StatusResponse:
    """Send a command to a MultiCam device and get the response."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(60.0)
        sock.connect((device_ip, TCP_PORT))

        # Send command
        sock.sendall(command.to_bytes())

        # Receive response
        response_data = sock.recv(4096)
        response_str = response_data.decode('utf-8')

        return StatusResponse.from_json(response_str)

# Use it
device_ip = "192.168.1.100"
cmd = CommandMessage.start_recording()
response = send_command(device_ip, cmd)

print(f"Status: {response.status}")
print(f"Recording: {response.isRecording}")
```

### File Transfer Example

```python
import struct
from multicam_common import CommandMessage, FileResponse

def download_video(device_ip: str, file_id: str, output_path: str):
    """Download a video file from a MultiCam device."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((device_ip, TCP_PORT))

        # Send GET_VIDEO command
        cmd = CommandMessage.get_video(file_id)
        sock.sendall(cmd.to_bytes())

        # Read header size (4 bytes, big-endian)
        header_size_bytes = sock.recv(4)
        header_size = struct.unpack('>I', header_size_bytes)[0]

        # Read JSON header
        header_json = sock.recv(header_size).decode('utf-8')
        file_response = FileResponse.from_json(header_json)

        print(f"Downloading: {file_response.fileName}")
        print(f"Size: {file_response.fileSize} bytes")

        # Read binary file data
        with open(output_path, 'wb') as f:
            remaining = file_response.fileSize
            while remaining > 0:
                chunk = sock.recv(min(8192, remaining))
                if not chunk:
                    raise ConnectionError("Connection closed prematurely")
                f.write(chunk)
                remaining -= len(chunk)

        print(f"Downloaded to: {output_path}")

# Use it
download_video("192.168.1.100", "device-id_1729000000123", "video.mp4")
```

## API Reference

### Command Types

- `START_RECORDING` - Start video recording (immediate or scheduled)
- `STOP_RECORDING` - Stop current recording
- `DEVICE_STATUS` - Query device status
- `GET_VIDEO` - Download video file
- `HEARTBEAT` - Health check
- `LIST_FILES` - List available files (may not be supported on all platforms)

### Device Statuses

- `ready` - Device idle and ready
- `recording` - Currently recording
- `stopping` - Recording stop in progress
- `error` - Error state
- `scheduled_recording_accepted` - Future recording scheduled
- `recording_stopped` - Recording completed
- `command_received` - Command acknowledged
- `time_not_synchronized` - Device clock not synced
- `file_not_found` - Requested file doesn't exist

### Data Classes

#### CommandMessage

Request message sent to device.

**Fields:**
- `command: CommandType` - Command to execute
- `timestamp: float` - Unix timestamp
- `deviceId: str` - Sender device ID
- `fileId: Optional[str]` - File ID (for GET_VIDEO)

**Methods:**
- `to_json() -> str` - Serialize to JSON
- `to_bytes() -> bytes` - Serialize to UTF-8 bytes
- `from_json(json_str) -> CommandMessage` - Deserialize

#### StatusResponse

Response from device.

**Fields:**
- `deviceId: str` - Device ID
- `status: str` - Status value
- `timestamp: float` - Response timestamp
- `isRecording: bool` - Recording state
- `message: Optional[str]` - Status message
- `fileId: Optional[str]` - File ID (after stop)
- `fileSize: Optional[int]` - File size (bytes)

**Methods:**
- `from_json(json_str) -> StatusResponse` - Deserialize
- `to_json() -> str` - Serialize

#### FileResponse

Header for binary file transfer.

**Fields:**
- `deviceId: str` - Device ID
- `fileId: str` - File ID
- `fileName: str` - Filename
- `fileSize: int` - File size (bytes)
- `status: str` - Status

#### FileMetadata

Metadata for a file.

**Fields:**
- `fileId: str` - File ID
- `fileName: str` - Filename
- `fileSize: int` - File size (bytes)
- `creationDate: float` - Creation timestamp
- `modificationDate: float` - Modification timestamp

#### ListFilesResponse

Response to LIST_FILES command.

**Fields:**
- `deviceId: str` - Device ID
- `status: str` - Status
- `timestamp: float` - Response timestamp
- `files: List[FileMetadata]` - File list

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest
```

### Type Checking

```bash
mypy multicam_common
```

### Code Formatting

```bash
black multicam_common
```

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
