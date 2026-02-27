# MultiCam Binary Protocol Specification

## Overview

The MultiCam protocol uses two distinct communication modes:

1. **JSON over TCP** - For commands and status messages
2. **Binary Protocol** - For file transfers

All communication occurs over TCP port 8080.

---

## 1. JSON Command Protocol

### Connection Flow

```
Controller                           Device
    |                                   |
    |-------- TCP Connect ------------->|
    |                                   |
    |-------- JSON Command ------------>|
    |                                   |
    |<------- JSON Response ------------|
    |                                   |
    |-------- TCP Close --------------->|
```

### Message Format

All commands and responses are sent as UTF-8 encoded JSON strings over raw TCP sockets.

#### Command Message Structure

```json
{
  "command": "COMMAND_NAME",
  "timestamp": 1729000000.123456,
  "deviceId": "controller",
  "fileName": "optional-file-name.mp4"
}
```

**Fields:**
- `command` (string, required): One of the command types (see Commands section)
- `timestamp` (float, required): Unix timestamp in seconds with fractional seconds
- `deviceId` (string, optional): Identifier of the sending device (default: "controller")
- `fileName` (string, optional): Required for GET_VIDEO and UPLOAD_TO_CLOUD commands

#### Response Message Structure

```json
{
  "deviceId": "device-unique-id",
  "status": "ready",
  "timestamp": 1729000000.456789,
  "batteryLevel": 85.5,
  "uploadQueue": [],
  "failedUploadQueue": []
}
```

**Fields:**
- `deviceId` (string, required): Unique device identifier
- `status` (string, required): Device status (see Status Values section)
- `timestamp` (float, required): Unix timestamp of response
- `batteryLevel` (float, optional): Battery percentage (0.0-100.0), null if unavailable
- `uploadQueue` (array, required): Upload queue (includes in-progress and queued uploads)
- `failedUploadQueue` (array, required): Failed upload queue

---

## 2. Binary File Transfer Protocol

Used exclusively for the `GET_VIDEO` command to transfer video files.

### Transfer Flow

```
Controller                                Device
    |                                        |
    |-------- GET_VIDEO Command ----------->|
    |                                        |
    |<------- [Header Size: 4 bytes] -------|
    |<------- [JSON Header: N bytes] -------|
    |<------- [Binary Data: M bytes] -------|
    |                                        |
    |-------- TCP Close -------------------->|
```

### Binary Protocol Structure

The file transfer consists of three parts sent sequentially:

#### Part 1: Header Size (4 bytes)

```
Bytes: [0x00 0x00 0x00 0xXX]
Format: Big-endian unsigned 32-bit integer
Value: Size of the JSON header (Part 2) in bytes
```

**Example:**
```
Header size = 150 bytes
Binary: 0x00 0x00 0x00 0x96
```

#### Part 2: JSON Header

A JSON object containing file metadata:

```json
{
  "deviceId": "device-unique-id",
  "fileName": "video_1729000000.mp4",
  "fileSize": 52428800,
  "status": "ready"
}
```

**Fields:**
- `deviceId` (string): Device that owns the file
- `fileName` (string): Filename
- `fileSize` (int64): Total file size in bytes
- `status` (string): Status (typically "ready")

#### Part 3: Binary File Data

Raw binary data of the video file. Length is specified in the JSON header's `fileSize` field.

### Reading Algorithm

Client implementation should follow this sequence:

```python
# 1. Read header size (4 bytes)
header_size_bytes = socket.recv(4)
header_size = int.from_bytes(header_size_bytes, byteorder='big')

# 2. Read JSON header
header_json_bytes = socket.recv(header_size)
header = json.loads(header_json_bytes.decode('utf-8'))

# 3. Read binary file data
file_size = header['fileSize']
file_data = b''
while len(file_data) < file_size:
    chunk = socket.recv(min(8192, file_size - len(file_data)))
    if not chunk:
        raise ConnectionError("Connection closed prematurely")
    file_data += chunk

# 4. Write to disk
with open(f"{header['fileName']}", 'wb') as f:
    f.write(file_data)
```

---

## 3. Commands

### START_RECORDING

Start video recording on the device.

**Behavior:**
- If `timestamp` is in the past or current time: Start recording immediately
- If `timestamp` is in the future: Schedule synchronized recording to start at that time

**Request:**
```json
{
  "command": "START_RECORDING",
  "timestamp": 1729000003.500,
  "deviceId": "controller"
}
```

**Response (Scheduled):**
```json
{
  "deviceId": "device-id",
  "status": "scheduled_recording_accepted",
  "timestamp": 1729000000.123,
  "batteryLevel": 85.5,
  "uploadQueue": [],
  "failedUploadQueue": []
}
```

