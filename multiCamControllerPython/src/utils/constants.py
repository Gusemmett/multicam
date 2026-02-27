"""Application constants - Controller-specific constants only"""

# Re-export common constants for convenience
from multicam_common import (
    TCP_PORT,
    SERVICE_TYPE,
    NTP_SERVER,
    NTP_PORT,
    MAX_ACCEPTABLE_RTT,
    SYNC_DELAY,
    COMMAND_TIMEOUT,
    DOWNLOAD_CHUNK_SIZE,
)

# Legacy alias for backward compatibility
DEFAULT_PORT = TCP_PORT
CHUNK_SIZE = DOWNLOAD_CHUNK_SIZE

# Controller-specific constants
DISCOVERY_TIMEOUT = 10  # seconds
DOWNLOAD_STALL_TIMEOUT = 600.0  # seconds (10 minutes) - how long to wait for download chunks

# Paths
DOWNLOADS_DIR_NAME = "multiCam"

# S3
DEFAULT_S3_REGION = "us-east-1"

# S3 Buckets
S3_BUCKET_PROD = "87c3e07f-3661-4489-829a-ddfa26943cb3"
S3_BUCKET_DEV = "dev-9013c940-f317-47b6-9b6c-2d6cea2be587"

# S3 Auto-Update Bucket (public bucket for hosting DMG releases)
UPDATE_S3_BUCKET = "auto-update-binaries"
UPDATE_S3_REGION = "us-east-1"

S3_BUCKET_OPTIONS = {
    "Production": S3_BUCKET_PROD,
    "Development": S3_BUCKET_DEV,
}

S3_BUCKET_DISPLAY_NAMES = {
    S3_BUCKET_PROD: "Production",
    S3_BUCKET_DEV: "Development",
}

# IAM Role ARN for device uploads
MULTICAM_UPLOAD_ROLE_ARN = "arn:aws:iam::306783770680:role/MultiCamDeviceUploadRole"

# Video Resolution (Controller UI specific)
RESOLUTION_OPTIONS = ["original", "1080p", "720p", "480p"]
RESOLUTION_DIMENSIONS = {
    "original": None,
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "480p": (854, 480),
}
RESOLUTION_DISPLAY_NAMES = {
    "original": "Original (no limit)",
    "1080p": "1080p (1920x1080)",
    "720p": "720p (1280x720)",
    "480p": "480p (854x480)",
}

# Task options for data collection (value, display_name)
TASK_OPTIONS = [
    ("open_container", "open container (открыть холодильник)"),
    ("fold_towel", "fold towel (сложить полотенце)"),
    ("pick_bear", "pick bear (взять мишку)"),
    ("place_plate", "place plate (поставить тарелку)"),
    ("rearrange_coke", "rearrange coke (переставить кока-колу)"),
    ("sweep_trash", "sweep trash (подмести мусор)"),
    ("clean_table", "clean table (убрать стол)"),
    ("unplug_charger", "unplug charger (вытащить зарядку)"),
    ("pour_coke", "pour coke (налить кока-колу)"),
    ("pick_bread", "pick bread (взять хлеб)"),
    ("hotdog_in_ricecooker", "hotdog in ricecooker (хот-дог в рисоварку)"),
    ("hotdog_in_roaster", "hotdog in roaster (хот-дог в тостер)"),
    ("pick_lid", "pick lid (взять крышку)"),
    ("open_drawer", "open drawer (открыть ящик)"),
    ("open_roaster", "open roaster (открыть тостер)"),
    ("pick_cup", "pick cup (взять чашку)"),
    ("pick_pen", "pick pen (взять ручку)"),
    ("close_ricecooker", "close ricecooker (закрыть рисоварку)"),
    ("open_suitcase", "open suitcase (открыть чемодан)"),
    ("cover_beef", "cover beef (накрыть говядину)"),
    ("other", "other (другое)"),
    ("test", "test (тест)"),
]
