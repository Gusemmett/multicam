//! WebSocket server for browser communication

use crate::device_registry::DeviceRegistry;
use crate::mdns::MdnsEvent;
use crate::protocol::{
    BroadcastDeviceResponse, ClientMessage, HealthResponse, ServerMessage,
};
use crate::tcp_client;
use crate::updater::Updater;
use crate::NetworkStatusState;
use futures::{SinkExt, StreamExt};
use std::sync::Arc;
use tokio::sync::{broadcast, mpsc, RwLock};
use tracing::{debug, error, info, warn};
use warp::ws::{Message, WebSocket};
use warp::Filter;

/// State shared across WebSocket connections
pub struct AppState {
    pub registry: DeviceRegistry,
    pub mdns_events: broadcast::Sender<MdnsEvent>,
    pub updater: Arc<Updater>,
    pub update_events: broadcast::Sender<ServerMessage>,
    pub network_status: Arc<RwLock<NetworkStatusState>>,
    pub status_events: broadcast::Sender<ServerMessage>,
}

/// Run the WebSocket and HTTP server
pub async fn run_server(
    port: u16,
    registry: DeviceRegistry,
    mdns_events: broadcast::Sender<MdnsEvent>,
    updater: Arc<Updater>,
    network_status: Arc<RwLock<NetworkStatusState>>,
    status_events: broadcast::Sender<ServerMessage>,
) {
    let (update_tx, _) = broadcast::channel::<ServerMessage>(16);

    let state = Arc::new(AppState {
        registry,
        mdns_events,
        updater,
        update_events: update_tx,
        network_status,
        status_events,
    });

    // Health check endpoint
    let health = warp::path("health").and(warp::get()).map(|| {
        let response = HealthResponse::ok();
        warp::reply::json(&response)
    });

    // WebSocket endpoint
    let ws_state = state.clone();
    let websocket = warp::path("ws")
        .and(warp::ws())
        .and(warp::any().map(move || ws_state.clone()))
        .map(|ws: warp::ws::Ws, state: Arc<AppState>| {
            ws.on_upgrade(move |socket| handle_websocket(socket, state))
        });

    // CORS headers for browser access
    let cors = warp::cors()
        .allow_any_origin()
        .allow_methods(vec!["GET", "POST", "OPTIONS"])
        .allow_headers(vec!["Content-Type"]);

    let routes = health.or(websocket).with(cors);

    info!("Starting relay server on port {}", port);
    warp::serve(routes).run(([127, 0, 0, 1], port)).await;
}

