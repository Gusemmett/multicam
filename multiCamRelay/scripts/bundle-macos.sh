#!/bin/bash
# Bundle MultiCam Relay as a macOS .app bundle
#
# Usage: ./scripts/bundle-macos.sh [--debug]
#
# Options:
#   --debug    Build debug version instead of release
#
# Environment variables:
#   ARCH              - Target architecture: arm64, intel, or native (default: native)
#   CODESIGN_IDENTITY - Developer ID certificate name for signing (optional)
#                       Example: "Developer ID Application: Your Name (TEAMID)"
#                       If not set, auto-detects from keychain or uses ad-hoc signing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APP_NAME="MultiCam Relay"
BUNDLE_NAME="MultiCam Relay.app"
BINARY_NAME="multicam-relay"
ENTITLEMENTS="$PROJECT_DIR/assets/multicam-relay.entitlements"

# Parse ARCH environment variable
ARCH="${ARCH:-native}"
case "$ARCH" in
    arm64)
        RUST_TARGET="aarch64-apple-darwin"
        echo "Building for Apple Silicon (arm64)..."
        ;;
    intel)
        RUST_TARGET="x86_64-apple-darwin"
        echo "Building for Intel (x86_64)..."
        ;;
    native|"")
        RUST_TARGET=""
        echo "Building for native architecture..."
        ;;
    *)
        echo "Error: Unknown architecture '$ARCH'. Use 'arm64', 'intel', or 'native'."
        exit 1
        ;;
esac

# Parse arguments
BUILD_TYPE="release"
CARGO_FLAGS="--release"
if [[ "$1" == "--debug" ]]; then
    BUILD_TYPE="debug"
    CARGO_FLAGS=""
    echo "Building debug version..."
else
    echo "Building release version..."
fi

# Add target flag if cross-compiling
if [[ -n "$RUST_TARGET" ]]; then
    CARGO_FLAGS="$CARGO_FLAGS --target $RUST_TARGET"
    TARGET_DIR="$PROJECT_DIR/target/$RUST_TARGET/$BUILD_TYPE"
else
    TARGET_DIR="$PROJECT_DIR/target/$BUILD_TYPE"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

cd "$PROJECT_DIR"

# Step 1: Build the binary
echo -e "${YELLOW}Step 1: Building binary...${NC}"
cargo build $CARGO_FLAGS

BINARY_PATH="$TARGET_DIR/$BINARY_NAME"
if [[ ! -f "$BINARY_PATH" ]]; then
    echo -e "${RED}Error: Binary not found at $BINARY_PATH${NC}"
    exit 1
fi
echo -e "${GREEN}Binary built successfully${NC}"

# Step 2: Create .app bundle structure
echo -e "${YELLOW}Step 2: Creating .app bundle structure...${NC}"
BUNDLE_DIR="$TARGET_DIR/$BUNDLE_NAME"
CONTENTS_DIR="$BUNDLE_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

# Clean up old bundle if exists
rm -rf "$BUNDLE_DIR"

# Create directories
mkdir -p "$MACOS_DIR"
mkdir -p "$RESOURCES_DIR"

echo -e "${GREEN}Bundle structure created${NC}"

# Step 3: Copy binary
echo -e "${YELLOW}Step 3: Copying binary...${NC}"
cp "$BINARY_PATH" "$MACOS_DIR/$BINARY_NAME"
chmod +x "$MACOS_DIR/$BINARY_NAME"
echo -e "${GREEN}Binary copied${NC}"

# Step 4: Copy Info.plist
echo -e "${YELLOW}Step 4: Copying Info.plist...${NC}"
if [[ -f "$PROJECT_DIR/assets/Info.plist" ]]; then
    cp "$PROJECT_DIR/assets/Info.plist" "$CONTENTS_DIR/Info.plist"
    echo -e "${GREEN}Info.plist copied${NC}"
else
    echo -e "${RED}Error: Info.plist not found at assets/Info.plist${NC}"
    exit 1
