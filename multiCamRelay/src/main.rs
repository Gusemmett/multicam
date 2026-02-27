//! MultiCam Relay - WebSocket to TCP bridge for browser-based device control

// Hide console window on Windows release builds
#![cfg_attr(
    all(target_os = "windows", not(debug_assertions)),
    windows_subsystem = "windows"
)]

mod config;
mod device_registry;
mod mdns;
mod protocol;
mod tcp_client;
mod updater;
mod url_handler;
mod websocket;

use crate::config::{MDNS_CHECK_INTERVAL_SECS, RELAY_PORT, UPDATE_STARTUP_DELAY_SECS};
use crate::device_registry::DeviceRegistry;
use crate::mdns::{check_mdns_available, MdnsDiscovery};
use crate::protocol::ServerMessage;
use crate::updater::Updater;
use std::sync::Arc;
use tokio::sync::{broadcast, RwLock};
use tracing::{debug, error, info, warn};
use tracing_subscriber::{fmt, prelude::*, EnvFilter};

/// Shared state for network/discovery status
pub struct NetworkStatusState {
    pub discovery_available: bool,
    pub error_message: Option<String>,
}

#[tokio::main]
async fn main() {
    // Initialize logging - use RUST_LOG if set, otherwise default to info level
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("multicam_relay=info"));

    tracing_subscriber::registry()
        .with(fmt::layer())
        .with(env_filter)
        .init();

    info!("MultiCam Relay v{} starting...", config::VERSION);

    // Parse URL scheme arguments (when launched via multicam:// URL)
    let args: Vec<String> = std::env::args().collect();
    if let Some(url_params) = url_handler::parse_launch_url(&args) {
        info!("Launched via URL scheme: command={}", url_params.command);
        if let Some(session) = url_params.session() {
            info!("Session ID: {}", session);
        }
        if let Some(callback) = url_params.callback() {
            info!("Callback URL: {}", callback);
        }
        // Log all parameters for debugging
        for (key, value) in &url_params.params {
            info!("URL param: {}={}", key, value);
        }
    }

    // Create shared device registry
    let registry = DeviceRegistry::new();

    // Create broadcast channel for network status updates
    let (status_tx, _) = broadcast::channel::<ServerMessage>(16);

    // Start mDNS discovery with graceful degradation
    let (mdns, event_tx) = match MdnsDiscovery::new(registry.clone()) {
        Ok(m) => {
            match m.start_discovery() {
                Ok(()) => {
                    info!("mDNS discovery started, searching for devices...");
                    let tx = m.event_sender();
                    (Some(m), tx)
                }
                Err(e) => {
                    error!("Failed to start mDNS discovery: {}", e);
                    warn!("Device discovery unavailable - check Local Network permissions");
                    let (tx, _) = broadcast::channel(100);
                    (None, tx)
                }
            }
        }
        Err(e) => {
            error!("Failed to create mDNS discovery: {}", e);
            warn!("Device discovery unavailable - check Local Network permissions");
            let (tx, _) = broadcast::channel(100);
            (None, tx)
        }
    };

    // Keep mdns alive for app lifetime
    let _mdns = mdns;

    // Create shared network status state (start pessimistic, will be updated by first check)
    let network_status = Arc::new(RwLock::new(NetworkStatusState {
        discovery_available: false,
        error_message: Some("Checking network permissions...".to_string()),
    }));

    // Spawn periodic mDNS availability check task
    let status_clone = network_status.clone();
    let status_tx_clone = status_tx.clone();
    tokio::spawn(async move {
        // Run first check immediately
        let mut first_check = true;

        loop {
            if !first_check {
                tokio::time::sleep(tokio::time::Duration::from_secs(MDNS_CHECK_INTERVAL_SECS)).await;
            }
            first_check = false;

            let available = check_mdns_available().await;

            let mut state = status_clone.write().await;
            if state.discovery_available != available {
                state.discovery_available = available;
                state.error_message = if available {
                    info!("mDNS discovery is now available");
                    None
                } else {
                    warn!("mDNS discovery is unavailable - check Local Network permissions");
                    Some("Discovery unavailable - check Local Network permissions in System Settings".to_string())
                };

                // Broadcast status change to all clients
                let msg = ServerMessage::NetworkStatus {
                    discovery_available: available,
                    error_message: state.error_message.clone(),
                };
                debug!("Broadcasting network status change: discovery_available={}", available);
                let _ = status_tx_clone.send(msg);
            }
            drop(state);
        }
    });

    // Create updater
    let updater = Arc::new(Updater::new());

    // Spawn background task to check for updates after startup delay
    let startup_updater = updater.clone();
    tokio::spawn(async move {
        tokio::time::sleep(tokio::time::Duration::from_secs(UPDATE_STARTUP_DELAY_SECS)).await;
        info!("Checking for updates...");
        match startup_updater.check_for_updates().await {
            Ok(Some(info)) => {
                info!(
                    "Update available: {} -> {}",
                    info.current_version, info.new_version
                );
            }
            Ok(None) => {
                info!("Already running latest version");
            }
            Err(e) => {
                info!("Update check failed: {}", e);
            }
        }
    });

    // Run WebSocket server (this blocks)
    websocket::run_server(RELAY_PORT, registry, event_tx, updater, network_status, status_tx).await;
}
