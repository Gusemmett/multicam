//! Thread-safe registry of discovered devices

use crate::protocol::Device;
use parking_lot::RwLock;
use std::collections::HashMap;
use std::sync::Arc;

/// Thread-safe device registry
#[derive(Debug, Clone, Default)]
pub struct DeviceRegistry {
    /// Devices keyed by "ip:port"
    devices: Arc<RwLock<HashMap<String, Device>>>,
}

impl DeviceRegistry {
    pub fn new() -> Self {
        Self {
            devices: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Generate key for device lookup
    fn key(ip: &str, port: u16) -> String {
        format!("{}:{}", ip, port)
    }

    /// Add or update a device
    pub fn add_device(&self, device: Device) {
        let key = Self::key(&device.ip, device.port);
        self.devices.write().insert(key, device);
    }

    /// Remove a device by IP and port
    pub fn remove_device(&self, ip: &str, port: u16) -> Option<Device> {
        let key = Self::key(ip, port);
        self.devices.write().remove(&key)
    }

    /// Get all devices
    pub fn get_all_devices(&self) -> Vec<Device> {
        self.devices.read().values().cloned().collect()
    }

    /// Get a device by IP and port
    #[allow(dead_code)]
    pub fn get_device(&self, ip: &str, port: u16) -> Option<Device> {
        let key = Self::key(ip, port);
        self.devices.read().get(&key).cloned()
    }

    /// Check if a device exists
    #[allow(dead_code)]
    pub fn has_device(&self, ip: &str, port: u16) -> bool {
        let key = Self::key(ip, port);
        self.devices.read().contains_key(&key)
    }

    /// Get device count
    #[allow(dead_code)]
    pub fn count(&self) -> usize {
        self.devices.read().len()
    }
}
