//! Configuration constants for the relay

/// WebSocket/HTTP server port
pub const RELAY_PORT: u16 = 9847;

/// S3 bucket base URL for updates
pub const UPDATE_BASE_URL: &str = "https://auto-update-binaries.s3.us-east-1.amazonaws.com";

/// S3 key prefix for this application's updates
pub const UPDATE_PREFIX: &str = "mcr";

/// Timeout for checking updates (seconds)
pub const UPDATE_CHECK_TIMEOUT_SECS: u64 = 30;

/// Delay before startup update check (seconds)
pub const UPDATE_STARTUP_DELAY_SECS: u64 = 3;

/// mDNS service type for MultiCam devices
pub const MDNS_SERVICE_TYPE: &str = "_multicam._tcp.local.";

/// Interval between mDNS availability checks (seconds)
pub const MDNS_CHECK_INTERVAL_SECS: u64 = 10;

/// Timeout waiting for mDNS SearchStarted event (seconds)
pub const MDNS_CHECK_TIMEOUT_SECS: u64 = 2;

/// Default TCP port for device communication
#[allow(dead_code)]
pub const DEFAULT_DEVICE_PORT: u16 = 8080;

/// TCP connection timeout in seconds
pub const TCP_CONNECT_TIMEOUT_SECS: u64 = 5;

/// TCP read/write timeout in seconds
pub const TCP_IO_TIMEOUT_SECS: u64 = 60;

/// Application version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
