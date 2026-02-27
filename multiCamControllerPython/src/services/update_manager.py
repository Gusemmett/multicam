"""Application update management via S3"""

import json
import logging
import os
import sys
import subprocess
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional
from datetime import datetime

import requests
from packaging import version
from PySide6.QtCore import QObject, Signal as pyqtSignal, QThread

from models.update_info import ReleaseInfo, UpdateState, UpdateProgress
from utils.constants import UPDATE_S3_BUCKET, UPDATE_S3_REGION

logger = logging.getLogger(__name__)


class DownloadWorker(QThread):
    """Background worker for downloading updates"""

    progress = pyqtSignal(UpdateProgress)
    finished = pyqtSignal(str)  # Path to downloaded file
    error = pyqtSignal(str)  # Error message

    CHUNK_SIZE = 8192

    def __init__(self, url: str, destination: Path, expected_size: int, parent=None):
        super().__init__(parent)
        self.url = url
        self.destination = destination
        self.expected_size = expected_size
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the download"""
        self._cancelled = True

    def run(self):
        """Download the file with progress reporting"""
        try:
            self.destination.parent.mkdir(parents=True, exist_ok=True)

            response = requests.get(self.url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", self.expected_size))
            bytes_downloaded = 0
            start_time = time.time()

            with open(self.destination, "wb") as f:
                for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                    if self._cancelled:
                        logger.info("Download cancelled by user")
                        self.destination.unlink(missing_ok=True)
                        self.error.emit("Download cancelled")
                        return

                    if chunk:
                        f.write(chunk)
                        bytes_downloaded += len(chunk)

                        elapsed = time.time() - start_time
                        speed = bytes_downloaded / elapsed if elapsed > 0 else 0

                        progress = UpdateProgress(
                            bytes_downloaded=bytes_downloaded,
                            total_bytes=total_size,
                            download_speed=speed,
                        )
                        self.progress.emit(progress)

            # Verify file size
            actual_size = self.destination.stat().st_size
            if actual_size != total_size:
                self.destination.unlink(missing_ok=True)
                self.error.emit(
                    f"Download incomplete: got {actual_size} bytes, expected {total_size}"
                )
                return

            logger.info(f"Download complete: {self.destination}")
            self.finished.emit(str(self.destination))

        except requests.RequestException as e:
            logger.error(f"Download failed: {e}")
            self.destination.unlink(missing_ok=True)
            self.error.emit(f"Download failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            self.destination.unlink(missing_ok=True)
            self.error.emit(f"Download error: {e}")


class UpdateCheckWorker(QThread):
    """Background worker for checking updates"""

    update_found = pyqtSignal(object)  # ReleaseInfo or None
    check_failed = pyqtSignal(str)  # Error message

    def __init__(self, url: str, current_version: str, timeout: int = 30, parent=None):
        super().__init__(parent)
        self.url = url
        self.current_version = current_version
        self.timeout = timeout

    def run(self):
        """Check S3 for latest version"""
        try:
            logger.info(f"Fetching: {self.url}")
            response = requests.get(self.url, timeout=self.timeout)
            logger.info(f"Response status: {response.status_code}")

            if response.status_code == 404:
                logger.info("No latest.json found in S3 bucket")
                self.update_found.emit(None)
                return

            response.raise_for_status()
            data = response.json()
            logger.info(f"latest.json contents: {data}")

            # Parse version
            release_version = data.get("version", "")
            logger.info(f"Latest version from S3: {release_version}")

            # Compare versions
            try:
                current = version.parse(self.current_version)
                latest = version.parse(release_version)

                if latest <= current:
                    logger.info(
                        f"Already up to date (current: {current}, latest: {latest})"
                    )
                    self.update_found.emit(None)
                    return

                # Check minimum version requirement
                min_version_str = data.get("min_version")
                if min_version_str:
                    min_ver = version.parse(min_version_str)
                    if current < min_ver:
                        logger.warning(
                            f"Current version {current} is below minimum required {min_ver}"
                        )

            except version.InvalidVersion as e:
                logger.warning(f"Invalid version format: {e}")
                self.update_found.emit(None)
                return

            # Parse release date
            released_str = data.get("released_at", "")
            try:
                released_at = datetime.fromisoformat(released_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                released_at = datetime.now()

            # Build download URL
            dmg_key = data.get("dmg_key", "")
            # Get base URL from the latest.json URL
            base_url = self.url.rsplit("/", 2)[0]  # Remove /prefix/latest.json
            download_url = f"{base_url}/{dmg_key}"

            release = ReleaseInfo(
                version=release_version,
                release_notes=data.get("release_notes", f"Version {release_version}"),
                download_url=download_url,
                file_size=data.get("size", 0),
                released_at=released_at,
                dmg_key=dmg_key,
                min_version=data.get("min_version"),
            )

            self.update_found.emit(release)

        except requests.RequestException as e:
            logger.error(f"Failed to check for updates: {e}")
            self.check_failed.emit(str(e))
        except Exception as e:
            logger.error(f"Unexpected error checking updates: {e}")
            self.check_failed.emit(str(e))


class UpdateManager(QObject):
    """Manages application updates from S3"""

    # Signals
    update_available = pyqtSignal(object)  # ReleaseInfo
    update_progress = pyqtSignal(object)  # UpdateProgress
    update_ready = pyqtSignal(str)  # Path to new app
    update_error = pyqtSignal(str)  # Error message
    state_changed = pyqtSignal(UpdateState)

    # Configuration
    S3_BUCKET = UPDATE_S3_BUCKET
    S3_REGION = UPDATE_S3_REGION
    S3_PREFIX = "mcc"  # All update files are under this prefix
    API_TIMEOUT = 10  # seconds
    CACHE_DIR = (
        Path.home() / "Library" / "Caches" / "com.multicam.controller" / "updates"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = UpdateState.IDLE
        self.current_version = self._get_current_version()
        self.latest_release: Optional[ReleaseInfo] = None
        self.download_path: Optional[Path] = None
        self._download_worker: Optional[DownloadWorker] = None
        self._check_worker: Optional[UpdateCheckWorker] = None
        self._mounted_volume: Optional[str] = None
        self._new_app_path: Optional[str] = None

        logger.info(f"UpdateManager initialized, current version: {self.current_version}")

    @property
    def state(self) -> UpdateState:
        return self._state

    @state.setter
    def state(self, value: UpdateState):
        if self._state != value:
            self._state = value
            self.state_changed.emit(value)
            logger.debug(f"Update state changed to: {value.value}")

    def _get_current_version(self) -> str:
        """Get current app version from VERSION file"""
        if getattr(sys, "frozen", False):
            # Running as bundled PyInstaller app
            version_file = Path(sys._MEIPASS) / "resources" / "VERSION"
        else:
            # Running in development - go from services/ -> src/ -> project root
            version_file = Path(__file__).parent.parent.parent / "resources" / "VERSION"

        try:
            version = version_file.read_text().strip()
            logger.debug(f"Read version '{version}' from {version_file}")
            return version
        except FileNotFoundError:
            logger.warning(f"VERSION file not found at {version_file}")
            return "0.0.0"

    def _get_s3_url(self, key: str) -> str:
        """Get public S3 URL for an object"""
        return f"https://{self.S3_BUCKET}.s3.{self.S3_REGION}.amazonaws.com/{key}"

    def check_for_updates_async(self):
        """Check for updates (non-blocking, runs in background thread)"""
        logger.info("=== UPDATE CHECK STARTED ===")
        logger.info(f"Current version: {self.current_version}")
        logger.info(f"S3 bucket: {self.S3_BUCKET}")
        logger.info(f"S3 prefix: {self.S3_PREFIX}")

        if self.state == UpdateState.CHECKING:
            logger.warning("Update check already in progress")
            return

        self.state = UpdateState.CHECKING

        # Create and start background worker
        latest_url = self._get_s3_url(f"{self.S3_PREFIX}/latest.json")
        self._check_worker = UpdateCheckWorker(
            url=latest_url,
            current_version=self.current_version,
            timeout=self.API_TIMEOUT,
            parent=self,
        )
        self._check_worker.update_found.connect(self._on_check_complete)
        self._check_worker.check_failed.connect(self._on_check_failed)
        self._check_worker.start()

    def _on_check_complete(self, release: Optional[ReleaseInfo]):
        """Handle update check completion"""
        self._check_worker = None
        if release:
            self.latest_release = release
            self.state = UpdateState.AVAILABLE
            self.update_available.emit(release)
            logger.info(f"=== UPDATE AVAILABLE: {release.version} ===")
        else:
            self.state = UpdateState.IDLE
            logger.info("=== NO UPDATE AVAILABLE ===")

    def _on_check_failed(self, error: str):
        """Handle update check failure"""
        self._check_worker = None
        logger.error(f"=== UPDATE CHECK FAILED: {error} ===")
        self.state = UpdateState.IDLE

    def download_update(self, release: Optional[ReleaseInfo] = None):
        """Start downloading update in background"""
        if release is None:
            release = self.latest_release

        if release is None:
            self.update_error.emit("No release information available")
            return

        if self.state == UpdateState.DOWNLOADING:
            logger.warning("Download already in progress")
            return

        self.state = UpdateState.DOWNLOADING

        # Prepare download destination
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Use the DMG key as filename
        dmg_filename = release.dmg_key.split("/")[-1] if "/" in release.dmg_key else release.dmg_key
        self.download_path = self.CACHE_DIR / dmg_filename

        # Remove any existing download
        self.download_path.unlink(missing_ok=True)

        # Start download worker
        self._download_worker = DownloadWorker(
            url=release.download_url,
            destination=self.download_path,
            expected_size=release.file_size,
            parent=self,
        )
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

        logger.info(f"Started downloading update: {dmg_filename}")

    def cancel_download(self):
        """Cancel ongoing download"""
        if self._download_worker and self._download_worker.isRunning():
            self._download_worker.cancel()
            self._download_worker.wait()
            self._download_worker = None
            self.state = UpdateState.AVAILABLE
            logger.info("Download cancelled")

    def _on_download_progress(self, progress: UpdateProgress):
        """Handle download progress update"""
        self.update_progress.emit(progress)

    def _on_download_finished(self, path: str):
        """Handle download completion"""
        logger.info(f"Download finished: {path}")
        self._download_worker = None

        # Mount and prepare the update
        try:
            self._prepare_update(Path(path))
        except Exception as e:
            logger.error(f"Failed to prepare update: {e}")
            self.state = UpdateState.ERROR
            self.update_error.emit(f"Failed to prepare update: {e}")

    def _on_download_error(self, error: str):
        """Handle download error"""
        logger.error(f"Download error: {error}")
        self._download_worker = None
        self.state = UpdateState.ERROR
        self.update_error.emit(error)

    def _prepare_update(self, dmg_path: Path):
        """Mount DMG and locate app bundle"""
        logger.info(f"Preparing update from: {dmg_path}")

        # Mount the DMG
        result = subprocess.run(
            ["hdiutil", "attach", "-nobrowse", "-readonly", str(dmg_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to mount DMG: {result.stderr}")

        # Parse mount point from output
        # Output format: /dev/disk4s1	Apple_HFS	/Volumes/MultiCam Controller
        mount_point = None
        for line in result.stdout.strip().split("\n"):
            if "/Volumes/" in line:
                parts = line.split("\t")
                if len(parts) >= 3:
                    mount_point = parts[-1].strip()
                    break

        if not mount_point:
            raise RuntimeError("Could not determine DMG mount point")

        self._mounted_volume = mount_point
        logger.info(f"DMG mounted at: {mount_point}")

        # Find .app in mounted volume
        volume_path = Path(mount_point)
        app_bundles = list(volume_path.glob("*.app"))

        if not app_bundles:
            self._unmount_dmg()
            raise RuntimeError("No .app bundle found in DMG")

        self._new_app_path = str(app_bundles[0])
        logger.info(f"Found app bundle: {self._new_app_path}")

        self.state = UpdateState.READY
        self.update_ready.emit(self._new_app_path)

    def _unmount_dmg(self):
        """Unmount the DMG if mounted"""
        if self._mounted_volume:
            subprocess.run(
                ["hdiutil", "detach", self._mounted_volume, "-quiet"],
                capture_output=True,
            )
            self._mounted_volume = None

    def apply_and_restart(self):
        """Apply the update and restart the application"""
        if self.state != UpdateState.READY or not self._new_app_path:
            self.update_error.emit("Update not ready to apply")
            return

        self.state = UpdateState.APPLYING

        try:
            current_app = self._get_app_path()
            helper_script = self._get_helper_script_path()
            app_pid = os.getpid()

            logger.info(f"Applying update:")
            logger.info(f"  Current app: {current_app}")
            logger.info(f"  New app: {self._new_app_path}")
            logger.info(f"  Helper script: {helper_script}")
            logger.info(f"  App PID: {app_pid}")

            # Copy helper script to temp location (in case app bundle gets replaced)
            temp_script = Path(tempfile.gettempdir()) / "multicam_apply_update.sh"
            shutil.copy2(helper_script, temp_script)
            os.chmod(temp_script, 0o755)

            # Launch helper script as detached process
            subprocess.Popen(
                [
                    str(temp_script),
                    str(app_pid),
                    self._new_app_path,
                    str(current_app),
                    self._mounted_volume or "",
                ],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            logger.info("Helper script launched, quitting application...")

            # Quit the application
            from PySide6.QtWidgets import QApplication

            QApplication.quit()

        except Exception as e:
            logger.error(f"Failed to apply update: {e}")
            self.state = UpdateState.ERROR
            self.update_error.emit(f"Failed to apply update: {e}")

    def _get_app_path(self) -> Path:
        """Get path to current app bundle"""
        if getattr(sys, "frozen", False):
            # Running as bundled app - executable is inside .app/Contents/MacOS/
            return Path(sys.executable).parent.parent.parent
        else:
            # Running in development - return a placeholder
            return Path("/Applications/MultiCam Controller.app")

    def _get_helper_script_path(self) -> Path:
        """Get path to apply_update.sh script"""
        if getattr(sys, "frozen", False):
            # Bundled with app
            return Path(sys._MEIPASS) / "resources" / "scripts" / "apply_update.sh"
        else:
            # Development
            return (
                Path(__file__).parent.parent.parent
                / "resources"
                / "scripts"
                / "apply_update.sh"
            )

    def cleanup(self):
        """Clean up resources (skipped if update is being applied)"""
        # Don't cleanup if we're in the middle of applying an update
        # The helper script needs the DMG to stay mounted
        if self.state == UpdateState.APPLYING:
            logger.debug("Skipping cleanup - update is being applied")
            return

        self.cancel_download()
        self._unmount_dmg()

        # Clean up cache directory
        if self.CACHE_DIR.exists():
            shutil.rmtree(self.CACHE_DIR, ignore_errors=True)
