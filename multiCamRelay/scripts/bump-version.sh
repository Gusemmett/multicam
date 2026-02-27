#!/bin/bash
# Bump the version number
#
# Usage: ./scripts/bump-version.sh [major|minor|patch]
#
# Default is patch (0.1.0 -> 0.1.1)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$PROJECT_DIR/VERSION"
CARGO_TOML="$PROJECT_DIR/Cargo.toml"
INFO_PLIST="$PROJECT_DIR/assets/Info.plist"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get current version
if [[ ! -f "$VERSION_FILE" ]]; then
    echo "Error: VERSION file not found"
    exit 1
fi

CURRENT_VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')
echo "Current version: $CURRENT_VERSION"

# Parse version components
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Determine bump type
BUMP_TYPE="${1:-patch}"

case "$BUMP_TYPE" in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
    *)
        echo "Error: Unknown bump type '$BUMP_TYPE'"
        echo "Usage: $0 [major|minor|patch]"
        exit 1
        ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
echo -e "${YELLOW}Bumping to: $NEW_VERSION${NC}"

# Update VERSION file
echo "$NEW_VERSION" > "$VERSION_FILE"

# Update Cargo.toml
sed -i.bak "s/^version = \".*\"/version = \"$NEW_VERSION\"/" "$CARGO_TOML"
rm -f "$CARGO_TOML.bak"

# Update Info.plist
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $NEW_VERSION" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $NEW_VERSION" "$INFO_PLIST"

echo -e "${GREEN}Version updated to $NEW_VERSION${NC}"
echo ""
echo "Updated files:"
echo "  - VERSION"
echo "  - Cargo.toml"
echo "  - assets/Info.plist"
