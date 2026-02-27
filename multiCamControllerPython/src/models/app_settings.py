"""Application settings with JSON persistence"""

import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AppSettings:
    """Application settings with persistence to JSON file"""

    # Video Processing
    reencode_to_av1: bool = True
    """Re-encode synced videos to AV1 format (smaller files, slower encoding)"""

    max_video_resolution: str = "720p"
    """Maximum video resolution: 'original', '1080p', '720p', or '480p'"""

    # S3 Upload
    upload_to_s3: bool = True
    """Upload processed videos to S3 cloud storage"""

    s3_bucket: str = "87c3e07f-3661-4489-829a-ddfa26943cb3"
    """S3 bucket name for cloud uploads (Production by default)"""

    upload_method: str = "direct"
    """Upload method: 'direct' (device → cloud) or 'download_and_process' (device → controller → cloud)"""

    upload_mode: str = "manual"
    """Upload mode: 'immediate' (upload right after processing) or 'manual' (queue for later). Only applies to download_and_process method."""

    delete_after_upload: bool = True
    """Delete local files after successful S3 upload"""

    # Recording
    recording_delay: float = 3.0
    """Delay in seconds before starting recording (for synchronization)"""

    # File Transfers
    max_download_retries: int = 3
    """Maximum number of retry attempts for failed downloads"""

    downloads_directory: str = ""
    """Custom downloads directory (empty string = use default ~/Downloads/multiCam)"""

    delete_zip_after_unpack: bool = True
    """Delete ZIP files after successfully unpacking them"""

    # Video Syncing
    last_video_sync_folder: Optional[str] = None
    """Last used folder for video syncing"""

    last_s3_sync_path: Optional[str] = None
    """Last used S3 URI for video syncing (e.g., s3://bucket-name/path/)"""

    s3_partial_download_mb: int = 20
    """Size of partial video download in MB (default: 20)"""

    # Metadata
    openweather_api_key: str = ""
    """OpenWeatherMap API key for location and weather data in metadata"""

    # Internal - settings file path
    _settings_path: Path = field(
        default_factory=lambda: Path.home() / ".multicam" / "settings.json",
        repr=False,
        compare=False,
    )

    def save(self) -> bool:
        """
        Save settings to JSON file.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict (exclude internal fields starting with '_')
            settings_dict = {k: v for k, v in asdict(self).items() if not k.startswith('_')}

            # Write to file
            with open(self._settings_path, "w") as f:
                json.dump(settings_dict, f, indent=2)

            logger.info(f"Settings saved to {self._settings_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False

    @classmethod
    def load(cls, settings_path: Optional[Path] = None) -> "AppSettings":
        """
        Load settings from JSON file.

        Args:
            settings_path: Optional custom path to settings file

        Returns:
            AppSettings instance with loaded values or defaults
        """
        path = settings_path or (Path.home() / ".multicam" / "settings.json")

        try:
            if not path.exists():
                logger.info(f"Settings file not found at {path}, using defaults")
                settings = cls(_settings_path=path)
                # Save default settings
                settings.save()
                return settings

            with open(path, "r") as f:
                settings_dict = json.load(f)

            # Create default instance to get default values
            defaults = cls(_settings_path=path)

            # Merge loaded settings with defaults (loaded settings take precedence)
            merged_settings = asdict(defaults)
            merged_settings.update(settings_dict)
            merged_settings['_settings_path'] = path  # Preserve the path

            # Create settings instance with merged values
            settings = cls(**merged_settings)

            logger.info(f"Settings loaded from {path}")
            return settings

        except Exception as e:
            logger.error(f"Failed to load settings: {e}, using defaults")
            return cls(_settings_path=path)

    def reset_to_defaults(self) -> bool:
        """
        Reset all settings to default values and save.

        Returns:
            True if successful, False otherwise
        """
        # Create a new default instance
        defaults = AppSettings(_settings_path=self._settings_path)

        # Copy all non-internal fields from defaults
        for field_name, field_value in asdict(defaults).items():
            if not field_name.startswith('_'):
                setattr(self, field_name, field_value)

        return self.save()

    def validate(self) -> tuple[bool, Optional[str]]:
        """
        Validate settings values.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate recording delay
        if not (1.0 <= self.recording_delay <= 10.0):
            return False, "Recording delay must be between 1.0 and 10.0 seconds"

        # Validate max download retries
        if not (0 <= self.max_download_retries <= 10):
            return False, "Max download retries must be between 0 and 10"

        # Validate max video resolution
        valid_resolutions = ["original", "1080p", "720p", "480p"]
        if self.max_video_resolution not in valid_resolutions:
            return False, f"Max video resolution must be one of: {', '.join(valid_resolutions)}"

        # Validate upload method
        valid_upload_methods = ["direct", "download_and_process"]
        if self.upload_method not in valid_upload_methods:
            return False, f"Upload method must be one of: {', '.join(valid_upload_methods)}"

        # Validate upload mode
        valid_upload_modes = ["immediate", "manual"]
        if self.upload_mode not in valid_upload_modes:
            return False, f"Upload mode must be one of: {', '.join(valid_upload_modes)}"

        # Validate S3 bucket
        from utils.constants import S3_BUCKET_OPTIONS
        valid_buckets = list(S3_BUCKET_OPTIONS.values())
        if self.s3_bucket not in valid_buckets:
            return False, f"S3 bucket must be one of the configured buckets"

        # Validate downloads directory (if set, check if it exists or can be created)
        if self.downloads_directory:
            try:
                downloads_path = Path(self.downloads_directory)
                # Try to create it if it doesn't exist
                downloads_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return False, f"Invalid downloads directory: {e}"

        return True, None

    def __str__(self) -> str:
        """String representation of settings"""
        return (
            f"AppSettings(\n"
            f"  reencode_to_av1={self.reencode_to_av1},\n"
            f"  max_video_resolution={self.max_video_resolution},\n"
            f"  upload_to_s3={self.upload_to_s3},\n"
            f"  s3_bucket={self.s3_bucket},\n"
            f"  upload_method={self.upload_method},\n"
            f"  upload_mode={self.upload_mode},\n"
            f"  delete_after_upload={self.delete_after_upload},\n"
            f"  recording_delay={self.recording_delay}s,\n"
            f"  max_download_retries={self.max_download_retries},\n"
            f"  downloads_directory={self.downloads_directory or 'default'},\n"
            f"  delete_zip_after_unpack={self.delete_zip_after_unpack},\n"
            f"  last_video_sync_folder={self.last_video_sync_folder or 'none'},\n"
            f"  last_s3_sync_path={self.last_s3_sync_path or 'none'},\n"
            f"  s3_partial_download_mb={self.s3_partial_download_mb},\n"
            f"  openweather_api_key={'***' if self.openweather_api_key else 'none'}\n"
            f")"
        )