**Response (Immediate):**
```json
{
  "deviceId": "device-id",
  "status": "recording",
  "timestamp": 1729000000.123,
  "batteryLevel": 85.5,
  "uploadQueue": [],
  "failedUploadQueue": []
}
```

**Error Response (Time Not Synced):**
```json
{
  "deviceId": "device-id",
  "status": "time_not_synchronized",
  "timestamp": 1729000000.123,
  "message": "Cannot start scheduled recording - time not synchronized"
}
```

---

### STOP_RECORDING

Stop current recording and return the file identifier.

**Request:**
```json
{
  "command": "STOP_RECORDING",
  "timestamp": 1729000030.123,
  "deviceId": "controller"
}
```

**Response:**
```json
{
  "deviceId": "device-id",
  "status": "recording_stopped",
  "timestamp": 1729000030.456,
  "fileName": "video_1729000000.mp4",
  "fileSize": 52428800
}
```

---

### DEVICE_STATUS

Query current device status.

**Request:**
```json
{
  "command": "DEVICE_STATUS",
  "timestamp": 1729000000.123,
  "deviceId": "controller"
}
```

**Response:**
```json
{
  "deviceId": "device-id",
  "status": "ready",
  "timestamp": 1729000000.456,
  "batteryLevel": 85.5,
  "uploadQueue": [
    {
      "fileName": "video_1729000000.mp4",
      "fileSize": 52428800,
      "bytesUploaded": 10485760,
      "uploadProgress": 20.0,
      "uploadSpeed": 2621440,
      "status": "uploading",
      "uploadUrl": "https://...",
      "error": null
    }
  ],
  "failedUploadQueue": []
}
```

---

### GET_VIDEO

Download video file using binary protocol.

**Request:**
```json
{
  "command": "GET_VIDEO",
  "timestamp": 1729000000.123,
  "deviceId": "controller",
  "fileName": "video_1729000000.mp4"
}
```

**Response:** Binary protocol (see Binary File Transfer Protocol section)

**Error Response (File Not Found):**
```json
{
  "deviceId": "device-id",
  "status": "file_not_found",
  "timestamp": 1729000000.123,
  "message": "File video_1729000000.mp4 not found"
}
```

---

### LIST_FILES

List all available video files on the device.

**Implementation Status:** ⚠️ Available in iOS, may not be implemented on all platforms

**Request:**
```json
{
  "command": "LIST_FILES",
  "timestamp": 1729000000.123,
  "deviceId": "controller"
}
```

**Response:**
```json
{
  "deviceId": "device-id",
  "status": "ready",
  "timestamp": 1729000000.456,
  "files": [
    {
      "fileName": "video_1729000000.mp4",
      "fileSize": 52428800,
      "creationDate": 1729000000.123,
      "modificationDate": 1729000030.456
    },
    {
      "fileName": "video_1729000100.mp4",
      "fileSize": 41943040,
      "creationDate": 1729000100.456,
      "modificationDate": 1729000125.789
    }
  ]
}
```

---

### HEARTBEAT

Health check ping to verify device connectivity.

**Request:**
```json
{
  "command": "HEARTBEAT",
  "timestamp": 1729000000.123,
  "deviceId": "controller"
}
```

**Response:**
```json
{
  "deviceId": "device-id",
  "status": "ready",
  "timestamp": 1729000000.456,
  "batteryLevel": 85.5,
  "uploadQueue": [],
  "failedUploadQueue": []
}
```

---

### UPLOAD_TO_CLOUD

Upload video file to cloud storage using either a presigned S3 URL or AWS IAM credentials.

**Behavior:**
- File is added to device upload queue
- Upload happens asynchronously (device continues accepting other commands)
- Device can record and upload simultaneously
- File is automatically deleted from device after successful upload
- Returns immediately with queue status

**Authentication Methods:**

The command supports two authentication methods:

1. **Presigned S3 URL** (original method)
   - Controller generates time-limited presigned URL
   - Device uses standard HTTP PUT request
   - No AWS SDK required on device
   - URL expires after configured time (typically 1 hour)

2. **IAM Credentials** (new method)
   - Controller provides temporary AWS credentials via STS AssumeRole
   - Device uses AWS SDK for upload with retry and progress tracking
   - Supports larger files and multipart uploads
   - Credentials can be scoped with IAM policies

**Request (Presigned URL):**
```json
{
  "command": "UPLOAD_TO_CLOUD",
  "timestamp": 1729000000.123,
  "deviceId": "controller",
  "fileName": "video_1729000000.mp4",
  "uploadUrl": "https://bucket.s3.amazonaws.com/path/video.mp4?AWSAccessKeyId=...&Signature=..."
}
```

