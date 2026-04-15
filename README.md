# multicam

Monorepo for the MultiCam system.

- `multiCamCommon` — shared protocol (Swift, Java, Python, OpenAPI spec)
- `multiCamControllerMacos` — macOS controller app
- `multiCamControllerPython` — Python controller / server
- `multiCamIOS` — iOS camera client
- `multiCamAndroid` — Android camera client
- `multiCamRelay` — Rust relay service

AWS credentials and API keys must be supplied via environment variables or platform credential stores — never committed.
