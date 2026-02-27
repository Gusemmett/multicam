# MultiCam Relay - Handoff Document

## Overview

A lightweight native relay binary that bridges browser WebSocket connections to device TCP connections, enabling a web-based MultiCam controller. The browser cannot directly perform mDNS discovery or open TCP sockets, so this relay handles those operations locally.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Browser App                             │
│  ws://localhost:9847/ws                                      │
└─────────────────────┬───────────────────────────────────────┘
                      │ WebSocket (JSON)
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                  multicam-relay                              │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ WebSocket   │  │   mDNS      │  │  TCP Connection     │  │
│  │ Server      │  │   Discovery │  │  Manager            │  │
│  │ :9847       │  │             │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                          │                                   │
│                    ┌─────▼─────┐                             │
│                    │  Device   │                             │
│                    │  Registry │                             │
│                    └───────────┘                             │
└─────────────────────────────────────────────────────────────┘
                      │ TCP (JSON)
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              Devices (iPhone / OAK)                          │
│              :8080                                           │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
multicam-relay/
├── Cargo.toml              # Dependencies and build config
├── Makefile                # Build tasks (make help)
├── HANDOFF.md              # This file
├── .cargo/
│   └── config.toml         # Cargo configuration
├── assets/
│   └── Info.plist          # macOS app bundle metadata
├── scripts/
│   └── bundle-macos.sh     # macOS .app bundle script
└── src/
    ├── main.rs             # Entry point, wires everything together
    ├── config.rs           # Constants (port, service type, version)
    ├── protocol.rs         # WebSocket message types (serde)
    ├── device_registry.rs  # Thread-safe device storage
    ├── mdns.rs             # mDNS discovery using mdns-sd crate
    ├── tcp_client.rs       # TCP communication to devices
    └── websocket.rs        # WebSocket server + HTTP health endpoint
```

## Key Files

### `src/config.rs`
Constants used throughout the app:
- `RELAY_PORT`: 9847 (WebSocket/HTTP server)
- `MDNS_SERVICE_TYPE`: `_multicam._tcp.local.`
- `DEFAULT_DEVICE_PORT`: 8080
- `COMMAND_TIMEOUT`: 60 seconds

### `src/protocol.rs`
Defines all WebSocket message types:

**Browser → Relay:**
- `discover` - Trigger mDNS discovery refresh
- `get_devices` - Get list of known devices
- `command` - Send command to specific device
- `broadcast` - Send command to all devices

**Relay → Browser:**
- `device_discovered` - New device found
- `device_removed` - Device went offline
- `device_list` - List of all devices
- `command_response` - Response from device
- `broadcast_response` - Aggregated responses
- `error` - Error message

### `src/mdns.rs`
Uses the `mdns-sd` crate for cross-platform mDNS discovery. Browses for `_multicam._tcp.local.` services and emits events when devices appear/disappear.

### `src/tcp_client.rs`
Handles TCP communication with devices. Supports:
- Single device commands
- Broadcast to multiple devices (concurrent)
- 60-second timeout per command

### `src/websocket.rs`
Warp-based server providing:
- `GET /health` - Health check endpoint
- `WS /ws` - WebSocket endpoint for browser communication

## WebSocket API

### Connection
```
ws://localhost:9847/ws
```

On connect, the relay sends the current device list.

### Messages (Browser → Relay)

**Get devices:**
```json
{"type": "get_devices"}
```

**Send command to device:**
```json
{
  "type": "command",
  "device_ip": "192.168.1.100",
  "device_port": 8080,
  "command": {
    "command": "START_RECORDING",
    "timestamp": 1700000000.5,
    "deviceId": "controller"
  }
}
```

**Broadcast to all devices:**
```json
{
  "type": "broadcast",
  "command": {
    "command": "START_RECORDING",
    "timestamp": 1700000000.5,
    "deviceId": "controller"
  }
}
```

### Messages (Relay → Browser)

**Device discovered:**
```json
{
  "type": "device_discovered",
  "device": {
    "name": "multiCam-oak-abc123._multicam._tcp.local.",
    "ip": "192.168.1.100",
    "port": 8080,
    "device_id": "abc123"
  }
}
```

**Command response:**
```json
{
  "type": "command_response",
  "device_ip": "192.168.1.100",
  "response": { /* device JSON response */ }
}
```

## Health Check

```bash
curl http://localhost:9847/health
# {"status":"ok","version":"0.1.0"}
```

## Building & Running

### Development
```bash
# Run in debug mode
cargo run

# With verbose logging
RUST_LOG=debug cargo run

# Build debug binary
cargo build
```

### Production
```bash
# Build release binary
cargo build --release

# Create macOS .app bundle
make bundle-macos

# Install to /Applications
make install
```

### All Make Tasks
```bash
make help
```

## macOS App Bundle

The bundle script creates:
```
MultiCam Relay.app/
└── Contents/
    ├── Info.plist          # App metadata + protocol handler
    ├── PkgInfo
    ├── MacOS/
    │   └── multicam-relay  # The binary
    └── Resources/
        └── AppIcon.icns    # (optional)
```

### Protocol Handler
The app registers `multicam://` URL scheme. Browser can launch with:
```javascript
window.location.href = 'multicam://launch';
```

### Background Mode
`LSUIElement = true` in Info.plist means no dock icon - runs invisibly.

## Browser Integration Flow

1. Browser pings `http://localhost:9847/health`
2. If no response, try `multicam://launch` (protocol handler)
3. Wait 2-3 seconds, retry health check
4. If still no response, prompt user to download/install

```javascript
async function connectToRelay() {
  // Try direct connection
  if (await pingHealth()) {
    return connectWebSocket();
  }

  // Try launching via protocol handler
  window.location.href = 'multicam://launch';
  await sleep(2500);

  if (await pingHealth()) {
    return connectWebSocket();
  }

  // Prompt download
  showDownloadPrompt();
}
```

## Supported Device Commands

The relay forwards these commands to devices:
- `START_RECORDING` - Start recording (with optional sync timestamp)
- `STOP_RECORDING` - Stop recording
- `DEVICE_STATUS` - Get device status
- `HEARTBEAT` - Keep-alive ping
- `UPLOAD_TO_CLOUD` - Trigger device-to-S3 upload

**Not implemented in relay (binary protocol):**
- `GET_VIDEO` - File download
- `LIST_FILES` - List recordings

## Dependencies

Key crates:
- `tokio` - Async runtime
- `warp` - HTTP/WebSocket server
- `mdns-sd` - Cross-platform mDNS (uses native OS APIs)
- `serde` / `serde_json` - JSON serialization
- `tracing` - Logging

## Known Issues / Notes

1. **awdl0 errors** - You may see errors about `awdl0` interface (Apple Wireless Direct Link). These are harmless - mDNS still works on other interfaces.

2. **Release build** - If release build fails with SIGKILL, it's likely resource constraints. Debug builds work fine for testing.

3. **Code signing** - The bundle script does ad-hoc signing. For distribution, you'd need proper Apple Developer signing.

## Future Work

- [ ] Windows support (installer + protocol handler registration)
- [ ] GET_VIDEO support (binary streaming over WebSocket)
- [ ] App icon
- [ ] Notarization for macOS distribution
- [ ] Auto-update mechanism
