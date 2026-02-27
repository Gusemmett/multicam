//! URL scheme handler for `multicamrelay://` URLs
//!
//! Parses URLs passed as launch arguments when the app is opened via custom URL scheme.
//!
//! Supported URL formats:
//! - `multicamrelay://launch` - Simple launch, no parameters
//! - `multicamrelay://connect?session=abc123&callback=https://...` - Launch with session info

use percent_encoding::percent_decode_str;
use std::collections::HashMap;

/// Parameters parsed from a `multicamrelay://` URL
#[derive(Debug, Default)]
pub struct UrlParams {
    /// The host/command portion of the URL (e.g., "launch", "connect")
    pub command: String,
    /// Query parameters as key-value pairs
    pub params: HashMap<String, String>,
}

impl UrlParams {
    /// Check if this represents a valid multicam URL that was parsed
    #[allow(dead_code)]
    pub fn is_valid(&self) -> bool {
        !self.command.is_empty()
    }

    /// Get a parameter value by key
    pub fn get(&self, key: &str) -> Option<&str> {
        self.params.get(key).map(|s| s.as_str())
    }

    /// Get the session ID if present
    pub fn session(&self) -> Option<&str> {
        self.get("session")
    }

    /// Get the callback URL if present
    pub fn callback(&self) -> Option<&str> {
        self.get("callback")
    }
}

/// Parse command line arguments to extract `multicamrelay://` URL parameters
///
/// On macOS, when an app is launched via URL scheme, the URL is passed as a command line argument.
/// This function finds and parses that URL.
pub fn parse_launch_url(args: &[String]) -> Option<UrlParams> {
    // Find the multicamrelay:// URL in the arguments
    let url = args.iter().find(|arg| arg.starts_with("multicamrelay://"))?;

    parse_multicam_url(url)
}

/// Parse a `multicamrelay://` URL into its components
pub fn parse_multicam_url(url: &str) -> Option<UrlParams> {
    // Remove the scheme prefix
    let without_scheme = url.strip_prefix("multicamrelay://")?;

    // Split into path and query
    let (path, query) = match without_scheme.find('?') {
        Some(idx) => (&without_scheme[..idx], Some(&without_scheme[idx + 1..])),
        None => (without_scheme, None),
    };

    // The command is the path (possibly empty)
    let command = path.trim_matches('/').to_string();

    // Parse query parameters
    let params = query
        .map(parse_query_string)
        .unwrap_or_default();

    Some(UrlParams { command, params })
}

/// Parse a query string into key-value pairs
fn parse_query_string(query: &str) -> HashMap<String, String> {
    let mut params = HashMap::new();

    for pair in query.split('&') {
        if let Some((key, value)) = pair.split_once('=') {
            // URL-decode both key and value
            let decoded_key = percent_decode_str(key)
                .decode_utf8_lossy()
                .into_owned();
            let decoded_value = percent_decode_str(value)
                .decode_utf8_lossy()
                .into_owned();
            params.insert(decoded_key, decoded_value);
        }
    }

    params
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_launch() {
        let params = parse_multicam_url("multicamrelay://launch").unwrap();
        assert_eq!(params.command, "launch");
        assert!(params.params.is_empty());
    }

    #[test]
    fn test_parse_connect_with_params() {
        let params = parse_multicam_url("multicamrelay://connect?session=abc123&callback=https://example.com").unwrap();
        assert_eq!(params.command, "connect");
        assert_eq!(params.session(), Some("abc123"));
        assert_eq!(params.callback(), Some("https://example.com"));
    }

    #[test]
    fn test_parse_encoded_params() {
        let params = parse_multicam_url("multicamrelay://connect?callback=https%3A%2F%2Fexample.com%2Fpath").unwrap();
        assert_eq!(params.callback(), Some("https://example.com/path"));
    }

    #[test]
    fn test_parse_launch_url_from_args() {
        let args = vec![
            "/Applications/MultiCam Relay.app/Contents/MacOS/multicam-relay".to_string(),
            "multicamrelay://connect?session=test123".to_string(),
        ];
        let params = parse_launch_url(&args).unwrap();
        assert_eq!(params.command, "connect");
        assert_eq!(params.session(), Some("test123"));
    }

    #[test]
    fn test_parse_no_multicam_url() {
        let args = vec![
            "/Applications/MultiCam Relay.app/Contents/MacOS/multicam-relay".to_string(),
        ];
        assert!(parse_launch_url(&args).is_none());
    }
}
