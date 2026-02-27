//! Protocol types for WebSocket and device communication

use crate::updater::{UpdateInfo, UpdateProgress, UpdateState};
use serde::{Deserialize, Serialize};

/// Device information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Device {
    pub name: String,
    pub ip: String,
    pub port: u16,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub device_id: Option<String>,
}

/// Messages from browser to relay
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ClientMessage {
    /// Request to start/refresh mDNS discovery
    Discover,
    /// Get list of currently known devices
    GetDevices,
    /// Send command to a specific device
    Command {
        device_ip: String,
        device_port: u16,
        command: serde_json::Value,
    },
    /// Broadcast command to all known devices
    Broadcast {
        command: serde_json::Value,
    },
    /// Check for available updates
    CheckUpdate,
    /// Download and apply available update
    ApplyUpdate,
    /// Get current update status
    GetUpdateStatus,
    /// Restart app after update is applied
    RestartApp,
    /// Shutdown the app
    Shutdown,
}

/// Messages from relay to browser
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ServerMessage {
    /// A device was discovered via mDNS
    DeviceDiscovered { device: Device },
    /// A device was removed (mDNS goodbye)
    DeviceRemoved { device: Device },
    /// List of all known devices (response to GetDevices)
    DeviceList { devices: Vec<Device> },
    /// Response from a device command
    CommandResponse {
        device_ip: String,
        response: serde_json::Value,
    },
    /// Broadcast response (aggregated from all devices)
    BroadcastResponse {
        responses: Vec<BroadcastDeviceResponse>,
    },
    /// Error occurred
    Error {
        message: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        device_ip: Option<String>,
    },
    /// Update is available
    UpdateAvailable {
        current_version: String,
        new_version: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        release_notes: Option<String>,
        #[serde(skip_serializing_if = "Option::is_none")]
        size: Option<u64>,
    },
    /// Current update state
    UpdateStatus {
        state: UpdateState,
    },
    /// Update download/install progress
    UpdateProgress {
        phase: String,
        progress: u8,
        message: String,
    },
    /// Update is ready, restart required
    UpdateReady {
        message: String,
    },
    /// Network/discovery status (sent on connect)
    NetworkStatus {
        discovery_available: bool,
        #[serde(skip_serializing_if = "Option::is_none")]
        error_message: Option<String>,
    },
}

/// Individual device response in a broadcast
#[derive(Debug, Clone, Serialize)]
pub struct BroadcastDeviceResponse {
    pub device_ip: String,
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub response: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// Health check response
#[derive(Debug, Serialize)]
pub struct HealthResponse {
    pub status: &'static str,
    pub version: &'static str,
}

impl HealthResponse {
    pub fn ok() -> Self {
        Self {
            status: "ok",
            version: crate::config::VERSION,
        }
    }
}

impl ServerMessage {
    /// Create UpdateAvailable message from UpdateInfo
    pub fn from_update_info(info: &UpdateInfo) -> Self {
        Self::UpdateAvailable {
            current_version: info.current_version.clone(),
            new_version: info.new_version.clone(),
            release_notes: info.release_notes.clone(),
            size: info.size,
        }
    }

    /// Create UpdateProgress message from updater::UpdateProgress
    pub fn from_update_progress(progress: &UpdateProgress) -> Self {
        Self::UpdateProgress {
            phase: progress.phase.clone(),
            progress: progress.progress,
            message: progress.message.clone(),
        }
    }
}
