#!/bin/bash
# apply_update.sh - Apply MultiCam Controller update after app quits
#
# This script is launched by the application before it quits.
# It waits for the app to exit, then replaces the app bundle with the new version.
#
# Arguments:
#   $1 - PID of the running app to wait for
#   $2 - Path to new .app (inside mounted DMG)
#   $3 - Path to current .app to replace
#   $4 - Path to mounted DMG (for cleanup)

set -e

APP_PID="$1"
NEW_APP="$2"
CURRENT_APP="$3"
DMG_MOUNT="$4"

LOG_FILE="/tmp/multicam_update.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log "Starting update process"
log "  APP_PID: $APP_PID"
log "  NEW_APP: $NEW_APP"
log "  CURRENT_APP: $CURRENT_APP"
log "  DMG_MOUNT: $DMG_MOUNT"

# Validate required arguments
if [ -z "$APP_PID" ] || [ -z "$NEW_APP" ] || [ -z "$CURRENT_APP" ]; then
    log "ERROR: Missing required arguments"
    exit 1
fi

# Wait for app to exit first (max 30 seconds)
log "Waiting for app (PID $APP_PID) to exit..."
for i in {1..60}; do
    if ! kill -0 "$APP_PID" 2>/dev/null; then
        log "App has exited"
        break
    fi
    sleep 0.5
done

# Double-check app has exited
if kill -0 "$APP_PID" 2>/dev/null; then
    log "WARNING: App still running after 30 seconds, proceeding anyway"
fi

# Give a moment for file handles to release
sleep 1

# Now validate the new app exists (after app has exited)
if [ ! -d "$NEW_APP" ]; then
    log "ERROR: New app not found at: $NEW_APP"
    log "Checking if DMG is still mounted..."
    ls -la "/Volumes/" >> "$LOG_FILE" 2>&1
    exit 1
fi

# Remove quarantine attribute from new app (critical for Gatekeeper)
log "Removing quarantine attribute from new app..."
xattr -cr "$NEW_APP" 2>/dev/null || true

# Backup current app
BACKUP_PATH="${CURRENT_APP}.bak"
if [ -d "$CURRENT_APP" ]; then
    log "Backing up current app to: $BACKUP_PATH"
    rm -rf "$BACKUP_PATH"
    mv "$CURRENT_APP" "$BACKUP_PATH"
fi

# Copy new app to destination
log "Installing new app..."
cp -R "$NEW_APP" "$CURRENT_APP"

if [ $? -ne 0 ]; then
    log "ERROR: Failed to copy new app"
    # Restore backup
    if [ -d "$BACKUP_PATH" ]; then
        log "Restoring backup..."
        mv "$BACKUP_PATH" "$CURRENT_APP"
    fi
    exit 1
fi

log "New app installed successfully"

# Remove quarantine from installed app as well
xattr -cr "$CURRENT_APP" 2>/dev/null || true

# Cleanup: Unmount DMG
if [ -n "$DMG_MOUNT" ] && [ -d "$DMG_MOUNT" ]; then
    log "Unmounting DMG: $DMG_MOUNT"
    hdiutil detach "$DMG_MOUNT" -quiet 2>/dev/null || true
fi

# Remove backup after successful update
if [ -d "$BACKUP_PATH" ]; then
    log "Removing backup"
    rm -rf "$BACKUP_PATH"
fi

# Clean up update cache
CACHE_DIR="$HOME/Library/Caches/com.multicam.controller/updates"
if [ -d "$CACHE_DIR" ]; then
    log "Cleaning update cache"
    rm -rf "$CACHE_DIR"
fi

# Launch new app
log "Launching updated app..."
open "$CURRENT_APP"

log "Update complete!"
exit 0
