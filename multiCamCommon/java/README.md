# MultiCam Common - Java Package

Java implementation of shared types and constants for the MultiCam synchronized recording API.

## Requirements

- Java 11+
- Gradle 7.0+ (or Maven)

## Installation

### Gradle

Add to your `build.gradle`:

```gradle
repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.multicam:multicam-common:1.0.0'
}
```

### Maven

Add to your `pom.xml`:

```xml
<dependency>
    <groupId>com.multicam</groupId>
    <artifactId>multicam-common</artifactId>
    <version>1.0.0</version>
</dependency>
```

### From Source

```bash
cd java
./gradlew build
./gradlew publishToMavenLocal
```

## Usage

### Importing

```java
import com.multicam.common.*;
import com.multicam.common.FileTypes.*;
```

### Creating Commands

```java
// Start recording immediately
CommandMessage cmd = CommandMessage.startRecording();
String json = cmd.toJson();
// {"command":"START_RECORDING","timestamp":1729000000.123,"deviceId":"controller","fileId":null}

// Start recording at a scheduled time (3 seconds from now)
double syncTime = System.currentTimeMillis() / 1000.0 + 3.0;
CommandMessage scheduledCmd = CommandMessage.startRecording(syncTime, "controller");

// Stop recording
CommandMessage stopCmd = CommandMessage.stopRecording();

// Query device status
CommandMessage statusCmd = CommandMessage.deviceStatus();

// Download a video file
CommandMessage getVideoCmd = CommandMessage.getVideo("device-id_1729000000123");

// List available files
CommandMessage listCmd = CommandMessage.listFiles();

// Heartbeat
CommandMessage heartbeatCmd = CommandMessage.heartbeat();
```

### Parsing Responses

```java
// Parse a status response
String jsonResponse = "{\"deviceId\":\"device-123\",\"status\":\"ready\"," +
                     "\"timestamp\":1729000000.456,\"isRecording\":false}";
StatusResponse response = StatusResponse.fromJson(jsonResponse);

System.out.println("Device: " + response.deviceId);
System.out.println("Status: " + response.status);
System.out.println("Recording: " + response.isRecording);

// Check if status is successful
DeviceStatus deviceStatus = response.getDeviceStatus();
if (deviceStatus != null && deviceStatus.isSuccess()) {
    System.out.println("Operation successful!");
}
```

### Working with Device Status

```java
// Use status enum
if (response.getDeviceStatus() == DeviceStatus.READY) {
    System.out.println("Device is ready");
}

// Check for errors
DeviceStatus status = response.getDeviceStatus();
if (status != null && status.isError()) {
    System.out.println("Error: " + response.message);
}

// All available statuses
for (DeviceStatus s : DeviceStatus.values()) {
    System.out.println(s.getValue());
}
```

### Constants

```java
// Network constants
int port = Constants.TCP_PORT;                      // 8080
String serviceType = Constants.SERVICE_TYPE;        // "_multicam._tcp.local."
String ntpServer = Constants.NTP_SERVER;            // "pool.ntp.org"

// Timing constants
double syncDelay = Constants.SYNC_DELAY;            // 3.0 seconds
double timeout = Constants.COMMAND_TIMEOUT;         // 60.0 seconds

// Transfer constants
int chunkSize = Constants.DOWNLOAD_CHUNK_SIZE;      // 8192 bytes

// Generate a file ID
String fileId = Constants.generateFileId("Android-ABC123");
// Result: "Android-ABC123_1729000000123"
```

### Complete Example: Send Command to Device

```java
import java.io.*;
import java.net.Socket;
import com.multicam.common.*;

public class MultiCamClient {
    public static StatusResponse sendCommand(String deviceIp, CommandMessage command)
            throws IOException {
        try (Socket socket = new Socket(deviceIp, Constants.TCP_PORT)) {
            socket.setSoTimeout((int) (Constants.COMMAND_TIMEOUT * 1000));

            // Send command
            OutputStream out = socket.getOutputStream();
            out.write(command.toBytes());
            out.flush();

            // Receive response
            InputStream in = socket.getInputStream();
            BufferedReader reader = new BufferedReader(
                new InputStreamReader(in, "UTF-8")
            );
            String responseLine = reader.readLine();

            return StatusResponse.fromJson(responseLine);
        }
    }

    public static void main(String[] args) {
        try {
            String deviceIp = "192.168.1.100";
            CommandMessage cmd = CommandMessage.startRecording();
            StatusResponse response = sendCommand(deviceIp, cmd);

            System.out.println("Status: " + response.status);
            System.out.println("Recording: " + response.isRecording);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}
```

### File Transfer Example

