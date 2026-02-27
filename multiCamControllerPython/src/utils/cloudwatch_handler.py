"""CloudWatch Logs handler for remote logging"""

import atexit
import logging
import threading
import queue
import time
import uuid
import json
import sys
import traceback
from pathlib import Path
from typing import Optional, Dict

import boto3
from botocore.exceptions import ClientError

# Constants
LOG_GROUP_NAME = "MCC"
BATCH_SIZE = 100  # CloudWatch max is 10,000, but smaller batches are more responsive
BATCH_INTERVAL_SECONDS = 5  # Flush every 5 seconds
MAX_QUEUE_SIZE = 10000  # Prevent memory issues
APP_UUID_FILE = Path.home() / ".multicam" / "app_uuid.txt"


def _get_or_create_app_uuid() -> str:
    """
    Get or create persistent app UUID at ~/.multicam/app_uuid.txt

    Follows the pattern from oak_device.py for oak_device_id.txt
    Returns just the first segment (8 chars) of the UUID.
    """
    multicam_dir = Path.home() / ".multicam"
    multicam_dir.mkdir(parents=True, exist_ok=True)

    if APP_UUID_FILE.exists():
        full_uuid = APP_UUID_FILE.read_text().strip()
        # Return just the first segment
        return full_uuid.split("-")[0]

    full_uuid = str(uuid.uuid4())
    APP_UUID_FILE.write_text(full_uuid)
    # Return just the first segment
    return full_uuid.split("-")[0]


def _generate_session_uuid() -> str:
    """Generate a short session UUID (first 8 chars) for this app session."""
    return str(uuid.uuid4()).split("-")[0]


def _load_cloudwatch_credentials() -> Optional[Dict[str, str]]:
    """
    Load CloudWatch credentials from cloudwatch_secrets.json

    Follows the pattern from s3_manager.py for secrets.json
    """
    try:
        if getattr(sys, "frozen", False):
            # Running as bundled app - secrets in Resources
            bundle_dir = Path(sys._MEIPASS)
            secrets_path = bundle_dir / "cloudwatch_secrets.json"
        else:
            # Running in development
            secrets_path = Path(__file__).parent.parent.parent / "cloudwatch_secrets.json"

        if not secrets_path.exists():
            return None  # CloudWatch logging disabled if no credentials

        with open(secrets_path, "r") as f:
            credentials = json.load(f)

        # Validate required fields
        required = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
        if not all(k in credentials for k in required):
            return None

        return credentials

    except Exception:
        return None


