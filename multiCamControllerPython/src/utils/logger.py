"""Logging configuration"""

import logging
import sys
from pathlib import Path

from utils.cloudwatch_handler import CloudWatchHandler, install_exception_handler


def setup_logging(log_level=logging.INFO, log_file: str = None):
    """Setup application logging with optional CloudWatch integration"""

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # CloudWatch handler (enabled if credentials exist)
    cloudwatch_handler = CloudWatchHandler(level=log_level)
    if cloudwatch_handler.is_enabled():
        cloudwatch_handler.setFormatter(formatter)
        root_logger.addHandler(cloudwatch_handler)
        root_logger.info("CloudWatch logging enabled")

    # Install global exception handler for unhandled exceptions
    install_exception_handler()

    # Reduce verbosity of some noisy libraries
    logging.getLogger("zeroconf").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return root_logger
