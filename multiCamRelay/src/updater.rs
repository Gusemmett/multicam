//! Auto-update functionality for MultiCam Relay
//!
//! Checks S3 for new versions, downloads DMG updates with progress reporting,
//! and applies updates by mounting DMG and copying the app bundle.

use crate::config::{UPDATE_BASE_URL, UPDATE_CHECK_TIMEOUT_SECS, UPDATE_PREFIX, VERSION};
use futures::StreamExt;
use parking_lot::RwLock;
use reqwest::Client;
use semver::Version;
use serde::{Deserialize, Serialize};
use std::io::Write;
use std::path::PathBuf;
use std::process::Command;
use std::sync::Arc;
use thiserror::Error;
use tokio::sync::mpsc;
use tracing::{debug, error, info, warn};

/// Errors that can occur during update operations
#[derive(Debug, Error)]
#[allow(dead_code)]
pub enum UpdateError {
    #[error("Network error: {0}")]
    Network(#[from] reqwest::Error),

    #[error("Failed to parse version: {0}")]
    VersionParse(#[from] semver::Error),

    #[error("Failed to parse manifest: {0}")]
    ManifestParse(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Failed to mount DMG: {0}")]
    MountFailed(String),

    #[error("Failed to copy app: {0}")]
    CopyFailed(String),

    #[error("Failed to unmount DMG: {0}")]
    UnmountFailed(String),

    #[error("App bundle not found in DMG")]
    AppNotFound,

    #[error("Cannot determine app path")]
    AppPathUnknown,

    #[error("Update cancelled")]
    Cancelled,
}

/// Current state of the update process
#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum UpdateState {
    Idle,
    Checking,
    Available(UpdateInfo),
    Downloading { progress: u8 },
    Applying,
    ReadyToRestart,
    Error { message: String },
}

impl Default for UpdateState {
    fn default() -> Self {
        Self::Idle
    }
}

/// Information about an available update
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UpdateInfo {
    pub current_version: String,
    pub new_version: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub release_notes: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub size: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub min_version: Option<String>,
}

/// Information about a DMG for a specific architecture
#[derive(Debug, Clone, Deserialize)]
pub struct DmgInfo {
    pub key: String,
    pub size: Option<u64>,
}

/// Manifest fetched from S3 latest.json
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateManifest {
    pub version: String,
    /// Architecture-specific DMG for Apple Silicon (arm64)
    #[serde(default)]
    pub dmg_arm64: Option<DmgInfo>,
    /// Architecture-specific DMG for Intel (x86_64)
    #[serde(default)]
    pub dmg_intel: Option<DmgInfo>,
    /// Legacy field for backward compatibility (defaults to arm64)
    #[serde(default)]
    pub dmg_key: Option<String>,
    #[serde(default)]
    pub size: Option<u64>,
    #[serde(default)]
    pub release_notes: Option<String>,
    #[serde(default)]
    pub min_version: Option<String>,
}

impl UpdateManifest {
    /// Get the DMG key for the current architecture
    pub fn dmg_key_for_arch(&self) -> Option<String> {
        match std::env::consts::ARCH {
            "aarch64" => {
                // Apple Silicon - prefer dmg_arm64, fallback to dmg_key
                self.dmg_arm64
                    .as_ref()
                    .map(|d| d.key.clone())
                    .or_else(|| self.dmg_key.clone())
            }
            "x86_64" => {
                // Intel - prefer dmg_intel, fallback to dmg_key
                self.dmg_intel
                    .as_ref()
                    .map(|d| d.key.clone())
                    .or_else(|| self.dmg_key.clone())
            }
            _ => self.dmg_key.clone(),
        }
    }

    /// Get the DMG size for the current architecture
    pub fn dmg_size_for_arch(&self) -> Option<u64> {
        match std::env::consts::ARCH {
            "aarch64" => {
                // Apple Silicon - prefer dmg_arm64, fallback to size
                self.dmg_arm64
                    .as_ref()
                    .and_then(|d| d.size)
                    .or(self.size)
            }
            "x86_64" => {
                // Intel - prefer dmg_intel, fallback to size
                self.dmg_intel
                    .as_ref()
                    .and_then(|d| d.size)
                    .or(self.size)
            }
            _ => self.size,
        }
    }
}

/// Progress update during download/install
#[derive(Debug, Clone, Serialize)]
pub struct UpdateProgress {
    pub phase: String,
    pub progress: u8,
    pub message: String,
}

/// Manages the update process
pub struct Updater {
    client: Client,
    state: Arc<RwLock<UpdateState>>,
    manifest: Arc<RwLock<Option<UpdateManifest>>>,
}

impl Updater {
    /// Create a new Updater instance
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(UPDATE_CHECK_TIMEOUT_SECS))
            .build()
            .expect("Failed to create HTTP client");

        Self {
            client,
            state: Arc::new(RwLock::new(UpdateState::Idle)),
            manifest: Arc::new(RwLock::new(None)),
        }
    }