fi

# Step 5: Copy icon if exists
echo -e "${YELLOW}Step 5: Checking for icon...${NC}"
if [[ -f "$PROJECT_DIR/assets/AppIcon.icns" ]]; then
    cp "$PROJECT_DIR/assets/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
    echo -e "${GREEN}Icon copied${NC}"
else
    echo -e "${YELLOW}No icon found at assets/AppIcon.icns (optional)${NC}"
fi

# Step 6: Create PkgInfo
echo -e "${YELLOW}Step 6: Creating PkgInfo...${NC}"
echo -n "APPL????" > "$CONTENTS_DIR/PkgInfo"
echo -e "${GREEN}PkgInfo created${NC}"

# Step 7: Determine signing identity
echo -e "${YELLOW}Step 7: Signing app...${NC}"

# Auto-detect Developer ID if not provided
if [[ -z "$CODESIGN_IDENTITY" ]]; then
    echo "Looking for Developer ID Application certificate in keychain..."
    CODESIGN_IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
        | awk -F\" '/Developer ID Application/ {print $2; exit}')" || true
fi

if [[ -n "$CODESIGN_IDENTITY" ]]; then
    echo "Signing with: $CODESIGN_IDENTITY"

    # Check if entitlements file exists
    if [[ ! -f "$ENTITLEMENTS" ]]; then
        echo -e "${RED}Error: Entitlements file not found at $ENTITLEMENTS${NC}"
        exit 1
    fi

    # Sign with Developer ID for distribution
    # --options runtime enables Hardened Runtime (required for notarization)
    # --timestamp adds secure timestamp (required for notarization)
    # --entitlements specifies the entitlements file
    codesign --force --deep \
        --sign "$CODESIGN_IDENTITY" \
        --options runtime \
        --timestamp \
        --entitlements "$ENTITLEMENTS" \
        "$BUNDLE_DIR"

    echo -e "${GREEN}App signed with Developer ID${NC}"

    # Verify the signature
    echo -e "${YELLOW}Verifying signature...${NC}"
    codesign --verify --deep --strict --verbose=2 "$BUNDLE_DIR"
    echo -e "${GREEN}Signature verified${NC}"

    SIGNED_WITH_DEVELOPER_ID=true
else
    echo "No Developer ID found, using ad-hoc signing (local development only)"
    codesign --force --deep --sign - "$BUNDLE_DIR" 2>/dev/null || {
        echo -e "${YELLOW}Warning: Code signing failed (may need Xcode command line tools)${NC}"
    }
    echo -e "${GREEN}App signed (ad-hoc)${NC}"
    SIGNED_WITH_DEVELOPER_ID=false
fi

# Calculate sizes
BINARY_SIZE=$(du -h "$MACOS_DIR/$BINARY_NAME" | cut -f1)
BUNDLE_SIZE=$(du -sh "$BUNDLE_DIR" | cut -f1)

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Bundle created successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Location: $BUNDLE_DIR"
echo "Binary size: $BINARY_SIZE"
echo "Bundle size: $BUNDLE_SIZE"
echo ""

if [[ "$SIGNED_WITH_DEVELOPER_ID" == true ]]; then
    echo "Signed with: $CODESIGN_IDENTITY"
    echo ""
    echo "Next steps for distribution:"
    echo "  1. Notarize: NOTARYTOOL_PROFILE=\"...\" make notarize"
    echo "  2. Create DMG: make dmg"
else
    echo "Signed with: ad-hoc (development only)"
    echo ""
    echo "For distribution, ensure you have a Developer ID certificate in your keychain."
    echo "Then rebuild: make bundle-macos"
fi
echo ""
echo "To install locally:"
echo "  cp -r \"$BUNDLE_DIR\" /Applications/"
echo ""
echo "To test protocol handler:"
echo "  open multicamrelay://launch"
echo ""
echo "To run directly:"
echo "  open \"$BUNDLE_DIR\""
