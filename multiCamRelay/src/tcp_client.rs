//! TCP client for communicating with MultiCam devices

use crate::config::{TCP_CONNECT_TIMEOUT_SECS, TCP_IO_TIMEOUT_SECS};
use std::time::Duration;
use thiserror::Error;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::time::timeout;
use tracing::debug;

#[derive(Error, Debug)]
pub enum TcpError {
    #[error("Connection timeout")]
    ConnectTimeout,
    #[error("Read timeout")]
    ReadTimeout,
    #[error("Write timeout")]
    WriteTimeout,
    #[error("Connection failed: {0}")]
    ConnectionFailed(String),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

/// Send a JSON command to a device and receive the JSON response
pub async fn send_command(
    ip: &str,
    port: u16,
    command: &serde_json::Value,
) -> Result<serde_json::Value, TcpError> {
    let addr = format!("{}:{}", ip, port);
    debug!("[Relay -> Device] Connecting to {}", addr);

    // Connect with timeout
    let stream = timeout(
        Duration::from_secs(TCP_CONNECT_TIMEOUT_SECS),
        TcpStream::connect(&addr),
    )
    .await
    .map_err(|_| {
        debug!("[Relay -> Device] Connection timeout to {}", addr);
        TcpError::ConnectTimeout
    })?
    .map_err(|e| {
        debug!("[Relay -> Device] Connection failed to {}: {}", addr, e);
        TcpError::ConnectionFailed(e.to_string())
    })?;

    debug!("[Relay -> Device] Connected to {}", addr);

    let (mut reader, mut writer) = stream.into_split();

    // Serialize and send command
    let command_bytes = serde_json::to_vec(command)?;
    debug!(
        "[Relay -> Device] Sending to {}: {}",
        addr,
        String::from_utf8_lossy(&command_bytes)
    );

    timeout(
        Duration::from_secs(TCP_IO_TIMEOUT_SECS),
        writer.write_all(&command_bytes),
    )
    .await
    .map_err(|_| {
        debug!("[Relay -> Device] Write timeout to {}", addr);
        TcpError::WriteTimeout
    })??;

    debug!("[Relay -> Device] Command sent to {}, waiting for response", addr);

    // Read response - read a chunk (don't wait for EOF, iOS doesn't close connection)
    let mut response_bytes = vec![0u8; 65536];
    let n = timeout(
        Duration::from_secs(TCP_IO_TIMEOUT_SECS),
        reader.read(&mut response_bytes),
    )
    .await
    .map_err(|_| {
        debug!("[Device -> Relay] Read timeout from {}", addr);
        TcpError::ReadTimeout
    })??;

    response_bytes.truncate(n);

    if n == 0 {
        return Err(TcpError::Io(std::io::Error::new(
            std::io::ErrorKind::UnexpectedEof,
            "Device closed connection without sending response",
        )));
    }

    debug!(
        "[Device -> Relay] Received from {}: {}",
        addr,
        String::from_utf8_lossy(&response_bytes)
    );

    // Parse JSON response
    let response: serde_json::Value = serde_json::from_slice(&response_bytes)?;

    Ok(response)
}

/// Send command to multiple devices concurrently
pub async fn broadcast_command(
    devices: &[(String, u16)],
    command: &serde_json::Value,
) -> Vec<(String, u16, Result<serde_json::Value, TcpError>)> {
    debug!("[Relay -> Device] Starting broadcast to {} devices", devices.len());
    let futures: Vec<_> = devices
        .iter()
        .map(|(ip, port)| {
            let ip = ip.clone();
            let port = *port;
            let cmd = command.clone();
            async move {
                let result = send_command(&ip, port, &cmd).await;
                (ip, port, result)
            }
        })
        .collect();

    let results = futures::future::join_all(futures).await;
    debug!("[Relay -> Device] Broadcast complete, received {} results", results.len());
    results
}
