"""Synchronization calculation engine."""


class SyncEngine:
    """Handles sync point calculations for multiple video tracks."""

    @staticmethod
    def calculate_sync_parameters(tracks: list[dict]) -> dict | None:
        """Calculate sync parameters for video cutting.

        Args:
            tracks: List of track dictionaries containing sync_cut_time_us and decoder info
                    First track (reference) may have cut_start_us and cut_end_us

        Returns:
            Dictionary with cut_times_us, duration_us, and min_pre_sync_us, or None if not ready
        """
        if not tracks:
            return None

        # Collect sync times and durations
        sync_times_us = []
        total_durations_us = []

        for t in tracks:
            sync_us = t.get("sync_cut_time_us")
            if sync_us is None:
                return None
            duration_us = t["decoder"].duration_us or 0
            sync_times_us.append(sync_us)
            total_durations_us.append(duration_us)

        if not sync_times_us:
            return None

        # Get reference track cut range (first track)
        reference_track = tracks[0]
        ref_cut_start_us = reference_track.get("cut_start_us")
        ref_cut_end_us = reference_track.get("cut_end_us")
        ref_sync_us = sync_times_us[0]

        # Determine the actual pre-sync content we want to include
        if ref_cut_start_us is not None:
            # Reference specifies a cut start - this defines how much pre-sync content
            desired_pre_sync_us = ref_sync_us - ref_cut_start_us
        else:
            # No cut start specified - use minimum available pre-sync content
            desired_pre_sync_us = min(sync_times_us)

        # Ensure we don't exceed what's available in any video
        min_pre_sync_us = min(sync_times_us)
        actual_pre_sync_us = min(desired_pre_sync_us, min_pre_sync_us)

        # Calculate new cut points
        cut_times_us = []
        for i, sync_us in enumerate(sync_times_us):
            if i == 0 and ref_cut_start_us is not None:
                # Reference track: use explicit cut_start
                cut_times_us.append(ref_cut_start_us)
            else:
                # Other tracks: calculate based on sync point
                new_cut_us = sync_us - actual_pre_sync_us
                cut_times_us.append(new_cut_us)

        # Calculate available durations from each video
        final_durations_us = []
        for i, (cut_us, duration_us) in enumerate(zip(cut_times_us, total_durations_us)):
            remaining_us = max(0, duration_us - cut_us)
            final_durations_us.append(remaining_us)

        # Determine final output duration
        if ref_cut_start_us is not None and ref_cut_end_us is not None:
            # Reference specifies both start and end - use this range
            ref_desired_duration = ref_cut_end_us - ref_cut_start_us
            shortest_us = min(ref_desired_duration, min(final_durations_us))
        else:
            # Use shortest available duration
            shortest_us = min(final_durations_us) if final_durations_us else 0

        return {
            "cut_times_us": cut_times_us,
            "duration_us": shortest_us,
            "min_pre_sync_us": actual_pre_sync_us
        }