/// Handle a single WebSocket connection
async fn handle_websocket(socket: WebSocket, state: Arc<AppState>) {
    info!("New WebSocket connection");

    let (mut ws_tx, mut ws_rx) = socket.split();

    // Subscribe to mDNS events
    let mut mdns_rx = state.mdns_events.subscribe();

    // Subscribe to update events
    let mut update_rx = state.update_events.subscribe();

    // Subscribe to network status events
    let mut status_rx = state.status_events.subscribe();

    // Send current device list on connect
    let devices = state.registry.get_all_devices();
    debug!("[Browser <- Relay] Sending initial device list ({} devices)", devices.len());
    let msg = ServerMessage::DeviceList { devices };
    if let Ok(json) = serde_json::to_string(&msg) {
        debug!("[Browser <- Relay] {}", json);
        if let Err(e) = ws_tx.send(Message::text(json)).await {
            error!("Failed to send initial device list: {}", e);
            return;
        }
    }

    // Send current network/discovery status
    let network_state = state.network_status.read().await;
    let status_msg = ServerMessage::NetworkStatus {
        discovery_available: network_state.discovery_available,
        error_message: network_state.error_message.clone(),
    };
    drop(network_state);
    if let Ok(json) = serde_json::to_string(&status_msg) {
        debug!("[Browser <- Relay] {}", json);
        if let Err(e) = ws_tx.send(Message::text(json)).await {
            error!("Failed to send network status: {}", e);
            return;
        }
    }

    // Clone state for the mDNS event handler
    let state_clone = state.clone();

    // Use channels to communicate between tasks
    let (internal_tx, mut internal_rx) = tokio::sync::mpsc::channel::<ServerMessage>(100);
    let internal_tx_mdns = internal_tx.clone();
    let internal_tx_update = internal_tx.clone();
    let internal_tx_status = internal_tx.clone();

    // Task to forward mDNS events to WebSocket
    let mdns_task = tokio::spawn(async move {
        while let Ok(event) = mdns_rx.recv().await {
            let msg = match &event {
                MdnsEvent::DeviceDiscovered(device) => {
                    debug!("[Browser <- Relay] mDNS device discovered: {} ({}:{})", device.name, device.ip, device.port);
                    ServerMessage::DeviceDiscovered { device: device.clone() }
                }
                MdnsEvent::DeviceRemoved(device) => {
                    debug!("[Browser <- Relay] mDNS device removed: {} ({}:{})", device.name, device.ip, device.port);
                    ServerMessage::DeviceRemoved { device: device.clone() }
                }
            };
            if internal_tx_mdns.send(msg).await.is_err() {
                break;
            }
        }
    });

    // Task to forward update events to WebSocket
    let update_task = tokio::spawn(async move {
        while let Ok(msg) = update_rx.recv().await {
            debug!("[Browser <- Relay] Update event: {:?}", msg);
            if internal_tx_update.send(msg).await.is_err() {
                break;
            }
        }
    });

    // Task to forward network status events to WebSocket
    let status_task = tokio::spawn(async move {
        while let Ok(msg) = status_rx.recv().await {
            debug!("[Browser <- Relay] Network status event: {:?}", msg);
            if internal_tx_status.send(msg).await.is_err() {
                break;
            }
        }
    });

    // Task to handle outgoing messages
    let send_task = tokio::spawn(async move {
        while let Some(msg) = internal_rx.recv().await {
            if let Ok(json) = serde_json::to_string(&msg) {
                debug!("[Browser <- Relay] Sending: {}", json);
                if ws_tx.send(Message::text(json)).await.is_err() {
                    break;
                }
            }
        }
    });

    // Handle incoming messages
    while let Some(result) = ws_rx.next().await {
        let msg = match result {
            Ok(msg) => msg,
            Err(e) => {
                error!("WebSocket error: {}", e);
                break;
            }
        };

        if msg.is_close() {
            info!("WebSocket connection closed");
            break;
        }

        if !msg.is_text() {
            continue;
        }

        let text = msg.to_str().unwrap_or_default();
        debug!("[Browser -> Relay] Received: {}", text);

        let response = handle_client_message(text, &state_clone).await;
        if let Some(response) = response {
            if internal_tx.send(response).await.is_err() {
                break;
            }
        }
    }

    // Clean up
    mdns_task.abort();
    update_task.abort();
    status_task.abort();
    send_task.abort();
    info!("WebSocket connection ended");
}

