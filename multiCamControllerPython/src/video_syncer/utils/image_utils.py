"""Image conversion utilities."""

import numpy as np
from PySide6 import QtGui


def np_bgr_to_qimage(arr: np.ndarray) -> QtGui.QImage:
    """Convert BGR numpy array to QImage."""
    h, w, ch = arr.shape
    bytes_per_line = ch * w
    rgb = arr[:, :, ::-1].copy()  # BGR to RGB
    return QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
