"""Track control widget for individual video tracks."""

from PySide6 import QtCore, QtWidgets


class TrackControlWidget(QtWidgets.QWidget):
    """Control widget for individual video tracks."""

    def __init__(self, track_name: str, duration_us: int):
        super().__init__()
        self.track_name = track_name
        self.duration_us = duration_us
        self.sync_offset_us = 0  # Offset relative to reference video
        self.cut_start_us = None  # Track cut start for label updates
        self.cut_end_us = None  # Track cut end for label updates

        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(2)  # Reduce spacing between elements
        layout.setContentsMargins(5, 5, 5, 5)  # Reduce padding

        # Scrubber slider at top
        self.scrubber = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.scrubber.setMinimum(0)
        self.scrubber.setMaximum(duration_us // 1000)  # Convert to milliseconds for slider
        self.scrubber.setValue(0)
        layout.addWidget(self.scrubber)

        # Time display (larger text, minimal padding)
        self.time_label = QtWidgets.QLabel("00:00.000")
        self.time_label.setAlignment(QtCore.Qt.AlignCenter)
        self.time_label.setStyleSheet("font-size: 14px; padding: 2px;")
        layout.addWidget(self.time_label)

        # Track label
        self.label = QtWidgets.QLabel(track_name)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet("padding: 2px;")
        layout.addWidget(self.label)

        # Sync info (larger text, minimal padding)
        self.sync_label = QtWidgets.QLabel("Not synced")
        self.sync_label.setAlignment(QtCore.Qt.AlignCenter)
        self.sync_label.setStyleSheet("color: orange; font-size: 13px; padding: 2px;")
        layout.addWidget(self.sync_label)

        # Cut range info (for reference track)
        self.cut_label = QtWidgets.QLabel("")
        self.cut_label.setAlignment(QtCore.Qt.AlignCenter)
        self.cut_label.setStyleSheet("color: purple; font-size: 9pt; padding: 2px;")
        layout.addWidget(self.cut_label)

        self.setLayout(layout)

    def update_time_display(self, time_us: int):
        """Update the time display label."""
        seconds = time_us / 1_000_000
        minutes = int(seconds // 60)
        seconds = seconds % 60
        self.time_label.setText(f"{minutes:02d}:{seconds:06.3f}")

        # Update scrubber position without triggering signals
        self.scrubber.blockSignals(True)
        self.scrubber.setValue(time_us // 1000)
        self.scrubber.blockSignals(False)

    def set_sync_offset(self, offset_us: int):
        """Set the sync offset for this track."""
        self.sync_offset_us = offset_us
        if offset_us == 0:
            self.sync_label.setText("Reference")
            self.sync_label.setStyleSheet("color: green; font-weight: bold; font-size: 13px; padding: 2px;")
        else:
            offset_ms = offset_us / 1000
            self.sync_label.setText(f"Offset: {offset_ms:+.0f}ms")
            self.sync_label.setStyleSheet("color: blue; font-size: 13px; padding: 2px;")

    def set_cut_start(self, cut_start_us: int):
        """Set and display cut start time."""
        self.cut_start_us = cut_start_us
        self._update_cut_label()

    def set_cut_end(self, cut_end_us: int):
        """Set and display cut end time."""
        self.cut_end_us = cut_end_us
        self._update_cut_label()

    def clear_cuts(self):
        """Clear cut start/end display."""
        self.cut_start_us = None
        self.cut_end_us = None
        self.cut_label.setText("")

    def _update_cut_label(self):
        """Update the cut range label."""
        parts = []
        if self.cut_start_us is not None:
            start_sec = self.cut_start_us / 1_000_000
            parts.append(f"Start: {start_sec:.3f}s")
        if self.cut_end_us is not None:
            end_sec = self.cut_end_us / 1_000_000
            parts.append(f"End: {end_sec:.3f}s")

        if parts:
            self.cut_label.setText(" | ".join(parts))
        else:
            self.cut_label.setText("")