    /// Get current update state
    pub fn state(&self) -> UpdateState {
        self.state.read().clone()
    }

    /// Set update state
    fn set_state(&self, state: UpdateState) {
        *self.state.write() = state;
    }

    /// Check for available updates
    pub async fn check_for_updates(&self) -> Result<Option<UpdateInfo>, UpdateError> {
        self.set_state(UpdateState::Checking);

        let manifest_url = format!("{}/{}/latest.json", UPDATE_BASE_URL, UPDATE_PREFIX);
        debug!("Checking for updates at: {}", manifest_url);

        let response = match self.client.get(&manifest_url).send().await {
            Ok(r) => r,
            Err(e) => {
                let msg = format!("Failed to fetch update manifest: {}", e);
                warn!("{}", msg);
                self.set_state(UpdateState::Error { message: msg.clone() });
                return Err(UpdateError::Network(e));
            }
        };

        if !response.status().is_success() {
            let msg = format!("Update check failed: HTTP {}", response.status());
            warn!("{}", msg);
            self.set_state(UpdateState::Error { message: msg.clone() });
            return Err(UpdateError::ManifestParse(msg));
        }

        let manifest: UpdateManifest = match response.json().await {
            Ok(m) => m,
            Err(e) => {
                let msg = format!("Failed to parse update manifest: {}", e);
                warn!("{}", msg);
                self.set_state(UpdateState::Error { message: msg.clone() });
                return Err(UpdateError::ManifestParse(msg));
            }
        };

        let dmg_key = manifest.dmg_key_for_arch();
        debug!(
            "Manifest: version={}, dmg_key={:?}, arch={}",
            manifest.version,
            dmg_key,
            std::env::consts::ARCH
        );

        // Parse versions for comparison
        let current = Version::parse(VERSION)?;
        let latest = Version::parse(&manifest.version)?;

        if latest > current {
            // Check minimum version requirement if specified
            if let Some(ref min_ver) = manifest.min_version {
                let min = Version::parse(min_ver)?;
                if current < min {
                    info!(
                        "Update {} available but requires minimum version {} (current: {})",
                        manifest.version, min_ver, VERSION
                    );
                }
            }

            let info = UpdateInfo {
                current_version: VERSION.to_string(),
                new_version: manifest.version.clone(),
                release_notes: manifest.release_notes.clone(),
                size: manifest.dmg_size_for_arch(),
                min_version: manifest.min_version.clone(),
            };

            info!(
                "Update available: {} -> {} (size: {:?})",
                VERSION, manifest.version, manifest.size
            );

            // Store manifest for download
            *self.manifest.write() = Some(manifest);
            self.set_state(UpdateState::Available(info.clone()));

            Ok(Some(info))
        } else {
            info!("Already on latest version: {}", VERSION);
            self.set_state(UpdateState::Idle);
            Ok(None)
        }
    }

    /// Download and apply the update
    pub async fn apply_update(
        &self,
        progress_tx: Option<mpsc::Sender<UpdateProgress>>,
    ) -> Result<(), UpdateError> {
        let manifest = {
            let guard = self.manifest.read();
            guard.clone().ok_or(UpdateError::ManifestParse(
                "No update manifest available".to_string(),
            ))?
        };

        // Download DMG
        let dmg_path = self.download_update(&manifest, progress_tx.clone()).await?;

        // Apply update
        self.install_update(&dmg_path, progress_tx.clone()).await?;

        // Clean up DMG
        if let Err(e) = std::fs::remove_file(&dmg_path) {
            warn!("Failed to clean up DMG file: {}", e);
        }

        self.set_state(UpdateState::ReadyToRestart);

        if let Some(tx) = progress_tx {
            let _ = tx
                .send(UpdateProgress {
                    phase: "complete".to_string(),
                    progress: 100,
                    message: "Update ready. Restart to apply.".to_string(),
                })
                .await;
        }

        Ok(())
    }

