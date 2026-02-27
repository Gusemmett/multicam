# MultiCam Controller - macOS Native

A native macOS SwiftUI application for controlling multiple iPhone cameras (via multiCam iOS app) and OAK cameras for synchronized recording.

## Features

- **mDNS Device Discovery**: Automatically discovers multiCam devices on the local network
- **Manual Device Connection**: Fallback for when automatic discovery fails
- **Synchronized Recording**: Start/stop recording on all devices with precise timing
- **File Management**: Download recorded files to local storage
- **S3 Integration**: Upload files to Amazon S3 (framework ready)
- **OAK Server Integration**: Manages Python OAK server as subprocess

## Requirements

- macOS 13.0 or later
- Xcode 15.0 or later
- Swift 5.9 or later

## Building the Project

1. Open `multiCamControllerMacos.xcodeproj` in Xcode
2. Select your development team in project settings
3. Build and run (⌘R)

## Network Permissions

The app requires network permissions for device discovery and communication. These are configured in the entitlements file:

- `com.apple.security.network.client` - For TCP communication with devices
- `com.apple.security.network.server` - For receiving device responses
- `com.apple.security.files.downloads.read-write` - For saving downloaded files

## Troubleshooting

### mDNS Discovery Error -72000

If you see the error "NSNetServicesErrorCode: -72000", this indicates a network permission issue:

**Solution 1: Check Entitlements**
- Ensure the app has proper network entitlements (already configured)
- Try building a fresh version of the app

**Solution 2: Use Manual Connection**
- Click the "+ Manual" button in the device list
- Enter the IP address and port of your iPhone running multiCam
- Default port is usually 8080

**Solution 3: Check Network Settings**
- Ensure your Mac and iPhone are on the same WiFi network
- Check for firewall settings blocking mDNS traffic
- Try disabling macOS firewall temporarily for testing

### Finding Device IP Address

On your iPhone running multiCam:
1. Open Settings → WiFi
2. Tap the ℹ️ next to your network name
3. Note the IP Address (e.g., 192.168.1.100)
4. Use this IP in the manual connection dialog

### OAK Server Issues

The app attempts to start the Python OAK server automatically. If this fails:
- Ensure Python 3 is installed on your system
- Check that the OAK-Controller-Rpi directory is present in the project
- View console logs for detailed error messages

## Project Structure

```
multiCamControllerMacos/
├── Models/                 # Data models
│   ├── MultiCamDevice.swift
│   ├── MultiCamCommand.swift
│   ├── RecordingSession.swift
│   └── AppState.swift
├── Services/               # Business logic
│   ├── DeviceDiscovery.swift
│   ├── DeviceCommunication.swift
│   ├── OAKServerManager.swift
│   └── S3Manager.swift
└── Views/                  # UI components
    ├── DeviceListView.swift
    ├── RecordingControlsView.swift
    └── ContentView.swift
```

## Protocol Compatibility

The app maintains full compatibility with the original Python implementation's network protocol:

- `START_RECORDING` - Begins recording with timestamp synchronization
- `STOP_RECORDING` - Stops recording and returns file ID
- `GET_VIDEO` - Downloads recorded file binary data
- `LIST_FILES` - Lists available recordings
- `DEVICE_STATUS` - Gets device status information

## Future Enhancements

- [ ] Add AWS SDK Swift for full S3 functionality
- [ ] Bundle OAK server Python dependencies
- [ ] Add app icon and branding
- [ ] Implement settings/preferences UI
- [ ] Add menu bar integration
- [ ] Support for additional video formats
- [ ] Automatic device reconnection

## Development Notes

- The app uses Swift Concurrency (async/await) for network operations
- SwiftUI is used throughout for the user interface
- Network operations are sandboxed but have appropriate entitlements
- The OAK server runs as a managed subprocess

## Support

For issues specific to the macOS port, check:
1. Console app for detailed logging
2. Network connectivity between devices
3. Firewall and security settings
4. Python environment for OAK server functionality