/// Process a client message and return a response
async fn handle_client_message(text: &str, state: &AppState) -> Option<ServerMessage> {
    let msg: ClientMessage = match serde_json::from_str(text) {
        Ok(m) => m,
        Err(e) => {
            warn!("Failed to parse message: {}", e);
            return Some(ServerMessage::Error {
                message: format!("Invalid message format: {}", e),
                device_ip: None,
            });
        }
    };

    match msg {
        ClientMessage::Discover => {
            // Discovery is continuous, just acknowledge
            debug!("[Browser -> Relay] Discover request (discovery is continuous)");
            None
        }
        ClientMessage::GetDevices => {
            let devices = state.registry.get_all_devices();
            debug!("[Browser -> Relay] GetDevices request - returning {} devices", devices.len());
            Some(ServerMessage::DeviceList { devices })
        }
        ClientMessage::Command {
            device_ip,
            device_port,
            command,
        } => {
            debug!("[Browser -> Relay] Command request for {}:{}", device_ip, device_port);
            debug!("[Relay -> Device] Sending to {}:{}: {}", device_ip, device_port, command);
            match tcp_client::send_command(&device_ip, device_port, &command).await {
                Ok(response) => {
                    debug!("[Device -> Relay] Response from {}:{}: {}", device_ip, device_port, response);
                    Some(ServerMessage::CommandResponse {
                        device_ip,
                        response,
                    })
                }
                Err(e) => {
                    debug!("[Device -> Relay] Error from {}:{}: {}", device_ip, device_port, e);
                    Some(ServerMessage::Error {
                        message: e.to_string(),
                        device_ip: Some(device_ip),
                    })
                }
            }
        }
        ClientMessage::Broadcast { command } => {
            let devices = state.registry.get_all_devices();
            debug!("[Browser -> Relay] Broadcast request to {} devices", devices.len());
            if devices.is_empty() {
                debug!("[Browser -> Relay] Broadcast failed - no devices available");
                return Some(ServerMessage::Error {
                    message: "No devices available".to_string(),
                    device_ip: None,
                });
            }

            let device_addrs: Vec<(String, u16)> =
                devices.iter().map(|d| (d.ip.clone(), d.port)).collect();

            debug!("[Relay -> Device] Broadcasting to devices: {:?}", device_addrs);
            debug!("[Relay -> Device] Broadcast command: {}", command);
            let results = tcp_client::broadcast_command(&device_addrs, &command).await;

            let responses: Vec<BroadcastDeviceResponse> = results
                .into_iter()
                .map(|(ip, port, result)| match result {
                    Ok(response) => {
                        debug!("[Device -> Relay] Broadcast response from {}:{}: {}", ip, port, response);
                        BroadcastDeviceResponse {
                            device_ip: ip,
                            success: true,
                            response: Some(response),
                            error: None,
                        }
                    }
                    Err(e) => {
                        debug!("[Device -> Relay] Broadcast error from {}:{}: {}", ip, port, e);
                        BroadcastDeviceResponse {
                            device_ip: ip,
                            success: false,
                            response: None,
                            error: Some(e.to_string()),
                        }
                    }
                })
                .collect();

            debug!("[Browser <- Relay] Broadcast complete - {} responses", responses.len());
            Some(ServerMessage::BroadcastResponse { responses })
        }
        ClientMessage::CheckUpdate => {
            debug!("[Browser -> Relay] CheckUpdate request");
            let updater = state.updater.clone();
            let update_tx = state.update_events.clone();

            // Spawn async task for update check
            tokio::spawn(async move {
                match updater.check_for_updates().await {
                    Ok(Some(info)) => {
                        let msg = ServerMessage::from_update_info(&info);
                        let _ = update_tx.send(msg);
                    }
                    Ok(None) => {
                        let _ = update_tx.send(ServerMessage::UpdateStatus {
                            state: crate::updater::UpdateState::Idle,
                        });
                    }
                    Err(e) => {
                        let _ = update_tx.send(ServerMessage::Error {
                            message: format!("Update check failed: {}", e),
                            device_ip: None,
                        });
                    }
                }
            });

            None // Response will be sent via update_events channel
        }
        ClientMessage::ApplyUpdate => {
            debug!("[Browser -> Relay] ApplyUpdate request");
            let updater = state.updater.clone();
            let update_tx = state.update_events.clone();

            // Create progress channel
            let (progress_tx, mut progress_rx) = mpsc::channel(32);

            // Spawn task to forward progress to update_events
            let update_tx_progress = update_tx.clone();
            tokio::spawn(async move {
                while let Some(progress) = progress_rx.recv().await {
                    let msg = ServerMessage::from_update_progress(&progress);
                    let _ = update_tx_progress.send(msg);
                }
            });

            // Spawn async task for update application
            tokio::spawn(async move {
                match updater.apply_update(Some(progress_tx)).await {
                    Ok(()) => {
                        let _ = update_tx.send(ServerMessage::UpdateReady {
                            message: "Update installed. Restart to apply.".to_string(),
                        });
                    }
                    Err(e) => {
                        let _ = update_tx.send(ServerMessage::Error {
                            message: format!("Update failed: {}", e),
                            device_ip: None,
                        });
                    }
                }
            });

            None // Response will be sent via update_events channel
        }
        ClientMessage::GetUpdateStatus => {
            debug!("[Browser -> Relay] GetUpdateStatus request");
            let current_state = state.updater.state();
            Some(ServerMessage::UpdateStatus {
                state: current_state,
            })
        }
        ClientMessage::RestartApp => {
            debug!("[Browser -> Relay] RestartApp request");
            // Send acknowledgment before restarting
            let _ = state.update_events.send(ServerMessage::UpdateStatus {
                state: crate::updater::UpdateState::ReadyToRestart,
            });

            // Delay slightly to allow message to be sent
            tokio::spawn(async {
                tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
                if let Err(e) = crate::updater::Updater::restart_app() {
                    error!("Failed to restart app: {}", e);
                }
            });

            None
        }
        ClientMessage::Shutdown => {
            info!("[Browser -> Relay] Shutdown request");

            // Delay slightly to allow any pending messages to be sent
            tokio::spawn(async {
                tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
                info!("Shutting down...");
                std::process::exit(0);
            });

            None
        }
    }
}
