#!/bin/bash
# Notarize MultiCam Relay app with Apple
#
# Usage: ./scripts/notarize.sh <path-to-app-or-dmg>
#
# Arguments:
#   path-to-app-or-dmg - Path to the .app bundle or .dmg file to notarize (REQUIRED)
#
# Environment variables:
#   NOTARYTOOL_PROFILE - Name of the keychain-stored notarization profile (REQUIRED)
#                        Create with: xcrun notarytool store-credentials
#
# To create a notarization profile (one-time setup):
#   xcrun notarytool store-credentials "multiCamRelayNotary" \
#     --apple-id "you@example.com" \
#     --team-id "ABCD1234EF" \
#     --password "xxxx-xxxx-xxxx-xxxx"
#
# Then set: export NOTARYTOOL_PROFILE="multiCamRelayNotary"
#
# Examples:
#   # Notarize arm64 app bundle:
#   ./scripts/notarize.sh "target/aarch64-apple-darwin/release/MultiCam Relay.app"
#
#   # Notarize Intel app bundle:
#   ./scripts/notarize.sh "target/x86_64-apple-darwin/release/MultiCam Relay.app"
#
#   # Notarize arm64 DMG:
#   ./scripts/notarize.sh "target/aarch64-apple-darwin/release/MultiCam-Relay-X.X.X-arm64.dmg"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default to multiCamControllerNotary if not set
NOTARYTOOL_PROFILE="${NOTARYTOOL_PROFILE:-multiCamControllerNotary}"

# Check that profile is set (should always be true now with default)
if [[ -z "$NOTARYTOOL_PROFILE" ]]; then
    echo -e "${RED}Error: NOTARYTOOL_PROFILE environment variable not set${NC}"
    echo ""
    echo "First, create a notarization profile (one-time setup):"
    echo "  xcrun notarytool store-credentials \"multiCamRelayNotary\" \\"
    echo "    --apple-id \"you@example.com\" \\"
    echo "    --team-id \"ABCD1234EF\" \\"
    echo "    --password \"xxxx-xxxx-xxxx-xxxx\""
    echo ""
    echo "Then set: export NOTARYTOOL_PROFILE=\"multiCamRelayNotary\""
    exit 1
fi

# Get the path to notarize (required argument)
if [[ -z "$1" ]]; then
    echo -e "${RED}Error: Path to app or DMG is required${NC}"
    echo ""
    echo "Usage: $0 <path-to-app-or-dmg>"
    echo ""
    echo "Examples:"
    echo "  # Notarize arm64 app:"
    echo "  $0 \"target/aarch64-apple-darwin/release/MultiCam Relay.app\""
    echo ""
    echo "  # Notarize Intel app:"
    echo "  $0 \"target/x86_64-apple-darwin/release/MultiCam Relay.app\""
    echo ""
    echo "  # Notarize arm64 DMG:"
    echo "  $0 \"target/aarch64-apple-darwin/release/MultiCam-Relay-X.X.X-arm64.dmg\""
    exit 1
fi

TARGET_PATH="$1"

if [[ ! -e "$TARGET_PATH" ]]; then
    echo -e "${RED}Error: Target not found at $TARGET_PATH${NC}"
    echo "Run 'make bundle-arm64' or 'make bundle-intel' first to create the app bundle"
    exit 1
fi

echo -e "${YELLOW}Notarizing: $TARGET_PATH${NC}"
echo "Using profile: $NOTARYTOOL_PROFILE"

# Determine if this is an app or DMG
if [[ "$TARGET_PATH" == *.app ]]; then
    # For .app bundles, we need to create a zip for submission
    echo -e "${YELLOW}Creating zip archive for submission...${NC}"
    ZIP_PATH="$PROJECT_DIR/target/release/MultiCam Relay.zip"
    rm -f "$ZIP_PATH"
    /usr/bin/ditto -c -k --sequesterRsrc --keepParent "$TARGET_PATH" "$ZIP_PATH"
    SUBMIT_PATH="$ZIP_PATH"
    STAPLE_PATH="$TARGET_PATH"
elif [[ "$TARGET_PATH" == *.dmg ]]; then
    SUBMIT_PATH="$TARGET_PATH"
    STAPLE_PATH="$TARGET_PATH"
else
    echo -e "${RED}Error: Unknown file type. Must be .app or .dmg${NC}"
    exit 1
fi

# Submit for notarization
echo -e "${YELLOW}Submitting to Apple notarization service...${NC}"
echo "This may take several minutes..."

xcrun notarytool submit "$SUBMIT_PATH" \
    --keychain-profile "$NOTARYTOOL_PROFILE" \
    --wait

# Check the result
if [[ $? -ne 0 ]]; then
    echo -e "${RED}Notarization failed!${NC}"
    echo "Check the logs with: xcrun notarytool log <submission-id> --keychain-profile \"$NOTARYTOOL_PROFILE\""
    exit 1
fi

echo -e "${GREEN}Notarization successful!${NC}"

# Staple the ticket
echo -e "${YELLOW}Stapling notarization ticket...${NC}"
xcrun stapler staple "$STAPLE_PATH"

if [[ $? -ne 0 ]]; then
    echo -e "${RED}Stapling failed!${NC}"
    exit 1
fi

echo -e "${GREEN}Stapling successful!${NC}"

# Clean up zip if we created one
if [[ "$TARGET_PATH" == *.app ]] && [[ -f "$ZIP_PATH" ]]; then
    rm -f "$ZIP_PATH"
fi

# Verify the notarization
echo -e "${YELLOW}Verifying notarization...${NC}"
spctl --assess --type execute --verbose "$STAPLE_PATH" 2>&1 || true

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Notarization complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "The app is now notarized and can be distributed."
echo "Users will be able to open it without Gatekeeper warnings."
echo ""

if [[ "$TARGET_PATH" == *.app ]]; then
    echo "Next step: Create a DMG for distribution"
    echo "  make dmg"
fi