**Request (IAM Credentials):**
```json
{
  "command": "UPLOAD_TO_CLOUD",
  "timestamp": 1729000000.123,
  "deviceId": "controller",
  "fileName": "video_1729000000.mp4",
  "s3Bucket": "my-bucket",
  "s3Key": "2025-01-15/session_123/video_1729000000.mp4",
  "awsAccessKeyId": "ASIAXXXXXXXXXXX",
  "awsSecretAccessKey": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "awsSessionToken": "FwoGZXIvYXdzEBYaD...",
  "awsRegion": "us-east-1"
}
```

**Fields:**
- `fileName` (string, required): File name to upload

**Fields for Presigned URL Authentication:**
- `uploadUrl` (string, required for presigned URL method): Presigned S3 URL with full signature

**Fields for IAM Credentials Authentication:**
- `s3Bucket` (string, required for IAM method): S3 bucket name
- `s3Key` (string, required for IAM method): S3 object key (path within bucket)
- `awsAccessKeyId` (string, required for IAM method): AWS access key ID from STS
- `awsSecretAccessKey` (string, required for IAM method): AWS secret access key from STS
- `awsSessionToken` (string, required for IAM method): AWS session token from STS
- `awsRegion` (string, required for IAM method): AWS region (e.g., "us-east-1")

**Note:** The device detects the authentication method based on which fields are present. If `uploadUrl` is provided, presigned URL method is used. If IAM credential fields are provided, IAM method is used.

**Response (Success):**
```json
{
  "deviceId": "device-id",
  "status": "upload_queued",
  "timestamp": 1729000000.456,
  "fileName": "video_1729000000.mp4",
  "fileSize": 52428800
}
```

**Error Response (File Not Found):**
```json
{
  "deviceId": "device-id",
  "status": "file_not_found",
  "timestamp": 1729000000.123,
  "message": "File video_1729000000.mp4 not found"
}
```

---

## 4. Status Values

| Status | Description |
|--------|-------------|
| `ready` | Device is idle and ready for commands |
| `recording` | Currently recording video |
| `stopping` | Recording stop in progress |
| `error` | Error state (check message field) |
| `scheduled_recording_accepted` | Future recording scheduled |
| `recording_stopped` | Recording completed successfully |
| `command_received` | Command acknowledged |
| `time_not_synchronized` | Device clock not synchronized via NTP |
| `file_not_found` | Requested file does not exist |
| `uploading` | Currently uploading file to cloud |
| `upload_queued` | Upload added to queue |
| `upload_completed` | Upload completed successfully (file auto-deleted) |
| `upload_failed` | Upload failed (check message field) |

---

## 5. Time Synchronization

MultiCam uses NTP (Network Time Protocol) for precise time synchronization across devices.

### NTP Configuration

- **NTP Server:** `pool.ntp.org`
- **NTP Port:** 123 (UDP)
- **Protocol:** NTP v3/v4
- **Sync Method:** Multiple samples, best 3 averaged
- **Max Acceptable RTT:** 500ms

### Synchronization Process

1. Device queries NTP server multiple times (typically 3-4 attempts)
2. Measures round-trip time (RTT) for each query
3. Calculates time offset: `offset = NTP_time - receive_time + (RTT / 2)`
4. Discards results with RTT > 500ms
5. Averages best 3 results
6. Stores offset for synchronized timestamps

### Time-Sensitive Operations

When `START_RECORDING` is sent with a future timestamp:

1. Device checks if time is synchronized (`isSynchronized == true`)
2. If not synchronized, returns `time_not_synchronized` error
3. If synchronized, schedules recording to start at the specified timestamp
4. Recording begins precisely at scheduled time using: `current_time + time_offset`

**Typical Sync Accuracy:** ±50ms

---

## 6. Device Discovery (mDNS)

Devices advertise themselves using mDNS/Bonjour service discovery.

### Service Configuration

- **Service Type:** `_multicam._tcp.local.`
- **Port:** 8080
- **Service Name Format:** `multiCam-{deviceId}`

**Example Service Name:**
```
multiCam-Mountain-A1B2C3D4._multicam._tcp.local.
```

### Discovery Process

Controllers use mDNS to discover available devices:

```python
import zeroconf

# Browse for MultiCam services
browser = zeroconf.ServiceBrowser(
    zeroconf.Zeroconf(),
    "_multicam._tcp.local.",
    handlers=[on_service_discovered]
)

# Discovered service info includes:
# - name: "multiCam-Mountain-A1B2C3D4._multicam._tcp.local."
# - ip: "192.168.1.100"
# - port: 8080
```

