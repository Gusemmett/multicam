#!/bin/bash
# Upload DMGs to S3 and update latest.json with dual-architecture support
#
# Usage: ./scripts/upload-s3.sh
#
# Uploads both arm64 and Intel DMGs and creates a latest.json with
# architecture-specific entries plus legacy fields for backward compatibility.
#
# Environment variables (optional):
#   S3_BUCKET - S3 bucket URI (default: s3://auto-update-binaries/mcr/)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$PROJECT_DIR/VERSION"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default S3 bucket
S3_BUCKET="${S3_BUCKET:-s3://auto-update-binaries/mcr/}"

# Ensure trailing slash
[[ "${S3_BUCKET}" != */ ]] && S3_BUCKET="${S3_BUCKET}/"

# Get version
if [[ ! -f "$VERSION_FILE" ]]; then
    echo -e "${RED}Error: VERSION file not found${NC}"
    exit 1
fi

VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')

# DMG paths for both architectures
DMG_NAME_ARM64="MultiCam-Relay-${VERSION}-arm64.dmg"
DMG_NAME_INTEL="MultiCam-Relay-${VERSION}-intel.dmg"
DMG_PATH_ARM64="$PROJECT_DIR/target/aarch64-apple-darwin/release/$DMG_NAME_ARM64"
DMG_PATH_INTEL="$PROJECT_DIR/target/x86_64-apple-darwin/release/$DMG_NAME_INTEL"

echo -e "${YELLOW}Uploading MultiCam Relay v$VERSION to S3${NC}"
echo "Bucket: $S3_BUCKET"

# Check AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI not found${NC}"
    echo "Install with: brew install awscli"
    exit 1
fi

# Check at least one DMG exists
HAS_ARM64=false
HAS_INTEL=false

if [[ -f "$DMG_PATH_ARM64" ]]; then
    HAS_ARM64=true
    echo -e "${GREEN}Found arm64 DMG: $DMG_PATH_ARM64${NC}"
fi

if [[ -f "$DMG_PATH_INTEL" ]]; then
    HAS_INTEL=true
    echo -e "${GREEN}Found Intel DMG: $DMG_PATH_INTEL${NC}"
fi

if [[ "$HAS_ARM64" == false && "$HAS_INTEL" == false ]]; then
    echo -e "${RED}Error: No DMG files found${NC}"
    echo "Expected locations:"
    echo "  $DMG_PATH_ARM64"
    echo "  $DMG_PATH_INTEL"
    echo ""
    echo "Run 'make release' first to create the DMGs"
    exit 1
fi

# Get current timestamp in ISO format
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.000000+00:00")

# S3 keys for the DMGs
DMG_KEY_ARM64="mcr/$DMG_NAME_ARM64"
DMG_KEY_INTEL="mcr/$DMG_NAME_INTEL"

# Upload arm64 DMG if it exists
if [[ "$HAS_ARM64" == true ]]; then
    echo -e "${YELLOW}Uploading arm64 DMG...${NC}"
    aws s3 cp "$DMG_PATH_ARM64" "${S3_BUCKET}${DMG_NAME_ARM64}"
    FILE_SIZE_ARM64=$(stat -f%z "$DMG_PATH_ARM64" 2>/dev/null || stat -c%s "$DMG_PATH_ARM64" 2>/dev/null)
    echo -e "${GREEN}arm64 DMG uploaded successfully${NC}"
fi

# Upload Intel DMG if it exists
if [[ "$HAS_INTEL" == true ]]; then
    echo -e "${YELLOW}Uploading Intel DMG...${NC}"
    aws s3 cp "$DMG_PATH_INTEL" "${S3_BUCKET}${DMG_NAME_INTEL}"
    FILE_SIZE_INTEL=$(stat -f%z "$DMG_PATH_INTEL" 2>/dev/null || stat -c%s "$DMG_PATH_INTEL" 2>/dev/null)
    echo -e "${GREEN}Intel DMG uploaded successfully${NC}"
fi

# Create latest.json with architecture-specific entries
echo -e "${YELLOW}Updating latest.json...${NC}"

# Build JSON parts based on available DMGs
DMG_ARM64_JSON=""
DMG_INTEL_JSON=""
LEGACY_DMG_KEY=""
LEGACY_SIZE=""

if [[ "$HAS_ARM64" == true ]]; then
    DMG_ARM64_JSON="\"dmg_arm64\": {
    \"key\": \"$DMG_KEY_ARM64\",
    \"size\": $FILE_SIZE_ARM64
  },"
    # Default legacy fields to arm64
    LEGACY_DMG_KEY="$DMG_KEY_ARM64"
    LEGACY_SIZE="$FILE_SIZE_ARM64"
fi

if [[ "$HAS_INTEL" == true ]]; then
    DMG_INTEL_JSON="\"dmg_intel\": {
    \"key\": \"$DMG_KEY_INTEL\",
    \"size\": $FILE_SIZE_INTEL
  },"
    # If no arm64, use Intel for legacy
    if [[ -z "$LEGACY_DMG_KEY" ]]; then
        LEGACY_DMG_KEY="$DMG_KEY_INTEL"
        LEGACY_SIZE="$FILE_SIZE_INTEL"
    fi
fi

LATEST_JSON=$(cat <<EOF
{
  "version": "$VERSION",
  $DMG_ARM64_JSON
  $DMG_INTEL_JSON
  "dmg_key": "$LEGACY_DMG_KEY",
  "size": $LEGACY_SIZE,
  "release_notes": "MultiCam Relay $VERSION",
  "released_at": "$TIMESTAMP"
}
EOF
)

# Write to temp file and upload
TEMP_JSON=$(mktemp)
echo "$LATEST_JSON" > "$TEMP_JSON"

aws s3 cp "$TEMP_JSON" "${S3_BUCKET}latest.json" --content-type "application/json"

rm -f "$TEMP_JSON"

echo -e "${GREEN}latest.json updated${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Upload complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
if [[ "$HAS_ARM64" == true ]]; then
    echo "arm64 DMG URL: ${S3_BUCKET}${DMG_NAME_ARM64}"
fi
if [[ "$HAS_INTEL" == true ]]; then
    echo "Intel DMG URL: ${S3_BUCKET}${DMG_NAME_INTEL}"
fi
echo "Latest JSON: ${S3_BUCKET}latest.json"
echo ""
echo "latest.json contents:"
echo "$LATEST_JSON"
