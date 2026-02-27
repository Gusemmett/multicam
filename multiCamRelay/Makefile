# MultiCam Relay Makefile
#
# Usage:
#   make build          - Build release binary
#   make build-debug    - Build debug binary
#   make bundle-macos   - Create macOS .app bundle (release, native arch)
#   make bundle-debug   - Create macOS .app bundle (debug)
#   make run            - Run the relay
#   make test           - Run tests
#   make clean          - Clean build artifacts
#   make install        - Install to /Applications (macOS)
#
# Distribution targets (require Apple Developer Program membership):
#   make setup-targets  - Install Rust cross-compilation targets
#   make bundle-arm64   - Build and bundle for Apple Silicon
#   make bundle-intel   - Build and bundle for Intel
#   make notarize-arm64 - Notarize arm64 app bundle
#   make notarize-intel - Notarize Intel app bundle
#   make dmg-arm64      - Create arm64 DMG
#   make dmg-intel      - Create Intel DMG
#   make sign           - Sign with Developer ID (auto-detected from keychain)
#   make notarize       - Notarize the app bundle (native arch)
#   make dmg            - Create distributable DMG (native arch)
#   make notarize-dmg   - Notarize an existing DMG
#   make release        - Bump version, build both archs, sign, notarize, create DMGs
#   make upload         - Upload DMGs to S3 and update latest.json
#
# Version management:
#   make bump           - Bump patch version (0.1.0 -> 0.1.1)
#   make bump-minor     - Bump minor version (0.1.0 -> 0.2.0)
#   make bump-major     - Bump major version (0.1.0 -> 1.0.0)
#
# Environment variables:
#   CODESIGN_IDENTITY  - Developer ID cert (auto-detected from keychain if not set)
#   NOTARYTOOL_PROFILE - Keychain profile for notarization (default: multiCamControllerNotary)

.PHONY: build build-debug bundle-macos bundle-debug run test clean install help
.PHONY: setup-targets bundle-arm64 bundle-intel notarize-arm64 notarize-intel dmg-arm64 dmg-intel
.PHONY: sign notarize dmg notarize-dmg release upload
.PHONY: bump bump-minor bump-major version

# Default target
help:
	@echo "MultiCam Relay Build Tasks"
	@echo ""
	@echo "Development:"
	@echo "  make build          - Build release binary"
	@echo "  make build-debug    - Build debug binary"
	@echo "  make bundle-macos   - Create macOS .app bundle (release, native arch)"
	@echo "  make bundle-debug   - Create macOS .app bundle (debug)"
	@echo "  make run            - Run the relay (debug mode)"
	@echo "  make run-release    - Run the relay (release mode)"
	@echo "  make test           - Run tests"
	@echo "  make clean          - Clean build artifacts"
	@echo "  make install        - Install to /Applications (macOS)"
	@echo ""
	@echo "Distribution (requires Apple Developer Program):"
	@echo "  make setup-targets  - Install Rust cross-compilation targets"
	@echo "  make bundle-arm64   - Build and bundle for Apple Silicon"
	@echo "  make bundle-intel   - Build and bundle for Intel"
	@echo "  make notarize-arm64 - Notarize arm64 app bundle"
	@echo "  make notarize-intel - Notarize Intel app bundle"
	@echo "  make dmg-arm64      - Create arm64 DMG"
	@echo "  make dmg-intel      - Create Intel DMG"
	@echo "  make sign           - Build and sign with Developer ID (native arch)"
	@echo "  make notarize       - Notarize the app bundle (native arch)"
	@echo "  make dmg            - Create distributable DMG (native arch)"
	@echo "  make notarize-dmg   - Notarize an existing DMG"
	@echo "  make release        - Bump version + full dual-arch release pipeline"
	@echo "  make upload         - Upload DMGs to S3"
	@echo ""
	@echo "Version management:"
	@echo "  make version        - Show current version"
	@echo "  make bump           - Bump patch version (0.1.0 -> 0.1.1)"
	@echo "  make bump-minor     - Bump minor version (0.1.0 -> 0.2.0)"
	@echo "  make bump-major     - Bump major version (0.1.0 -> 1.0.0)"
	@echo ""
	@echo "Environment variables:"
	@echo "  CODESIGN_IDENTITY  - Developer ID cert (auto-detected if not set)"
	@echo "  NOTARYTOOL_PROFILE - Keychain profile (default: multiCamControllerNotary)"
	@echo ""

# =============================================================================
# Version management
# =============================================================================

version:
	@cat VERSION

bump:
	./scripts/bump-version.sh patch

