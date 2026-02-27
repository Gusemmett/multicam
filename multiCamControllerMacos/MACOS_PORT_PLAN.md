# MultiCam Controller - macOS Native Port Plan

## Overview
Port the existing Python/Gradio MultiCam Controller to a native macOS SwiftUI application while preserving all core functionality and keeping the OAK server component as a bundled Python subprocess.

## Current Architecture Analysis

### Existing Components
- **Main App**: Gradio web interface (`src/multicam_app.py`) - localhost:7860
- **Camera Controller**: Network discovery & communication (`src/multicam_controller.py`)
- **S3 Controller**: AWS upload functionality (`src/s3_controller.py`)
- **OAK Server**: Embedded Python server (`OAK-Controller-Rpi/` submodule)

### Key Technologies Used
- **Python**: Gradio, asyncio, threading, zeroconf
- **Network**: mDNS discovery via `_multicam._tcp.local.`
- **Protocol**: TCP JSON commands (START_RECORDING, STOP_RECORDING, etc.)
- **Storage**: Local downloads + S3 upload with boto3
- **Packaging**: PyInstaller → macOS app bundle

## Target Architecture

### SwiftUI Native App
- **Frontend**: SwiftUI for native macOS interface
- **Backend**: Swift networking and file management
- **OAK Integration**: Bundle and launch Python OAK server as subprocess

### Technology Stack
- **UI Framework**: SwiftUI
- **Network Discovery**: `NetService`/`NetServiceBrowser` (Foundation)
- **AWS Integration**: `aws-sdk-swift`
- **JSON Handling**: `Codable`
- **Async Operations**: Swift Concurrency (async/await)

## Implementation Plan

### Phase 1: Project Setup & OAK Integration
1. **Create Xcode Project**
   - macOS SwiftUI app
   - Bundle identifier: `com.multicam.controller`
   - Minimum deployment: macOS 13.0+

2. **Bundle OAK Server**
   - pull in git repo for oak server: https://github.com/Gusemmett/OAK-Controller-Rpi.git
   - Include Python runtime and dependencies
   - Create launch scripts for OAK server subprocess

3. **Process Management**
   - `Process` class to launch OAK Python server
   - Handle cleanup on app termination
   - Monitor server health/restart capability

### Phase 2: Network Discovery & Communication
1. **mDNS Service Discovery**
   - Replace `zeroconf` with `NetServiceBrowser`
   - Search for `_multicam._tcp.local.` services
   - Parse service info (IP, port, device name)

2. **TCP Communication Layer**
   - Swift socket communication
   - JSON command serialization (`Codable`)
   - Implement existing protocol:
     - `START_RECORDING` (with timestamp sync)
     - `STOP_RECORDING` (returns fileId)
     - `GET_VIDEO` (binary file download)
     - `LIST_FILES`
     - `DEVICE_STATUS`

3. **Device Management**
   - Device discovery state management
   - Connection status tracking
   - Error handling and reconnection logic

### Phase 3: Core Recording Functionality
1. **Recording Controls**
   - Start/stop synchronized recording
   - 3-second delay countdown
   - Multi-device command broadcasting

2. **File Management**
   - Download files from devices
   - Local storage in `~/Downloads/multiCam/`
   - Progress tracking for downloads

3. **Session Management**
   - Recording state tracking
   - File ID collection and management
   - Status updates and error handling

### Phase 4: AWS S3 Integration
1. **AWS SDK Setup**
   - Integrate `aws-sdk-swift`
   - Configure S3 client with credentials
   - Handle authentication (IAM roles, profiles)

2. **Upload Functionality**
   - Replace boto3 upload logic
   - Progress tracking for uploads
   - Session folder organization
   - Cleanup after successful uploads

3. **Error Handling**
   - Upload retry logic
   - Partial upload recovery
   - User feedback for failures

### Phase 5: User Interface
1. **Main Window Layout**
   - Device discovery section
   - Recording controls
   - Status display
   - Progress indicators

2. **Device List Display**
   - Live device list updates
   - Device status indicators (📷 icons)
   - Connection status

3. **Recording Interface**
   - Start/Stop recording buttons
   - Countdown timer display
   - Status messages and alerts

4. **Upload Progress**
   - Progress bars for uploads
   - File-by-file progress details
   - Completion notifications

### Phase 6: Advanced Features
1. **Settings/Preferences**
   - S3 configuration
   - Default directories
   - Network timeout settings

2. **Menu Bar Integration**
   - Status in menu bar
   - Quick actions
   - Background operation capability

3. **Error Recovery**
   - Automatic device rediscovery
   - OAK server restart functionality
   - Network reconnection handling

## Key Implementation Details

### OAK Server Integration
```swift
class OAKServerManager: ObservableObject {
    private var oakProcess: Process?

    func startOAKServer() async throws {
        let bundlePath = Bundle.main.bundlePath
        let oakPath = "\(bundlePath)/Contents/Resources/OAK-Controller-Rpi"
        // Launch Python subprocess
    }
}
```

### mDNS Discovery
```swift
class DeviceDiscovery: NSObject, ObservableObject, NetServiceBrowserDelegate {
    private let browser = NetServiceBrowser()
    @Published var discoveredDevices: [MultiCamDevice] = []

    func startDiscovery() {
        browser.searchForServices(ofType: "_multicam._tcp.", inDomain: "")
    }
}
```

### Command Protocol
```swift
struct MultiCamCommand: Codable {
    let command: String
    let timestamp: TimeInterval
    let deviceId: String
    let fileId: String?
}
```

## File Structure
```
MultiCamController/
├── MultiCamController/
│   ├── App/
│   │   ├── MultiCamControllerApp.swift
│   │   └── ContentView.swift
│   ├── Models/
│   │   ├── MultiCamDevice.swift
│   │   ├── RecordingSession.swift
│   │   └── AppState.swift
│   ├── Services/
│   │   ├── DeviceDiscovery.swift
│   │   ├── DeviceCommunication.swift
│   │   ├── OAKServerManager.swift
│   │   └── S3Manager.swift
│   ├── Views/
│   │   ├── DeviceListView.swift
│   │   ├── RecordingControlsView.swift
│   │   └── ProgressView.swift
│   └── Resources/
│       └── OAK-Controller-Rpi/
└── MultiCamController.xcodeproj
```

## Testing Strategy
1. **Unit Tests**: Individual service components
2. **Integration Tests**: Device communication protocols
3. **Manual Testing**: Multi-device recording scenarios
4. **Performance**: Large file download/upload handling

## Migration Benefits
- **Native Performance**: Faster UI, better system integration
- **Better UX**: Native macOS look and feel
- **System Integration**: Menu bar, notifications, file system
- **Maintenance**: Single codebase, no Python packaging complexity
- **Distribution**: Mac App Store compatibility

## Risks & Considerations
- **OAK Dependencies**: Python subprocess adds complexity
- **Protocol Compatibility**: Must maintain compatibility with iOS multiCam apps
- **AWS Credentials**: Secure handling in native app
- **Testing Complexity**: Multi-device scenarios harder to test

## Success Criteria
- [ ] OAK server launches and advertises via mDNS
- [ ] iPhone multiCam devices discovered successfully
- [ ] Synchronized recording works across all devices
- [ ] File downloads complete without corruption
- [ ] S3 uploads match current functionality
- [ ] UI responsive during all operations
- [ ] App bundle under 100MB
- [ ] Memory usage under 200MB during normal operation