    /// Download update DMG with progress reporting
    async fn download_update(
        &self,
        manifest: &UpdateManifest,
        progress_tx: Option<mpsc::Sender<UpdateProgress>>,
    ) -> Result<PathBuf, UpdateError> {
        let dmg_key = manifest.dmg_key_for_arch().ok_or_else(|| {
            UpdateError::ManifestParse(format!(
                "No DMG available for architecture: {}",
                std::env::consts::ARCH
            ))
        })?;
        let dmg_url = format!("{}/{}", UPDATE_BASE_URL, dmg_key);
        info!(
            "Downloading update from: {} (arch: {})",
            dmg_url,
            std::env::consts::ARCH
        );

        self.set_state(UpdateState::Downloading { progress: 0 });

        // Create a client without the timeout for downloads
        let download_client = Client::builder()
            .build()
            .expect("Failed to create download client");

        let response = download_client.get(&dmg_url).send().await?;

        if !response.status().is_success() {
            let msg = format!("Download failed: HTTP {}", response.status());
            self.set_state(UpdateState::Error { message: msg.clone() });
            return Err(UpdateError::Network(
                reqwest::Error::from(response.error_for_status().unwrap_err()),
            ));
        }

        let total_size = response
            .content_length()
            .or_else(|| manifest.dmg_size_for_arch())
            .unwrap_or(0);
        debug!("Download size: {} bytes", total_size);

        // Create temp file for download
        let temp_dir = std::env::temp_dir();
        let dmg_filename = dmg_key.split('/').last().unwrap_or("update.dmg");
        let dmg_path = temp_dir.join(dmg_filename);

        let mut file = std::fs::File::create(&dmg_path)?;
        let mut downloaded: u64 = 0;
        let mut last_progress: u8 = 0;

        let mut stream = response.bytes_stream();

        while let Some(chunk_result) = stream.next().await {
            let chunk = chunk_result?;
            file.write_all(&chunk)?;
            downloaded += chunk.len() as u64;

            let progress = if total_size > 0 {
                ((downloaded as f64 / total_size as f64) * 100.0) as u8
            } else {
                0
            };

            // Report progress every 1%
            if progress > last_progress {
                last_progress = progress;
                self.set_state(UpdateState::Downloading { progress });

                if let Some(ref tx) = progress_tx {
                    let _ = tx
                        .send(UpdateProgress {
                            phase: "downloading".to_string(),
                            progress,
                            message: format!(
                                "Downloaded {} of {} bytes",
                                downloaded, total_size
                            ),
                        })
                        .await;
                }
            }
        }

        file.sync_all()?;
        info!("Download complete: {}", dmg_path.display());

        Ok(dmg_path)
    }

    /// Install update from downloaded DMG
    async fn install_update(
        &self,
        dmg_path: &PathBuf,
        progress_tx: Option<mpsc::Sender<UpdateProgress>>,
    ) -> Result<(), UpdateError> {
        self.set_state(UpdateState::Applying);

        if let Some(ref tx) = progress_tx {
            let _ = tx
                .send(UpdateProgress {
                    phase: "applying".to_string(),
                    progress: 0,
                    message: "Mounting disk image...".to_string(),
                })
                .await;
        }

        // Mount DMG
        let mount_output = Command::new("hdiutil")
            .args(["attach", "-nobrowse", "-readonly", "-plist"])
            .arg(dmg_path)
            .output()?;

        if !mount_output.status.success() {
            let stderr = String::from_utf8_lossy(&mount_output.stderr);
            let msg = format!("Failed to mount DMG: {}", stderr);
            error!("{}", msg);
            self.set_state(UpdateState::Error { message: msg.clone() });
            return Err(UpdateError::MountFailed(msg));
        }

        // Parse mount point from plist output
        let stdout = String::from_utf8_lossy(&mount_output.stdout);
        let mount_point = Self::parse_mount_point(&stdout)?;
        info!("DMG mounted at: {}", mount_point);

        if let Some(ref tx) = progress_tx {
            let _ = tx
                .send(UpdateProgress {
                    phase: "applying".to_string(),
                    progress: 33,
                    message: "Finding app bundle...".to_string(),
                })
                .await;
        }

        // Find .app bundle in mounted DMG
        let app_source = Self::find_app_bundle(&mount_point)?;
        info!("Found app bundle: {}", app_source.display());

        // Get current app path
        let current_app = Self::get_current_app_path()?;
        info!("Current app path: {}", current_app.display());

        if let Some(ref tx) = progress_tx {
            let _ = tx
                .send(UpdateProgress {
                    phase: "applying".to_string(),
                    progress: 50,
                    message: "Copying new version...".to_string(),
                })
                .await;
        }

        // Copy new app over current app
        let copy_output = Command::new("cp")
            .args(["-R"])
            .arg(&app_source)
            .arg(current_app.parent().unwrap_or(&PathBuf::from("/Applications")))
            .output()?;

        if !copy_output.status.success() {
            let stderr = String::from_utf8_lossy(&copy_output.stderr);
            let msg = format!("Failed to copy app: {}", stderr);
            error!("{}", msg);
            // Try to unmount before returning error
            let _ = Command::new("hdiutil")
                .args(["detach", &mount_point])
                .output();
            self.set_state(UpdateState::Error { message: msg.clone() });
            return Err(UpdateError::CopyFailed(msg));
        }

        if let Some(ref tx) = progress_tx {
            let _ = tx
                .send(UpdateProgress {
                    phase: "applying".to_string(),
                    progress: 80,
                    message: "Unmounting disk image...".to_string(),
                })
                .await;
        }

        // Unmount DMG
        let unmount_output = Command::new("hdiutil")
            .args(["detach", &mount_point])
            .output()?;

        if !unmount_output.status.success() {
            let stderr = String::from_utf8_lossy(&unmount_output.stderr);
            warn!("Failed to unmount DMG: {}", stderr);
            // Don't fail the update for unmount issues
        }

        info!("Update applied successfully");

        if let Some(ref tx) = progress_tx {
            let _ = tx
                .send(UpdateProgress {
                    phase: "applying".to_string(),
                    progress: 100,
                    message: "Update applied successfully".to_string(),
                })
                .await;
        }

        Ok(())
    }