bump-minor:
	./scripts/bump-version.sh minor

bump-major:
	./scripts/bump-version.sh major

# =============================================================================
# Build targets
# =============================================================================

build:
	cargo build --release

build-debug:
	cargo build

# Setup cross-compilation targets
setup-targets:
	rustup target add aarch64-apple-darwin x86_64-apple-darwin

# Bundle targets (auto-detects Developer ID from keychain)
bundle-macos: build
	./scripts/bundle-macos.sh

bundle-debug: build-debug
	./scripts/bundle-macos.sh --debug

# Architecture-specific bundle targets
bundle-arm64:
	ARCH=arm64 ./scripts/bundle-macos.sh

bundle-intel:
	ARCH=intel ./scripts/bundle-macos.sh

# Run targets
run:
	cargo run

run-release:
	cargo run --release

# Test target
test:
	cargo test

# Clean target
clean:
	cargo clean

# Install to /Applications (macOS only)
install: bundle-macos
	@echo "Installing to /Applications..."
	@rm -rf "/Applications/MultiCam Relay.app"
	@cp -r "target/release/MultiCam Relay.app" /Applications/
	@echo "Installed to /Applications/MultiCam Relay.app"
	@echo ""
	@echo "Test with: open multicamrelay://launch"

# =============================================================================
# Distribution targets
# =============================================================================

# Sign the app with Developer ID (auto-detects from keychain)
# Same as bundle-macos but makes intent clear
sign: bundle-macos

# Notarize the app bundle (uses multiCamControllerNotary by default)
notarize:
	./scripts/notarize.sh "target/release/MultiCam Relay.app"

# Notarize architecture-specific app bundles
notarize-arm64:
	./scripts/notarize.sh "target/aarch64-apple-darwin/release/MultiCam Relay.app"

notarize-intel:
	./scripts/notarize.sh "target/x86_64-apple-darwin/release/MultiCam Relay.app"

# Create DMG (signs with Developer ID if available)
dmg:
	./scripts/create-dmg.sh

# Create architecture-specific DMGs
dmg-arm64:
	ARCH=arm64 ./scripts/create-dmg.sh

dmg-intel:
	ARCH=intel ./scripts/create-dmg.sh

# Notarize an existing DMG (uses multiCamControllerNotary by default)
notarize-dmg:
	@VERSION=$$(cat VERSION | tr -d '[:space:]'); \
	./scripts/notarize.sh "target/release/MultiCam-Relay-$$VERSION.dmg"

# Notarize architecture-specific DMGs
notarize-dmg-arm64:
	@VERSION=$$(cat VERSION | tr -d '[:space:]'); \
	./scripts/notarize.sh "target/aarch64-apple-darwin/release/MultiCam-Relay-$$VERSION-arm64.dmg"

notarize-dmg-intel:
	@VERSION=$$(cat VERSION | tr -d '[:space:]'); \
	./scripts/notarize.sh "target/x86_64-apple-darwin/release/MultiCam-Relay-$$VERSION-intel.dmg"

# Full release pipeline: bump version, build both archs, sign, notarize, create DMGs
release: bump
	@echo ""
	@echo "========================================="
	@echo "Building and signing arm64 app..."
	@echo "========================================="
	$(MAKE) bundle-arm64
	@echo ""
	@echo "========================================="
	@echo "Notarizing arm64 app..."
	@echo "========================================="
	$(MAKE) notarize-arm64
	@echo ""
	@echo "========================================="
	@echo "Creating arm64 DMG..."
	@echo "========================================="
	$(MAKE) dmg-arm64
	@echo ""
	@echo "========================================="
	@echo "Building and signing Intel app..."
	@echo "========================================="
	$(MAKE) bundle-intel
	@echo ""
	@echo "========================================="
	@echo "Notarizing Intel app..."
	@echo "========================================="
	$(MAKE) notarize-intel
	@echo ""
	@echo "========================================="
	@echo "Creating Intel DMG..."
	@echo "========================================="
	$(MAKE) dmg-intel
	@echo ""
	@echo "========================================="
	@echo "Release complete!"
	@echo "========================================="
	@VERSION=$$(cat VERSION | tr -d '[:space:]'); \
	echo "Version: $$VERSION"; \
	echo "arm64 DMG: target/aarch64-apple-darwin/release/MultiCam-Relay-$$VERSION-arm64.dmg"; \
	echo "Intel DMG: target/x86_64-apple-darwin/release/MultiCam-Relay-$$VERSION-intel.dmg"

# Upload DMG to S3 and update latest.json
upload:
	./scripts/upload-s3.sh
