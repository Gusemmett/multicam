#!/bin/bash
# Create a distributable DMG for MultiCam Relay
#
# Usage: ./scripts/create-dmg.sh
#
# Environment variables (optional):
#   ARCH               - Target architecture: arm64, intel, or native (default: native)
#   CODESIGN_IDENTITY  - Developer ID certificate for signing the DMG (auto-detected)
#   NOTARYTOOL_PROFILE - Keychain profile for notarizing the DMG
#
# If notarization credentials are provided, the DMG will be notarized and stapled.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APP_NAME="MultiCam Relay"
BUNDLE_NAME="MultiCam Relay.app"
DMG_NAME="MultiCam-Relay"
VERSION=$(grep '^version' "$PROJECT_DIR/Cargo.toml" | head -1 | sed 's/.*"\(.*\)".*/\1/')

# Parse ARCH environment variable
ARCH="${ARCH:-native}"
case "$ARCH" in
    arm64)
        RUST_TARGET="aarch64-apple-darwin"
        ARCH_SUFFIX="-arm64"
        ;;
    intel)
        RUST_TARGET="x86_64-apple-darwin"
        ARCH_SUFFIX="-intel"
        ;;
    native|"")
        RUST_TARGET=""
        ARCH_SUFFIX=""
        ;;
    *)
        echo "Error: Unknown architecture '$ARCH'. Use 'arm64', 'intel', or 'native'."
        exit 1
        ;;
esac

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Paths - use target-specific directory if cross-compiling
if [[ -n "$RUST_TARGET" ]]; then
    TARGET_DIR="$PROJECT_DIR/target/$RUST_TARGET/release"
else
    TARGET_DIR="$PROJECT_DIR/target/release"
fi

APP_PATH="$TARGET_DIR/$BUNDLE_NAME"
DMG_PATH="$TARGET_DIR/${DMG_NAME}-${VERSION}${ARCH_SUFFIX}.dmg"
TEMP_DMG_PATH="$TARGET_DIR/${DMG_NAME}-temp.dmg"
MOUNT_DIR="/Volumes/$APP_NAME"

echo -e "${YELLOW}Creating DMG for $APP_NAME v$VERSION${ARCH_SUFFIX}${NC}"

# Check that the app bundle exists
if [[ ! -d "$APP_PATH" ]]; then
    echo -e "${RED}Error: App bundle not found at $APP_PATH${NC}"
    echo "Run 'make bundle-macos' first"
    exit 1
fi

# Check that the app is signed (at least ad-hoc)
echo -e "${YELLOW}Checking app signature...${NC}"
if ! codesign -v "$APP_PATH" 2>/dev/null; then
    echo -e "${RED}Error: App is not signed${NC}"
    echo "Run 'make bundle-macos' to sign the app first"
    exit 1
fi
echo -e "${GREEN}App signature verified${NC}"

# Clean up any existing DMG
rm -f "$DMG_PATH" "$TEMP_DMG_PATH"

# Unmount if already mounted
if [[ -d "$MOUNT_DIR" ]]; then
    echo -e "${YELLOW}Unmounting existing volume...${NC}"
    hdiutil detach "$MOUNT_DIR" -quiet -force 2>/dev/null || true
fi

# Calculate required size (app size + padding for symlink and filesystem overhead)
APP_SIZE_KB=$(du -sk "$APP_PATH" | cut -f1)
DMG_SIZE_KB=$((APP_SIZE_KB + 10240))  # Add 10MB padding

echo -e "${YELLOW}Creating temporary DMG (${DMG_SIZE_KB}KB)...${NC}"

# Create a temporary DMG
hdiutil create -srcfolder "$APP_PATH" \
    -volname "$APP_NAME" \
    -fs HFS+ \
    -fsargs "-c c=64,a=16,e=16" \
    -format UDRW \
    -size ${DMG_SIZE_KB}k \
    "$TEMP_DMG_PATH"

echo -e "${YELLOW}Mounting DMG...${NC}"

# Mount the DMG
DEVICE=$(hdiutil attach -readwrite -noverify -noautoopen "$TEMP_DMG_PATH" | \
    awk '/\/Volumes\// {print $1}' | head -1)

if [[ -z "$DEVICE" ]]; then
    echo -e "${RED}Error: Failed to mount DMG${NC}"
    exit 1
fi

echo "Mounted at $MOUNT_DIR (device: $DEVICE)"

# Add Applications symlink
echo -e "${YELLOW}Adding Applications symlink...${NC}"
ln -sf /Applications "$MOUNT_DIR/Applications"

# Wait for the system to sync
sync

# Unmount
echo -e "${YELLOW}Unmounting...${NC}"
hdiutil detach "$DEVICE" -quiet

# Convert to compressed, read-only DMG
echo -e "${YELLOW}Converting to compressed DMG...${NC}"
hdiutil convert "$TEMP_DMG_PATH" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$DMG_PATH"

# Clean up temp DMG
rm -f "$TEMP_DMG_PATH"

# Auto-detect signing identity if not provided
if [[ -z "$CODESIGN_IDENTITY" ]]; then
    CODESIGN_IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
        | awk -F\" '/Developer ID Application/ {print $2; exit}')" || true
fi

# Sign the DMG if we have a Developer ID
if [[ -n "$CODESIGN_IDENTITY" ]]; then
    echo -e "${YELLOW}Signing DMG...${NC}"
    codesign --force --sign "$CODESIGN_IDENTITY" --timestamp "$DMG_PATH"
    echo -e "${GREEN}DMG signed${NC}"
fi

# Calculate final size
DMG_SIZE=$(du -h "$DMG_PATH" | cut -f1)

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}DMG created successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Location: $DMG_PATH"
echo "Size: $DMG_SIZE"
echo ""

# Default to multiCamControllerNotary if not set
NOTARYTOOL_PROFILE="${NOTARYTOOL_PROFILE:-multiCamControllerNotary}"

# Check if we should notarize
if [[ -n "$NOTARYTOOL_PROFILE" ]]; then
    echo -e "${YELLOW}Notarizing DMG...${NC}"
    "$SCRIPT_DIR/notarize.sh" "$DMG_PATH"
else
    if [[ -n "$CODESIGN_IDENTITY" ]]; then
        echo "DMG is signed but not notarized."
        echo "To notarize, set NOTARYTOOL_PROFILE:"
        echo "  NOTARYTOOL_PROFILE=\"multiCamRelayNotary\" make notarize-dmg"
    else
        echo "DMG is unsigned (development only)."
        echo "For distribution, ensure you have a Developer ID certificate."
    fi
fi
echo ""
echo "To verify the DMG:"
echo "  spctl --assess --type open --context context:primary-signature --verbose \"$DMG_PATH\""