class CloudWatchHandler(logging.Handler):
    """
    Async-safe CloudWatch Logs handler that batches log events.

    Features:
    - Non-blocking: uses background thread for network I/O
    - Batching: groups logs to respect CloudWatch rate limits
    - Graceful degradation: network failures don't crash the app
    - Session log streams: {APP_UUID}_{SESSION_UUID} format
    """

    def __init__(self, level=logging.NOTSET):
        super().__init__(level)

        self._log_queue: queue.Queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        self._shutdown = threading.Event()
        self._client = None
        self._sequence_token: Optional[str] = None
        self._current_stream_name: Optional[str] = None
        self._app_uuid: Optional[str] = None
        self._session_uuid: Optional[str] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._enabled = False
        self._region = "us-east-1"

        # Try to initialize
        self._initialize()

    def _initialize(self) -> bool:
        """Initialize CloudWatch client and start worker thread."""
        try:
            # Load credentials
            credentials = _load_cloudwatch_credentials()
            if not credentials:
                return False

            # Get or create app UUID and generate session UUID
            self._app_uuid = _get_or_create_app_uuid()
            self._session_uuid = _generate_session_uuid()
            self._region = credentials.get("AWS_REGION", "us-east-1")

            # Create CloudWatch Logs client
            self._client = boto3.client(
                "logs",
                region_name=self._region,
                aws_access_key_id=credentials["AWS_ACCESS_KEY_ID"],
                aws_secret_access_key=credentials["AWS_SECRET_ACCESS_KEY"],
            )

            # Start background worker
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True, name="CloudWatchLogWorker"
            )
            self._worker_thread.start()

            # Register atexit handler to flush logs on app exit
            atexit.register(self.close)

            self._enabled = True
            return True

        except Exception as e:
            # Log to stderr since logging isn't fully set up
            print(f"CloudWatch logging disabled: {e}", file=sys.stderr)
            return False

    def is_enabled(self) -> bool:
        """Check if CloudWatch logging is enabled."""
        return self._enabled

    def _get_log_stream_name(self) -> str:
        """Generate log stream name: {APP_UUID}_{SESSION_UUID}"""
        return f"{self._app_uuid}_{self._session_uuid}"

    def _ensure_log_stream(self) -> bool:
        """Create log stream if it doesn't exist."""
        stream_name = self._get_log_stream_name()

        # Check if we need to create the stream
        if stream_name != self._current_stream_name:
            try:
                self._client.create_log_stream(
                    logGroupName=LOG_GROUP_NAME, logStreamName=stream_name
                )
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code == "ResourceAlreadyExistsException":
                    # Stream exists, that's fine
                    pass
                else:
                    # Log the error and re-raise
                    print(f"Failed to create log stream: {error_code} - {e}", file=sys.stderr)
                    raise

            self._current_stream_name = stream_name
            self._sequence_token = None  # Reset token for new stream

        return True

    def emit(self, record):
        """Queue log record for async sending."""
        if not self._enabled:
            return

        try:
            # Format the record
            msg = self.format(record)
            timestamp = int(record.created * 1000)  # CloudWatch uses milliseconds

            # Non-blocking put
            self._log_queue.put_nowait({"timestamp": timestamp, "message": msg})
        except queue.Full:
            pass  # Drop logs if queue is full (graceful degradation)
        except Exception:
            pass  # Never crash the app

    def _worker_loop(self):
        """Background thread that batches and sends logs to CloudWatch."""
        batch = []
        last_flush = time.time()

        while not self._shutdown.is_set():
            try:
                # Try to get a log event with timeout
                try:
                    event = self._log_queue.get(timeout=1.0)
                    batch.append(event)
                except queue.Empty:
                    pass

                # Flush if batch is full or interval elapsed
                should_flush = len(batch) >= BATCH_SIZE or (
                    batch and time.time() - last_flush >= BATCH_INTERVAL_SECONDS
                )

                if should_flush and batch:
                    self._send_batch(batch)
                    batch = []
                    last_flush = time.time()

            except Exception as e:
                # Log to stderr, don't crash
                print(f"CloudWatch worker error: {e}", file=sys.stderr)
                batch = []  # Drop batch on error

        # Final flush on shutdown
        if batch:
            try:
                self._send_batch(batch)
            except Exception:
                pass

    def _send_batch(self, events: list):
        """Send a batch of log events to CloudWatch."""
        if not events:
            return

        try:
            self._ensure_log_stream()

            # Sort by timestamp (CloudWatch requirement)
            events.sort(key=lambda x: x["timestamp"])

            # Build request
            kwargs = {
                "logGroupName": LOG_GROUP_NAME,
                "logStreamName": self._current_stream_name,
                "logEvents": events,
            }

            if self._sequence_token:
                kwargs["sequenceToken"] = self._sequence_token

            # Send
            response = self._client.put_log_events(**kwargs)
            self._sequence_token = response.get("nextSequenceToken")

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code in (
                "InvalidSequenceTokenException",
                "DataAlreadyAcceptedException",
            ):
                # Get correct sequence token and retry
                expected_token = e.response["Error"].get("expectedSequenceToken")
                if expected_token:
                    self._sequence_token = expected_token
                    self._send_batch(events)  # Retry once
            else:
                raise

    def flush(self):
        """Flush pending logs (blocking)."""
        if not self._enabled:
            return

        # Wait for queue to drain (with timeout)
        timeout = 10  # seconds
        start = time.time()
        while not self._log_queue.empty() and time.time() - start < timeout:
            time.sleep(0.1)

    def close(self):
        """Flush remaining logs and shutdown worker."""
        if self._enabled:
            self._shutdown.set()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=5)
        super().close()


def install_exception_handler():
    """
    Install sys.excepthook to capture unhandled exceptions.

    Logs full stack trace to CloudWatch before app crashes.
    """
    original_excepthook = sys.excepthook
    crash_logger = logging.getLogger("CRASH")

    def exception_handler(exc_type, exc_value, exc_traceback):
        """Log unhandled exceptions with full traceback."""
        if issubclass(exc_type, KeyboardInterrupt):
            # Don't log keyboard interrupts
            original_excepthook(exc_type, exc_value, exc_traceback)
            return

        # Format the exception with full traceback
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        tb_text = "".join(tb_lines)

        # Log as CRITICAL with full trace
        crash_logger.critical(f"Unhandled exception:\n{tb_text}")

        # Flush CloudWatch handler to ensure crash is logged
        for handler in logging.getLogger().handlers:
            if isinstance(handler, CloudWatchHandler):
                handler.flush()

        # Call original handler
        original_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = exception_handler