```java
import java.io.*;
import java.net.Socket;
import java.nio.ByteBuffer;
import com.multicam.common.*;
import com.multicam.common.FileTypes.*;

public class VideoDownloader {
    public static void downloadVideo(String deviceIp, String fileId, String outputPath)
            throws IOException {
        try (Socket socket = new Socket(deviceIp, Constants.TCP_PORT)) {
            // Send GET_VIDEO command
            CommandMessage cmd = CommandMessage.getVideo(fileId);
            OutputStream out = socket.getOutputStream();
            out.write(cmd.toBytes());
            out.flush();

            InputStream in = socket.getInputStream();
            DataInputStream dataIn = new DataInputStream(in);

            // Read header size (4 bytes, big-endian)
            int headerSize = dataIn.readInt();

            // Read JSON header
            byte[] headerBytes = new byte[headerSize];
            dataIn.readFully(headerBytes);
            String headerJson = new String(headerBytes, "UTF-8");
            FileResponse fileResponse = FileResponse.fromJson(headerJson);

            System.out.println("Downloading: " + fileResponse.fileName);
            System.out.println("Size: " + fileResponse.fileSize + " bytes");

            // Read binary file data
            try (FileOutputStream fileOut = new FileOutputStream(outputPath)) {
                long remaining = fileResponse.fileSize;
                byte[] buffer = new byte[Constants.DOWNLOAD_CHUNK_SIZE];

                while (remaining > 0) {
                    int toRead = (int) Math.min(buffer.length, remaining);
                    int bytesRead = dataIn.read(buffer, 0, toRead);
                    if (bytesRead == -1) {
                        throw new IOException("Connection closed prematurely");
                    }
                    fileOut.write(buffer, 0, bytesRead);
                    remaining -= bytesRead;
                }
            }

            System.out.println("Downloaded to: " + outputPath);
        }
    }

    public static void main(String[] args) {
        try {
            downloadVideo("192.168.1.100", "device-id_1729000000123", "video.mp4");
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}
```

## API Reference

### Command Types

```java
enum CommandType {
    START_RECORDING    // Start video recording
    STOP_RECORDING     // Stop current recording
    DEVICE_STATUS      // Query device status
    GET_VIDEO          // Download video file
    HEARTBEAT          // Health check
    LIST_FILES         // List available files
}
```

### Device Statuses

```java
enum DeviceStatus {
    READY                          // Device idle and ready
    RECORDING                      // Currently recording
    STOPPING                       // Recording stop in progress
    ERROR                          // Error state
    SCHEDULED_RECORDING_ACCEPTED   // Future recording scheduled
    RECORDING_STOPPED              // Recording completed
    COMMAND_RECEIVED               // Command acknowledged
    TIME_NOT_SYNCHRONIZED          // Device clock not synced
    FILE_NOT_FOUND                 // Requested file doesn't exist
}
```

### Data Classes

#### CommandMessage

Request message sent to device.

**Fields:**
- `CommandType command` - Command to execute
- `double timestamp` - Unix timestamp
- `String deviceId` - Sender device ID
- `String fileId` - File ID (for GET_VIDEO)

**Methods:**
- `String toJson()` - Serialize to JSON
- `byte[] toBytes()` - Serialize to UTF-8 bytes
- `CommandMessage fromJson(String)` - Deserialize

#### StatusResponse

Response from device.

**Fields:**
- `String deviceId` - Device ID
- `String status` - Status value
- `double timestamp` - Response timestamp
- `boolean isRecording` - Recording state
- `String message` - Status message
- `String fileId` - File ID (after stop)
- `Long fileSize` - File size (bytes)

**Methods:**
- `DeviceStatus getDeviceStatus()` - Get status enum
- `StatusResponse fromJson(String)` - Deserialize
- `String toJson()` - Serialize

#### FileTypes.FileResponse

Header for binary file transfer.

**Fields:**
- `String deviceId` - Device ID
- `String fileId` - File ID
- `String fileName` - Filename
- `long fileSize` - File size (bytes)
- `String status` - Status

#### FileTypes.FileMetadata

Metadata for a file.

**Fields:**
- `String fileId` - File ID
- `String fileName` - Filename
- `long fileSize` - File size (bytes)
- `double creationDate` - Creation timestamp
- `double modificationDate` - Modification timestamp

#### FileTypes.ListFilesResponse

Response to LIST_FILES command.

**Fields:**
- `String deviceId` - Device ID
- `String status` - Status
- `double timestamp` - Response timestamp
- `List<FileMetadata> files` - File list

## Building from Source

```bash
# Build library
./gradlew build

# Run tests
./gradlew test

# Publish to local Maven
./gradlew publishToMavenLocal
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
