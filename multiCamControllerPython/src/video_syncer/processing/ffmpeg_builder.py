"""FFmpeg command builder to eliminate code repetition."""

from ..utils.ffmpeg_utils import get_ffmpeg_path


class FFmpegCommandBuilder:
    """Builder for FFmpeg commands with common patterns."""

    @staticmethod
    def build_cut_command(
        input_path: str,
        output_path: str,
        cut_time_str: str,
        duration_str: str,
        target_height: int | None = None,
        codec: str = "av1",
        crf: str = "30",
        audio_bitrate: str = "192k",
        max_resolution: tuple[int, int] | None = None,
    ) -> list[str]:
        """Build FFmpeg command for cutting and optionally resizing video.

        Args:
            input_path: Input video file path
            output_path: Output video file path
            cut_time_str: Start time in HH:MM:SS.mmm format
            duration_str: Duration in HH:MM:SS.mmm format
            target_height: Target height for resolution scaling (None = no scaling)
                         DEPRECATED: Use max_resolution instead
            codec: Video codec to use - 'av1' (libaom-av1) or 'h264' (libx264)
            crf: Constant Rate Factor for quality (lower = better quality)
                 Recommended: AV1: 30-35, H.264: 18-23
            audio_bitrate: Audio bitrate
            max_resolution: Maximum resolution as (width, height) tuple
                          e.g., (1280, 720) for 720p ceiling

        Returns:
            List of command arguments for subprocess
        """
        ffmpeg = get_ffmpeg_path()
        cmd = [
            ffmpeg, "-y", "-i", input_path,
            "-ss", cut_time_str, "-t", duration_str,
        ]

        # Determine scaling requirements
        scale_filter = None

        if max_resolution:
            # Apply resolution ceiling
            max_width, max_height = max_resolution
            scale_filter = f"scale='min({max_width},iw)':'min({max_height},ih)':force_original_aspect_ratio=decrease"
        elif target_height:
            # Legacy height-only scaling
            scale_filter = f"scale=-2:{target_height}"

        if scale_filter:
            cmd.extend(["-vf", scale_filter])

        # Add codec-specific encoding parameters
        if codec == "av1":
            # AV1 encoding with libaom-av1
            cmd.extend([
                "-c:v", "libaom-av1",
                "-cpu-used", "4",  # Speed preset (0-8, higher = faster but lower quality)
                "-crf", crf,
                "-b:v", "0",  # Constant quality mode (CQ)
                "-strict", "experimental",  # May be needed for some ffmpeg versions
            ])
        elif codec == "h264":
            # H.264 encoding with libx264
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",  # Speed preset
                "-crf", crf,
            ])
        else:
            raise ValueError(f"Unsupported codec: {codec}. Use 'av1' or 'h264'")

        # Add audio encoding
        cmd.extend([
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            output_path
        ])

        return cmd

    @staticmethod
    def build_tiled_command(
        video_streams: list[tuple[str, str]],
        output_file: str,
        duration_str: str,
        grid_cols: int,
        grid_rows: int,
        tile_width: int,
        tile_height: int,
        preset: str = "medium",
        crf: str = "20",
        fps: int = 30
    ) -> list[str]:
        """Build FFmpeg command for creating tiled video.

        Args:
            video_streams: List of (input_path, cut_time_str) tuples
            output_file: Output file path
            duration_str: Duration in HH:MM:SS.mmm format
            grid_cols: Number of columns in grid
            grid_rows: Number of rows in grid
            tile_width: Width of each tile
            tile_height: Height of each tile
            preset: FFmpeg encoding preset
            crf: Constant Rate Factor for quality
            fps: Output frame rate

        Returns:
            List of command arguments for subprocess
        """
        ffmpeg = get_ffmpeg_path()
        video_count = len(video_streams)
        cmd = [ffmpeg, "-y"]

        # Add all video streams as inputs
        for input_path, cut_str in video_streams:
            cmd.extend(["-ss", cut_str, "-t", duration_str, "-i", input_path])

        # Build filter graph for tiling
        # Scale all inputs to same size first
        scaled_inputs = []
        for i in range(video_count):
            scaled_inputs.append(
                f"[{i}:v]scale={tile_width}:{tile_height}:force_original_aspect_ratio=decrease:eval=frame[v{i}scaled]"
            )

        # Create tile layout
        tile_filter = "".join(f"[v{i}scaled]" for i in range(video_count))
        tile_filter += f"xstack=inputs={video_count}:layout="

        # Generate layout positions
        positions = []
        for i in range(video_count):
            row = i // grid_cols
            col = i % grid_cols
            x = col * tile_width
            y = row * tile_height
            positions.append(f"{x}_{y}")

        tile_filter += "|".join(positions) + "[tiled]"

        # Complete filter graph
        filter_graph = ";".join(scaled_inputs) + ";" + tile_filter

        cmd.extend([
            "-filter_complex", filter_graph,
            "-map", "[tiled]",
            "-c:v", "libx264", "-preset", preset, "-crf", crf,
            "-r", str(fps),
            output_file
        ])

        return cmd
