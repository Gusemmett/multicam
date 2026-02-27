#!/usr/bin/env python3
"""
Upload a new release to S3 for auto-update distribution.

Usage:
    python scripts/upload_release.py path/to/MultiCam-Controller.dmg [--notes "Release notes"]

This script:
1. Reads the version from resources/VERSION
2. Uploads the DMG to S3 with a versioned filename
3. Updates latest.json with the new release info
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.constants import UPDATE_S3_BUCKET, UPDATE_S3_REGION

# S3 prefix for all update files
S3_PREFIX = "mcc"


def get_version() -> str:
    """Read version from VERSION file"""
    version_file = Path(__file__).parent.parent / "resources" / "VERSION"
    if not version_file.exists():
        raise FileNotFoundError(f"VERSION file not found at {version_file}")
    return version_file.read_text().strip()


def upload_release(dmg_path: str, release_notes: str = "", min_version: str = None):
    """Upload a release DMG to S3 and update latest.json"""

    dmg_file = Path(dmg_path)
    if not dmg_file.exists():
        raise FileNotFoundError(f"DMG file not found: {dmg_path}")

    version = get_version()
    dmg_filename = f"MultiCam-Controller-{version}.dmg"
    dmg_key = f"{S3_PREFIX}/{dmg_filename}"
    file_size = dmg_file.stat().st_size

    print(f"Uploading release:")
    print(f"  Version: {version}")
    print(f"  DMG: {dmg_file.name}")
    print(f"  Size: {file_size / (1024*1024):.1f} MB")
    print(f"  Bucket: {UPDATE_S3_BUCKET}")
    print(f"  Region: {UPDATE_S3_REGION}")
    print()

    # Create S3 client
    s3 = boto3.client("s3", region_name=UPDATE_S3_REGION)

    # Upload DMG
    print(f"Uploading {dmg_key}...")
    try:
        s3.upload_file(
            str(dmg_file),
            UPDATE_S3_BUCKET,
            dmg_key,
            ExtraArgs={"ContentType": "application/x-apple-diskimage"}
        )
        print(f"  Uploaded successfully")
    except ClientError as e:
        raise RuntimeError(f"Failed to upload DMG: {e}")

    # Create latest.json
    latest_data = {
        "version": version,
        "dmg_key": dmg_key,
        "size": file_size,
        "release_notes": release_notes or f"MultiCam Controller {version}",
        "released_at": datetime.now(timezone.utc).isoformat(),
    }

    if min_version:
        latest_data["min_version"] = min_version

    # Upload latest.json
    latest_key = f"{S3_PREFIX}/latest.json"
    print(f"Updating {latest_key}...")
    try:
        s3.put_object(
            Bucket=UPDATE_S3_BUCKET,
            Key=latest_key,
            Body=json.dumps(latest_data, indent=2),
            ContentType="application/json"
        )
        print("  Updated successfully")
    except ClientError as e:
        raise RuntimeError(f"Failed to update latest.json: {e}")

    # Print public URLs
    base_url = f"https://{UPDATE_S3_BUCKET}.s3.{UPDATE_S3_REGION}.amazonaws.com"
    print()
    print("Release published!")
    print(f"  DMG URL: {base_url}/{dmg_key}")
    print(f"  Manifest: {base_url}/{latest_key}")
    print()
    print("latest.json contents:")
    print(json.dumps(latest_data, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Upload a MultiCam Controller release to S3"
    )
    parser.add_argument(
        "dmg_path",
        help="Path to the DMG file to upload"
    )
    parser.add_argument(
        "--notes", "-n",
        default="",
        help="Release notes (markdown supported)"
    )
    parser.add_argument(
        "--min-version", "-m",
        default=None,
        help="Minimum version required to update (optional)"
    )

    args = parser.parse_args()

    try:
        upload_release(args.dmg_path, args.notes, args.min_version)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
