"""Video Job Service API Client

Client for interacting with the Video Job Service API to retrieve,
complete, and abandon video processing jobs.
"""

import logging
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VideoJob:
    """Represents a video processing job"""
    job_id: str
    job_type: str
    status: str
    s3_uri: str
    assigned_at: str
    expires_at: str
    session_name: Optional[str] = None
    session_data: Optional[Dict[str, Any]] = None


class VideoJobService:
    """Client for Video Job Service API"""

    # API Configuration
    BASE_URL = "https://gk6p6053yg.execute-api.us-east-1.amazonaws.com/prod"
    TIMEOUT = 10  # seconds

    @classmethod
    def get_next_job(cls, job_type: str = "SYNCING", worker_id: Optional[str] = None) -> Optional[VideoJob]:
        """
        Retrieve the next available job from the API.

        Args:
            job_type: Type of job to request (SYNCING or ANNOTATION)
            worker_id: Optional identifier for the worker requesting the job

        Returns:
            VideoJob object if a job is available, None if no jobs available

        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{cls.BASE_URL}/jobs"
        params = {"job_type": job_type}

        if worker_id:
            params["assigned_to"] = worker_id

        logger.info(f"Requesting next {job_type} job for worker: {worker_id or 'anonymous'}")

        try:
            response = requests.get(url, params=params, timeout=cls.TIMEOUT)

            if response.status_code == 404:
                # No jobs available
                logger.info(f"No {job_type} jobs available")
                return None

            response.raise_for_status()

            # Parse response
            data = response.json()

            # Extract session info if present
            session_data = data.get("session")
            session_name = session_data.get("session_name") if session_data else None

            job = VideoJob(
                job_id=data["job_id"],
                job_type=data["job_type"],
                status=data["status"],
                s3_uri=data["s3_uri"],
                assigned_at=data["assigned_at"],
                expires_at=data["expires_at"],
                session_name=session_name,
                session_data=session_data
            )

            logger.info(f"Retrieved job: {job.job_id} (session: {session_name or 'unknown'})")
            return job

        except requests.exceptions.Timeout:
            logger.error(f"Timeout while requesting job from {url}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get next job: {e}")
            raise

    @classmethod
    def complete_job(cls, job_id: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mark a job as completed.

        Args:
            job_id: The job ID to complete
            metadata: Optional metadata about the job completion

        Returns:
            True if successful, False otherwise

        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{cls.BASE_URL}/jobs/{job_id}/complete"

        body = {}
        if metadata:
            body["metadata"] = metadata

        logger.info(f"Completing job: {job_id}")

        try:
            response = requests.post(url, json=body, timeout=cls.TIMEOUT)

            if response.status_code == 404:
                logger.warning(f"Job not found or already completed: {job_id}")
                return False

            response.raise_for_status()

            data = response.json()
            logger.info(
                f"Job {job_id} completed successfully. "
                f"Session: {data.get('session_name')}, "
                f"State: {data.get('previous_state')} → {data.get('new_state')}"
            )
            return True

        except requests.exceptions.Timeout:
            logger.error(f"Timeout while completing job {job_id}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to complete job {job_id}: {e}")
            raise

    @classmethod
    def abandon_job(cls, job_id: str) -> bool:
        """
        Abandon a job, allowing it to be reassigned to another worker.

        Args:
            job_id: The job ID to abandon

        Returns:
            True if successful, False otherwise

        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{cls.BASE_URL}/jobs/{job_id}/abandon"

        logger.info(f"Abandoning job: {job_id}")

        try:
            response = requests.post(url, timeout=cls.TIMEOUT)

            if response.status_code == 404:
                logger.warning(f"Job not found: {job_id}")
                return False

            response.raise_for_status()

            data = response.json()
            logger.info(f"Job {job_id} abandoned successfully (session: {data.get('session_name')})")
            return True

        except requests.exceptions.Timeout:
            logger.error(f"Timeout while abandoning job {job_id}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to abandon job {job_id}: {e}")
            raise
