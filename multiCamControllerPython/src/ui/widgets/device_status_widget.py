"""Device status widget - displays detailed device information"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from PySide6.QtCore import Qt

from multicam_common import StatusResponse
from models.device import MultiCamDevice


class DeviceStatusWidget(QWidget):
    """Widget displaying comprehensive device status information"""

    def __init__(self, device: MultiCamDevice, parent=None):
        super().__init__(parent)
        self.device = device
        self.current_status: Optional[StatusResponse] = None
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI layout"""
        self.setStyleSheet("""
            DeviceStatusWidget {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 5px;
            }
            DeviceStatusWidget:hover {
                border: 1px solid #4a90e2;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(5)

        # Top row: Device name and battery
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # Device name
        self.name_label = QLabel(self.device.display_name)
        self.name_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        top_row.addWidget(self.name_label)

        top_row.addStretch()

        # Battery label
        self.battery_label = QLabel("--")
        self.battery_label.setStyleSheet("color: #666; font-size: 11px;")
        top_row.addWidget(self.battery_label)

        main_layout.addLayout(top_row)

        # Second row: IP address and status
        self.ip_label = QLabel(f"{self.device.ip}:{self.device.port} | --")
        self.ip_label.setStyleSheet("color: #888; font-size: 10px;")
        main_layout.addWidget(self.ip_label)

    def update_status(self, status: StatusResponse):
        """Update widget with new status information"""
        self.current_status = status

        # Update device name with type if available
        if status.deviceType:
            # Extract simple device type name for display
            device_type_display = status.deviceType.split(':')[-1]  # "Android:Quest" -> "Quest"
            self.name_label.setText(f"{self.device.display_name} [{device_type_display}]")
        else:
            self.name_label.setText(self.device.display_name)

        # Update battery
        if status.batteryLevel is not None:
            self.battery_label.setText(f"Battery: {status.batteryLevel:.0f}%")
        else:
            self.battery_label.setText("Battery: --")

        # Update IP and status
        self.ip_label.setText(f"{self.device.ip}:{self.device.port} | {status.status}")

    def get_device_name(self) -> str:
        """Get the device name"""
        return self.device.name
