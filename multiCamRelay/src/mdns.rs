//! mDNS device discovery using mdns-sd

use crate::config::{MDNS_CHECK_TIMEOUT_SECS, MDNS_SERVICE_TYPE};
use crate::device_registry::DeviceRegistry;
use crate::protocol::Device;
use mdns_sd::{ServiceDaemon, ServiceEvent};
use std::net::IpAddr;
use std::time::Duration;
use tokio::sync::broadcast;
use tracing::{debug, error, info, warn};

/// Events emitted by the mDNS discovery service
#[derive(Debug, Clone)]
pub enum MdnsEvent {
    DeviceDiscovered(Device),
    DeviceRemoved(Device),
}

/// mDNS discovery service
pub struct MdnsDiscovery {
    daemon: ServiceDaemon,
    registry: DeviceRegistry,
    event_tx: broadcast::Sender<MdnsEvent>,
}

impl MdnsDiscovery {
    /// Get the event sender for sharing with other components
    pub fn event_sender(&self) -> broadcast::Sender<MdnsEvent> {
        self.event_tx.clone()
    }
}

impl MdnsDiscovery {
    /// Create a new mDNS discovery service
    pub fn new(registry: DeviceRegistry) -> Result<Self, mdns_sd::Error> {
        let daemon = ServiceDaemon::new()?;
        let (event_tx, _) = broadcast::channel(100);

        Ok(Self {
            daemon,
            registry,
            event_tx,
        })
    }

    /// Subscribe to discovery events
    #[allow(dead_code)]
    pub fn subscribe(&self) -> broadcast::Receiver<MdnsEvent> {
        self.event_tx.subscribe()
    }

    /// Start browsing for MultiCam devices
    pub fn start_discovery(&self) -> Result<(), mdns_sd::Error> {
        info!("Starting mDNS discovery for {}", MDNS_SERVICE_TYPE);
        let receiver = self.daemon.browse(MDNS_SERVICE_TYPE)?;

        let registry = self.registry.clone();
        let event_tx = self.event_tx.clone();

        // Spawn task to handle discovery events
        tokio::spawn(async move {
            while let Ok(event) = receiver.recv() {
                match event {
                    ServiceEvent::ServiceResolved(info) => {
                        debug!("Service resolved: {:?}", info);

                        // Get first IPv4 address
                        let ip = info
                            .get_addresses()
                            .iter()
                            .find(|addr| matches!(addr, IpAddr::V4(_)))
                            .or_else(|| info.get_addresses().iter().next());

                        let Some(ip) = ip else {
                            warn!("No IP address for service: {}", info.get_fullname());
                            continue;
                        };

                        let port = info.get_port();
                        let name = info.get_fullname().to_string();

                        // Extract device_id from properties if available
                        let device_id = info
                            .get_properties()
                            .iter()
                            .find(|p| p.key() == "deviceId")
                            .map(|p| p.val_str().to_string());

                        let device = Device {
                            name,
                            ip: ip.to_string(),
                            port,
                            device_id,
                        };

                        info!("Discovered device: {} at {}:{}", device.name, device.ip, device.port);
                        registry.add_device(device.clone());
                        let _ = event_tx.send(MdnsEvent::DeviceDiscovered(device));
                    }
                    ServiceEvent::ServiceRemoved(_, fullname) => {
                        debug!("Service removed: {}", fullname);

                        // Try to find and remove the device
                        let devices = registry.get_all_devices();
                        if let Some(device) = devices.iter().find(|d| d.name == fullname) {
                            let device = device.clone();
                            registry.remove_device(&device.ip, device.port);
                            info!("Removed device: {} at {}:{}", device.name, device.ip, device.port);
                            let _ = event_tx.send(MdnsEvent::DeviceRemoved(device));
                        }
                    }
                    ServiceEvent::SearchStarted(_) => {
                        debug!("mDNS search started");
                    }
                    ServiceEvent::SearchStopped(_) => {
                        debug!("mDNS search stopped");
                    }
                    _ => {}
                }
            }
        });

        Ok(())
    }

    /// Get the device registry
    #[allow(dead_code)]
    pub fn registry(&self) -> &DeviceRegistry {
        &self.registry
    }
}

impl Drop for MdnsDiscovery {
    fn drop(&mut self) {
        if let Err(e) = self.daemon.shutdown() {
            error!("Error shutting down mDNS daemon: {}", e);
        }
    }
}

/// Check if mDNS discovery is working by attempting a browse and waiting for SearchStarted
pub async fn check_mdns_available() -> bool {
    // Create temporary daemon for testing
    let daemon = match ServiceDaemon::new() {
        Ok(d) => d,
        Err(e) => {
            debug!("mDNS check: failed to create daemon: {}", e);
            return false;
        }
    };

    let receiver = match daemon.browse(MDNS_SERVICE_TYPE) {
        Ok(r) => r,
        Err(e) => {
            debug!("mDNS check: failed to start browse: {}", e);
            let _ = daemon.shutdown();
            return false;
        }
    };

    // Wait for SearchStarted event with timeout
    let timeout_duration = Duration::from_secs(MDNS_CHECK_TIMEOUT_SECS);
    let result = tokio::time::timeout(timeout_duration, async {
        while let Ok(event) = receiver.recv() {
            if matches!(event, ServiceEvent::SearchStarted(_)) {
                return true;
            }
        }
        false
    })
    .await;

    // Clean up
    let _ = daemon.shutdown();

    match result {
        Ok(success) => {
            debug!("mDNS check: {}", if success { "available" } else { "unavailable" });
            success
        }
        Err(_) => {
            debug!("mDNS check: timeout waiting for SearchStarted");
            false
        }
    }
}
