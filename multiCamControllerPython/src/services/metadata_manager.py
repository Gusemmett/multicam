"""Metadata file management for recording sessions"""

import json
import logging
import os
import tempfile
import requests
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MetadataManager:
    """Manages creation and persistence of metadata.json files"""

    # WeatherAPI.com API key — set via WEATHER_API_KEY env var
    _WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")

    @staticmethod
    def _get_location_and_weather(timeout: int = 5) -> tuple[Optional[Dict], Optional[Dict]]:
        """
        Get location and weather data from WeatherAPI.com using IP-based location detection.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Tuple of (location_dict, weather_dict) or (None, None) if failed
        """
        try:
            # WeatherAPI.com current weather API with auto IP detection
            url = "http://api.weatherapi.com/v1/current.json"
            params = {
                "key": MetadataManager._WEATHER_API_KEY,
                "q": "auto:ip",  # Automatically detect location from IP
                "aqi": "no"  # We don't need air quality data
            }
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            # Extract location data
            location = data.get("location", {})
            location_data = {
                "latitude": location.get("lat"),
                "longitude": location.get("lon"),
                "city": location.get("name"),
                "country": location.get("country")
            }

            # Extract weather data
            current = data.get("current", {})
            weather_data = {
                "temperature_celsius": current.get("temp_c"),
                "conditions": current.get("condition", {}).get("text"),
                "cloud_cover_percent": current.get("cloud"),
                "uv_index": current.get("uv")
            }

            return location_data, weather_data

        except Exception as e:
            logger.warning(f"Failed to get location and weather data from WeatherAPI.com: {e}")
            return None, None

    @staticmethod
    def create_metadata(
        session_id: str,
        recorder_name: Optional[str],
        recording_start_time: Optional[datetime],
        file_names: Optional[Dict[str, str]] = None,
        openweather_api_key: Optional[str] = None,  # Kept for backwards compatibility but not used
        task: Optional[str] = None
    ) -> Dict:
        """
        Create metadata dictionary for a recording session.

        Args:
            session_id: Unique identifier for the recording session
            recorder_name: Name of the person/device recording
            recording_start_time: When the recording started
            file_names: Optional dict mapping device_name -> file_name
            openweather_api_key: Deprecated - kept for backwards compatibility
            task: Task being performed during recording

        Returns:
            Dictionary containing session metadata
        """
        logger.info(f"Creating metadata for session: {session_id}, recorder: {recorder_name or 'Unknown'}")
        
        # Convert recording_start_time to UTC with timezone info
        time_collected_utc = None
        if recording_start_time:
            # If datetime is naive (no timezone), assume it's local time
            if recording_start_time.tzinfo is None:
                recording_start_time = recording_start_time.replace(tzinfo=timezone.utc)
            # Convert to UTC
            time_collected_utc = recording_start_time.astimezone(timezone.utc).isoformat()

        # Get local timezone offset
        now = datetime.now()
        local_offset = now.astimezone().strftime("%z")
        # Format as "+HH:MM" or "-HH:MM"
        local_timezone_offset = f"{local_offset[:3]}:{local_offset[3:]}" if local_offset else None

        metadata = {
            "session_name": session_id,
            "collector_name": recorder_name or "Unknown",
            "task": task,
            "time_collected": time_collected_utc,
            "local_timezone_offset": local_timezone_offset
        }

        # Try to get location and weather data from WeatherAPI.com
        logger.info("Fetching location and weather data from WeatherAPI.com...")
        location_data, weather_data = MetadataManager._get_location_and_weather()
        
        if location_data:
            metadata["location"] = location_data
            logger.info(f"Location data collected: {location_data.get('city')}, {location_data.get('country')}")
        else:
            logger.warning("Failed to collect location data")
        
        if weather_data:
            metadata["weather"] = weather_data
            logger.info(f"Weather data collected: {weather_data.get('temperature_celsius')}°C, {weather_data.get('conditions')}")
        else:
            logger.warning("Failed to collect weather data")

        # Add file names if provided
        if file_names:
            metadata["files"] = file_names
            logger.info(f"Added {len(file_names)} file(s) to metadata")

        # Log the complete metadata object at debug level
        logger.debug(f"Complete metadata object created:\n{json.dumps(metadata, indent=2)}")
        logger.info(f"Metadata creation completed successfully for session: {session_id}")
        
        return metadata

    @staticmethod
    def save_metadata_to_file(
        metadata: Dict,
        file_path: Path
    ) -> bool:
        """
        Save metadata dictionary to a JSON file.

        Args:
            metadata: Metadata dictionary to save
            file_path: Path where the file should be saved

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Saving metadata to file: {file_path}")
            logger.debug(f"Metadata to be saved:\n{json.dumps(metadata, indent=2)}")
            
            with open(file_path, "w") as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"✓ Successfully saved metadata.json at {file_path}")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to save metadata.json at {file_path}: {e}")
            return False

    @staticmethod
    def create_temp_metadata_file(
        session_id: str,
        recorder_name: Optional[str],
        recording_start_time: Optional[datetime],
        file_names: Optional[Dict[str, str]] = None,
        openweather_api_key: Optional[str] = None,
        task: Optional[str] = None
    ) -> Optional[Path]:
        """
        Create a temporary metadata.json file for upload.

        Args:
            session_id: Unique identifier for the recording session
            recorder_name: Name of the person/device recording
            recording_start_time: When the recording started
            file_names: Optional dict mapping device_name -> file_name
            openweather_api_key: Optional OpenWeatherMap API key for weather data
            task: Task being performed during recording

        Returns:
            Path to the temporary file, or None if creation failed
        """
        try:
            logger.info(f"Creating temporary metadata file for session: {session_id}")

            # Create metadata
            metadata = MetadataManager.create_metadata(
                session_id=session_id,
                recorder_name=recorder_name,
                recording_start_time=recording_start_time,
                file_names=file_names,
                openweather_api_key=openweather_api_key,
                task=task
            )

            # Create metadata.json in system temp directory with fixed name
            temp_dir = Path(tempfile.gettempdir())
            temp_path = temp_dir / "metadata.json"

            # Write metadata to file
            with open(temp_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"✓ Created temporary metadata.json at {temp_path}")
            logger.debug(f"Temporary metadata content:\n{json.dumps(metadata, indent=2)}")
            return temp_path

        except Exception as e:
            logger.error(f"✗ Failed to create temporary metadata.json: {e}")
            return None