    /// Parse mount point from hdiutil plist output
    fn parse_mount_point(plist_output: &str) -> Result<String, UpdateError> {
        // Look for mount-point in the plist output
        // Format: <key>mount-point</key><string>/Volumes/Something</string>
        for line in plist_output.lines() {
            if line.contains("/Volumes/") {
                // Extract path from <string>/Volumes/...</string>
                if let Some(start) = line.find("/Volumes/") {
                    let rest = &line[start..];
                    if let Some(end) = rest.find("</") {
                        return Ok(rest[..end].to_string());
                    }
                    // If no closing tag on same line, take to end
                    return Ok(rest.trim_end_matches("</string>").to_string());
                }
            }
        }
        Err(UpdateError::MountFailed(
            "Could not find mount point in hdiutil output".to_string(),
        ))
    }

    /// Find .app bundle in mounted DMG
    fn find_app_bundle(mount_point: &str) -> Result<PathBuf, UpdateError> {
        let mount_path = PathBuf::from(mount_point);

        for entry in std::fs::read_dir(&mount_path)? {
            let entry = entry?;
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "app") {
                return Ok(path);
            }
        }

        Err(UpdateError::AppNotFound)
    }

    /// Get the path to the current running app bundle
    fn get_current_app_path() -> Result<PathBuf, UpdateError> {
        let exe = std::env::current_exe()?;
        // Traverse up from binary to find .app bundle
        // Typical structure: Foo.app/Contents/MacOS/binary
        let mut path = exe.as_path();
        for _ in 0..3 {
            if let Some(parent) = path.parent() {
                path = parent;
            }
        }

        if path.extension().map_or(false, |ext| ext == "app") {
            Ok(path.to_path_buf())
        } else {
            // Fallback: assume /Applications
            Ok(PathBuf::from("/Applications/MultiCam Relay.app"))
        }
    }

    /// Restart the application
    pub fn restart_app() -> Result<(), UpdateError> {
        let exe = std::env::current_exe()?;

        info!("Restarting application: {}", exe.display());

        // Spawn new process
        Command::new(&exe).spawn()?;

        // Exit current process
        std::process::exit(0);
    }
}

impl Default for Updater {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_version_comparison() {
        let v1 = Version::parse("0.1.0").unwrap();
        let v2 = Version::parse("0.2.0").unwrap();
        assert!(v2 > v1);
    }

    #[test]
    fn test_parse_mount_point() {
        let plist = r#"
            <dict>
                <key>mount-point</key>
                <string>/Volumes/MultiCam Relay</string>
            </dict>
        "#;
        let result = Updater::parse_mount_point(plist);
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "/Volumes/MultiCam Relay");
    }
}
