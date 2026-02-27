"""Video decoder with direct frame access via index."""

import json
import subprocess
import logging
from collections import deque
import av
import numpy as np

from ..utils.ffmpeg_utils import get_ffprobe_path


def build_frame_index(path: str) -> tuple[list[tuple[int, int]], float]:
    """Deprecated heavy index build kept for compatibility. Not used in fast path.

    Returns a minimal placeholder index and a best-effort FPS estimate using ffprobe only
    if available, otherwise defaults. This avoids parsing every frame at startup.
    """
    logging.info(f"Fast init: skipping full frame index build for {path}")
    try:
        # Try to get FPS via ffprobe without enumerating all frames
        ffprobe = get_ffprobe_path()
        cmd = [
            ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-of", "json",
            "-show_streams",
            path,
        ]
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        data = json.loads(out)
        streams = data.get("streams", [])
        fps = 30.0
        if streams:
            stream = streams[0]
            # avg_frame_rate like "30000/1001"
            afr = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
            if afr and afr != "0/0":
                num, den = afr.split("/")
                num = float(num)
                den = float(den) if float(den) != 0 else 1.0
                fps = num / den if den else 30.0
        return [(0, 0)], float(fps)
    except Exception:
        return [(0, 0)], 30.0


class TrackDecoder:
    """Video decoder with direct frame access via index."""

    def __init__(self, path: str):
        self.path = path
        self.container = av.open(path)
        self.vs = self.container.streams.video[0]
        self.time_base = self.vs.time_base
        self.duration_us = int(self.vs.duration * float(self.time_base) * 1_000_000) if self.vs.duration else 0

        # Lightweight FPS estimate from stream; fallback to ffprobe helper
        try:
            self.fps = float(self.vs.average_rate) if self.vs.average_rate else None
        except Exception:
            self.fps = None
        if not self.fps:
            _, self.fps = build_frame_index(path)

        # Estimated total frames (for info only)
        self.total_frames = int((self.duration_us / 1_000_000.0) * self.fps) if self.duration_us and self.fps else 0

        # Sliding window / history of decoded frames near current playback
        # Stores tuples of (pts_us, img_bgr)
        self.history_frames: deque[tuple[int, np.ndarray]] = deque()
        self.max_history_frames = 90  # ~1.5s @60fps or 3s @30fps

        # Last decoded presentation timestamp in microseconds
        self.last_decoded_pts_us: int | None = None

        # How far around a target to rebuild the window when seeking (microseconds)
        self.window_pre_us = 250_000
        self.window_post_us = 250_000
        self.backward_slack_us = 50_000
        self.forward_slack_us = 200_000

        logging.info(f"Initialized decoder for {path}: {self.total_frames} frames, {self.fps:.2f} fps, duration={self.duration_us/1_000_000:.3f}s")

    def _decode_frame_by_timestamp(self, target_us: int) -> tuple[int, np.ndarray]:
        """Decode or retrieve the frame at or before target timestamp using a sliding window.

        Strategy:
        - If target is slightly ahead of the last decoded PTS, continue decoding forward without seeking.
        - If target is within the in-memory history, pick the best frame from history.
        - Otherwise, seek to a little before the target, rebuild a small window, and return.
        """
        try:
            # Helper to pick best frame <= target from a sequence of (pts_us, img)
            def pick_best_from(frames: deque[tuple[int, np.ndarray]], tgt_us: int) -> tuple[int, np.ndarray] | None:
                best: tuple[int, np.ndarray] | None = None
                for pts_us, img in frames:
                    if pts_us <= tgt_us:
                        if best is None or pts_us > best[0]:
                            best = (pts_us, img)
                return best

            # If within history range, try to satisfy from memory first
            if self.history_frames:
                history_min = self.history_frames[0][0]
                history_max = self.history_frames[-1][0]
                if history_min - self.backward_slack_us <= target_us <= history_max + self.forward_slack_us:
                    best = pick_best_from(self.history_frames, target_us)
                    if best is not None:
                        # If we already have enough future coverage, return immediately
                        if history_max >= target_us + self.forward_slack_us:
                            return best
                        # Otherwise, we will extend coverage below without seeking
                        tentative_best = best
                    else:
                        tentative_best = None
                else:
                    tentative_best = None
            else:
                tentative_best = None

            # Decide whether to seek: only when going significantly backwards or on first decode
            need_seek = False
            if self.last_decoded_pts_us is None:
                need_seek = True
            else:
                if self.history_frames:
                    history_min = self.history_frames[0][0]
                    if target_us + self.backward_slack_us < history_min:
                        need_seek = True

            if need_seek:
                seek_start_us = max(0, target_us - self.window_pre_us)
                seek_ts = int(seek_start_us / (self.time_base * 1_000_000))
                self.container.seek(seek_ts, backward=True, stream=self.vs)
                self.history_frames.clear()
                self.last_decoded_pts_us = None

            # Decode forward until we cover target_us + small post window or we hit a reasonable frame cap
            frames_decoded = 0
            frame_cap = 150  # safety cap per call
            best_frame: tuple[int, np.ndarray] | None = tentative_best if 'tentative_best' in locals() else None
            cover_until_us = target_us + self.window_post_us

            # If we already decoded far enough into the future, skip decoding and return the best we have
            if not need_seek and self.history_frames and self.history_frames[-1][0] >= cover_until_us and best_frame is not None:
                return best_frame

            for frame in self.container.decode(self.vs):
                if frame.pts is None:
                    continue
                frame_ts = int(frame.pts * float(self.time_base) * 1_000_000)
                img = frame.to_ndarray(format="bgr24")

                # Append to history
                self.history_frames.append((frame_ts, img))
                self.last_decoded_pts_us = frame_ts
                frames_decoded += 1

                # Trim history size
                while len(self.history_frames) > self.max_history_frames:
                    self.history_frames.popleft()

                # Track best frame at or before target
                if frame_ts <= target_us:
                    best_frame = (frame_ts, img)

                # Stop when we've passed target and have some future coverage
                if frame_ts >= cover_until_us or frames_decoded >= frame_cap:
                    break

            # If we still do not have a best frame (e.g., first frame after seek is already past target),
            # try to pick from whatever is in history now.
            if best_frame is None and self.history_frames:
                best_frame = pick_best_from(self.history_frames, target_us)

            if best_frame is not None:
                return best_frame

        except Exception as e:
            logging.error(f"Failed to decode frame at {target_us}us: {e}")

        # Fallback: return dummy frame
        logging.warning(f"Could not decode frame at {target_us}us, returning black frame")
        dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
        return (target_us, dummy_img)

    def frame_at_or_before(self, target_us: int):
        """Get the frame at or before the target timestamp."""
        # Sliding window based timestamp lookup/decoding
        return self._decode_frame_by_timestamp(target_us)

    def close(self):
        """Close the video container and release resources."""
        if self.container is not None:
            try:
                self.container.close()
                logging.info(f"Closed decoder for {self.path}")
            except Exception as e:
                logging.warning(f"Error closing decoder for {self.path}: {e}")
            finally:
                self.container = None
                # Clear the history frames to free memory
                self.history_frames.clear()

    def __del__(self):
        """Destructor to ensure container is closed."""
        self.close()