---

## 7. Error Handling

### Network Errors

- **Connection Timeout:** Device may be offline or unreachable
- **Read Timeout:** Device not responding (command timeout: 60 seconds)
- **Connection Reset:** Device disconnected during operation

### Command Errors

- **time_not_synchronized:** Device cannot start scheduled recording without NTP sync
- **file_not_found:** Requested file does not exist on device
- **upload_failed:** Upload to cloud failed (network error, invalid URL, etc.)
- **error:** Generic error (check `message` field for details)

### Retry Strategy

Recommended retry approach for network operations:

1. **Max Retries:** 3 attempts
2. **Backoff:** Exponential (1s, 2s, 4s)
3. **Timeout:** 60 seconds per attempt
4. **Retryable Errors:** Network timeouts, connection resets
5. **Non-Retryable Errors:** `file_not_found`, `time_not_synchronized`
6. **Upload Retries:** Device handles upload retries internally; use `UPLOAD_STATUS` to monitor

---

## 8. Multi-Device Synchronization

For synchronized multi-camera recording:

### Workflow

```python
import time

# 1. Calculate future sync timestamp
sync_delay = 3.0  # seconds in the future
sync_timestamp = time.time() + sync_delay

# 2. Send START_RECORDING to all devices with same timestamp
for device in devices:
    send_command(device, {
        "command": "START_RECORDING",
        "timestamp": sync_timestamp,
        "deviceId": "controller"
    })

# 3. All devices start recording at precisely sync_timestamp
# (assuming all devices are NTP synchronized)

# 4. Wait for recording duration
time.sleep(recording_duration)

# 5. Send STOP_RECORDING to all devices
for device in devices:
    response = send_command(device, {
        "command": "STOP_RECORDING",
        "timestamp": time.time(),
        "deviceId": "controller"
    })
    file_names[device.name] = response["fileName"]

# 6a. Option 1: Download files from all devices
for device, file_name in file_names.items():
    send_command(device, {
        "command": "GET_VIDEO",
        "timestamp": time.time(),
        "deviceId": "controller",
        "fileName": file_name
    })

# 6b. Option 2: Upload files directly to cloud (recommended)
for device, file_name in file_names.items():
    # Generate presigned S3 URL for this device/file
    upload_url = generate_presigned_url(bucket, f"recordings/{device.name}/{file_name}")

    send_command(device, {
        "command": "UPLOAD_TO_CLOUD",
        "timestamp": time.time(),
        "deviceId": "controller",
        "fileName": file_name,
        "uploadUrl": upload_url
    })

# 7. Monitor upload progress (if using cloud upload)
while True:
    all_done = True
    for device in devices:
        status = send_command(device, {
            "command": "DEVICE_STATUS",
            "timestamp": time.time(),
            "deviceId": "controller"
        })

        if status["uploadQueue"] or status["failedUploadQueue"]:
            all_done = False
            # Get first item in queue (currently uploading)
            if status["uploadQueue"]:
                current = status["uploadQueue"][0]
                print(f"{device.name}: {current['uploadProgress']}%")

    if all_done:
        break
    time.sleep(2)
```

### Synchronization Accuracy

- **Typical Accuracy:** 50-100ms across devices
- **Factors:**
  - NTP sync quality
  - Network latency variance
  - Device processing time

---

## 9. Implementation Notes

### Socket Handling

- **Connection Model:** One connection per command (stateless)
- **Keep-Alive:** Not used - connections are short-lived
- **Buffer Size:** 8192 bytes recommended for file transfers

### JSON Encoding

- **Encoding:** UTF-8
- **Whitespace:** Not significant (compact or pretty both acceptable)
- **Null Values:** Optional fields should be `null` (not omitted)

### File Naming

Video files follow a timestamp-based naming pattern:
```
video_{unixTimeSeconds}.mp4
```

Examples:
- `video_1729000000.mp4`
- `video_1729000100.mp4`

This format ensures:
- Chronological ordering
- Simple and consistent naming
- Human readability

---

## 10. Platform-Specific Notes

### iOS (Swift)

- Fully implements all commands including `LIST_FILES`
- Uses AVFoundation for video capture
- FileResponse includes full FileMetadata structure

### Android (Java)

- Implements 5 core commands (may not support `LIST_FILES`)
- Uses CameraX framework for video capture
- May include video trimming/post-processing

### Python Controller

- Reference implementation for controller logic
- Uses asyncio for concurrent device operations
- Includes S3 upload capabilities

**See IMPLEMENTATION_DIFFERENCES.md for detailed platform variations.**
