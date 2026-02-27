"""S3 upload management"""

import boto3
from botocore.exceptions import ClientError
from pathlib import Path
from datetime import datetime
from typing import List, Callable, Optional
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal as pyqtSignal
import logging
import json
import sys
from utils.constants import MULTICAM_UPLOAD_ROLE_ARN

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of uploading files to S3"""

    success: bool
    session_folder: Optional[str]
    uploaded_count: int
    error: Optional[str]


@dataclass
class SingleFileUploadResult:
    """Result of uploading a single file to S3"""

    success: bool
    s3_key: Optional[str]
    error: Optional[str]


class S3Manager(QObject):
    """Manages file uploads to Amazon S3"""

    upload_progress_changed = pyqtSignal(float)
    upload_complete = pyqtSignal(UploadResult)

    def __init__(self, bucket_name: str, region: str = "us-east-1", parent=None):
        super().__init__(parent)
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = None
        self.upload_progress = 0.0
        self.is_uploading = False

        self._configure_aws_client()

    def _configure_aws_client(self):
        """Configure AWS S3 client"""
        try:
            # Load credentials from secrets.json
            # Handle both development and bundled app paths
            if getattr(sys, 'frozen', False):
                # Running as bundled app - secrets.json is in Resources
                bundle_dir = Path(sys._MEIPASS)
                secrets_path = bundle_dir / "secrets.json"
            else:
                # Running in development
                secrets_path = Path(__file__).parent.parent.parent / "secrets.json"

            logger.info(f"Looking for secrets.json at: {secrets_path}")
            with open(secrets_path, "r") as f:
                secrets = json.load(f)

            # Use explicit credentials from secrets.json
            self.s3_client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=secrets["ACCESS_KEY"],
                aws_secret_access_key=secrets["SECRET_KEY"],
            )
            logger.info(f"AWS S3 client configured for region: {self.region}")
        except Exception as e:
            logger.error(f"Failed to configure AWS S3 client: {e}")

    async def upload_files(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable[[int, int, float, str], None]] = None,
        session_id: Optional[str] = None,
        base_directory: Optional[str] = None,
    ) -> UploadResult:
        """Upload multiple files to S3"""
        self.is_uploading = True
        self.upload_progress = 0.0

        logger.info(f"Starting upload of {len(file_paths)} files to S3...")

        # Generate session folder
        session_folder = self._generate_session_folder(session_id)

        if not self.s3_client:
            self.is_uploading = False
            return UploadResult(
                success=False, session_folder=None, uploaded_count=0, error="S3 client not configured"
            )

        uploaded_count = 0

        for index, file_path in enumerate(file_paths):
            file_path_obj = Path(file_path)
            
            # Preserve directory structure if base_directory is provided
            if base_directory:
                try:
                    # Calculate relative path from base directory
                    relative_path = file_path_obj.relative_to(Path(base_directory))
                    # Use forward slashes for S3 keys (works on all platforms)
                    s3_key = f"{session_folder}{relative_path.as_posix()}"
                    file_display_name = str(relative_path)
                except ValueError:
                    # File is not under base_directory, fall back to filename only
                    logger.warning(f"File {file_path} is not under base directory {base_directory}, using filename only")
                    file_display_name = file_path_obj.name
                    s3_key = f"{session_folder}{file_display_name}"
            else:
                # No base directory - use filename only (backward compatible)
                file_display_name = file_path_obj.name
                s3_key = f"{session_folder}{file_display_name}"

            logger.info(f"Uploading {file_display_name} to s3://{self.bucket_name}/{s3_key}")

            try:
                # Determine content type
                content_type = self._get_content_type(file_path_obj.name)

                # Upload file
                extra_args = {}
                if content_type:
                    extra_args["ContentType"] = content_type

                self.s3_client.upload_file(file_path, self.bucket_name, s3_key, ExtraArgs=extra_args)

                uploaded_count += 1
                progress = (uploaded_count / len(file_paths)) * 100.0

                if progress_callback:
                    progress_callback(index, len(file_paths), 100.0, file_display_name)

                self.upload_progress = progress / 100.0
                self.upload_progress_changed.emit(self.upload_progress)

            except ClientError as e:
                logger.error(f"Failed to upload {file_display_name}: {e}")
                self.is_uploading = False
                return UploadResult(
                    success=False,
                    session_folder=session_folder,
                    uploaded_count=uploaded_count,
                    error=str(e),
                )

        self.upload_progress = 1.0
        self.upload_progress_changed.emit(1.0)
        self.is_uploading = False

        result = UploadResult(
            success=True, session_folder=session_folder, uploaded_count=uploaded_count, error=None
        )

        logger.info(
            f"Upload complete! {uploaded_count} files uploaded to folder: {session_folder}"
        )
        self.upload_complete.emit(result)
        return result

    async def upload_and_cleanup(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable[[int, int, float, str], None]] = None,
        session_id: Optional[str] = None,
        base_directory: Optional[str] = None,
    ) -> UploadResult:
        """Upload files and cleanup local files on success"""
        result = await self.upload_files(file_paths, progress_callback, session_id, base_directory)

        if result.success:
            self._cleanup_local_files(file_paths)
            logger.info("Local files cleaned up after successful upload")

        return result

    async def test_connection(self) -> bool:
        """Test S3 connection"""
        if not self.s3_client:
            logger.error("S3 client not configured")
            return False

        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"S3 connection test successful for bucket: {self.bucket_name}")
            return True
        except ClientError as e:
            logger.error(f"S3 connection test failed: {e}")
            return False

    def generate_presigned_upload_url(
        self,
        file_id: str,
        session_id: str,
        device_name: str,
        device_type: Optional[str] = None,
        expires_in: int = 3600
    ) -> Optional[str]:
        """
        Generate a presigned S3 URL for direct device upload.

        Args:
            file_id: Unique file identifier from device (includes extension)
            session_id: Recording session ID
            device_name: Name of the device
            device_type: Device type from StatusResponse (e.g., "Oak", "Android:Quest")
            expires_in: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned upload URL or None if failed
        """
        if not self.s3_client:
            logger.error("S3 client not configured")
            return None

        try:
            # Generate S3 key: session_folder/device_folder/file_id
            session_folder = self._generate_session_folder(session_id)
            device_folder = self._get_device_folder(device_type)
            s3_key = f"{session_folder}{device_folder}/{file_id}"

            # Generate presigned URL for PUT operation
            presigned_url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expires_in
            )

            logger.info(f"Generated presigned URL for {file_id} (expires in {expires_in}s)")
            logger.info(f"Using bucket: {self.bucket_name}")
            logger.debug(f"S3 key: {s3_key}")

            return presigned_url

        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return None

    def assume_role_for_upload(
        self,
        role_arn: Optional[str] = None,
        session_name: str = "MultiCamDeviceUpload",
        duration_seconds: int = 43200  # Maximum allowed: 12 hours
    ) -> Optional[dict]:
        """
        Assume an IAM role and get temporary credentials for device uploads.

        Args:
            role_arn: ARN of the role to assume (if None, uses MULTICAM_UPLOAD_ROLE_ARN constant)
            session_name: Name for the assumed role session
            duration_seconds: Credential expiration time in seconds (default: 12 hours - maximum allowed)

        Returns:
            Dictionary with keys: AccessKeyId, SecretAccessKey, SessionToken, Expiration
            Returns None if failed
        """
        # Get role ARN from parameter or constant
        if not role_arn:
            role_arn = MULTICAM_UPLOAD_ROLE_ARN

        if not role_arn:
            logger.error("No role ARN provided and MULTICAM_UPLOAD_ROLE_ARN constant not set")
            return None

        if not self.s3_client:
            logger.error("S3 client not configured")
            return None

        try:
            # Create STS client using the same credentials as S3
            sts_client = boto3.client(
                'sts',
                region_name=self.region,
                aws_access_key_id=self.s3_client._request_signer._credentials.access_key,
                aws_secret_access_key=self.s3_client._request_signer._credentials.secret_key
            )

            # Assume role
            response = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                DurationSeconds=duration_seconds
            )

            credentials = response['Credentials']

            logger.info(f"Successfully assumed role: {role_arn}")
            logger.info(f"Credentials expire at: {credentials['Expiration']}")

            # Return credentials in a simplified format
            return {
                'AccessKeyId': credentials['AccessKeyId'],
                'SecretAccessKey': credentials['SecretAccessKey'],
                'SessionToken': credentials['SessionToken'],
                'Expiration': credentials['Expiration'].isoformat()
            }

        except ClientError as e:
            logger.error(f"Failed to assume role {role_arn}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error assuming role: {e}")
            return None

    def _cleanup_local_files(self, file_paths: List[str]):
        """Delete local files and session directory after successful upload"""
        if not file_paths:
            return

        import shutil

        # Find the common ancestor directory of all files (the session directory)
        # Convert all paths to Path objects
        paths = [Path(file_path).resolve() for file_path in file_paths]

        # Find common parent by comparing all path parts
        if len(paths) == 1:
            # Single file - use its parent directory
            session_dir = paths[0].parent
        else:
            # Multiple files - find common ancestor
            common_parts = []
            for parts in zip(*[p.parts for p in paths]):
                if len(set(parts)) == 1:  # All paths have the same part at this level
                    common_parts.append(parts[0])
                else:
                    break

            if common_parts:
                session_dir = Path(*common_parts)
            else:
                # Fallback to first file's parent
                session_dir = paths[0].parent

        # Delete the session directory
        if session_dir.exists() and session_dir.is_dir():
            try:
                shutil.rmtree(session_dir)
                logger.info(f"Deleted session directory: {session_dir}")
            except Exception as e:
                logger.error(f"Failed to delete session directory {session_dir}: {e}")

    def _generate_session_folder(self, session_id: Optional[str] = None) -> str:
        """Generate session folder name with date and session ID"""
        date = datetime.now().strftime("%Y-%m-%d")
        if session_id:
            return f"{date}/{session_id}/"
        else:
            # Fallback to timestamp if no session ID provided
            timestamp = datetime.now().strftime("%Y-%m-%d/%H-%M-%S")
            return f"{timestamp}/"

    @staticmethod
    def _get_device_folder(device_type: Optional[str]) -> str:
        """
        Map device type to S3 folder name.
        
        Args:
            device_type: Device type from StatusResponse (e.g., "Oak", "Android:Quest", "iOS:iPhone")
        
        Returns:
            Folder name: "ego" for Oak, "quest" for Android:Quest, "exo" for everything else
        """
        if not device_type:
            return "exo"
        
        device_type_lower = device_type.lower()
        
        if device_type_lower == "oak":
            return "ego"
        elif "quest" in device_type_lower:
            return "quest"
        else:
            return "exo"

    async def list_directory(self, s3_prefix: str) -> List[dict]:
        """
        List all objects under S3 prefix.

        Args:
            s3_prefix: S3 path prefix (e.g., "2025-01-15/session_123/")

        Returns:
            List of dicts with 'Key', 'Size', 'LastModified'
        """
        if not self.s3_client:
            logger.error("S3 client not configured")
            return []

        try:
            # Ensure prefix ends with /
            if s3_prefix and not s3_prefix.endswith('/'):
                s3_prefix += '/'

            logger.info(f"Listing S3 directory: s3://{self.bucket_name}/{s3_prefix}")

            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=s3_prefix)

            objects = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects.append({
                            'Key': obj['Key'],
                            'Size': obj['Size'],
                            'LastModified': obj['LastModified']
                        })

            logger.info(f"Found {len(objects)} objects in {s3_prefix}")
            return objects

        except ClientError as e:
            logger.error(f"Failed to list S3 directory {s3_prefix}: {e}")
            return []

    async def download_partial_video(
        self,
        s3_key: str,
        local_path: str,
        max_bytes: int = 30_000_000  # 30MB default
    ) -> bool:
        """
        Download first N bytes of video file using range request.

        Args:
            s3_key: S3 object key
            local_path: Local file path to save to
            max_bytes: Maximum bytes to download (default: 20MB)

        Returns:
            True if successful, False otherwise
        """
        if not self.s3_client:
            logger.error("S3 client not configured")
            return False

        try:
            logger.info(f"Downloading first {max_bytes / 1_000_000:.1f}MB of s3://{self.bucket_name}/{s3_key}")

            # Ensure parent directory exists
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            # Download using range request
            range_header = f"bytes=0-{max_bytes - 1}"
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Range=range_header
            )

            # Write to local file
            with open(local_path, 'wb') as f:
                f.write(response['Body'].read())

            file_size = Path(local_path).stat().st_size
            logger.info(f"Downloaded {file_size / 1_000_000:.1f}MB to {local_path}")
            return True

        except ClientError as e:
            logger.error(f"Failed to download {s3_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error downloading {s3_key}: {e}")
            return False

    async def upload_json(self, json_data: dict, s3_key: str) -> bool:
        """
        Upload JSON metadata to S3.

        Args:
            json_data: Dictionary to upload as JSON
            s3_key: S3 object key for the JSON file

        Returns:
            True if successful, False otherwise
        """
        if not self.s3_client:
            logger.error("S3 client not configured")
            return False

        try:
            logger.info(f"Uploading JSON to s3://{self.bucket_name}/{s3_key}")

            # Convert to JSON string
            json_string = json.dumps(json_data, indent=2)

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json_string.encode('utf-8'),
                ContentType='application/json'
            )

            logger.info(f"Successfully uploaded JSON to {s3_key}")
            return True

        except ClientError as e:
            logger.error(f"Failed to upload JSON to {s3_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error uploading JSON to {s3_key}: {e}")
            return False

    @staticmethod
    def _get_content_type(file_name: str) -> Optional[str]:
        """Get MIME content type for file"""
        ext = Path(file_name).suffix.lower()
        content_types = {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".json": "application/json",
            ".txt": "text/plain",
        }
        return content_types.get(ext)
