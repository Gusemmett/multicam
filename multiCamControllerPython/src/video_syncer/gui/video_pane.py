"""Video display pane widget."""

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ..utils import np_bgr_to_qimage


class VideoPane(QtWidgets.QLabel):
    """Widget for displaying video frames."""

    def __init__(self, title: str):
        super().__init__()
        self.setMinimumSize(480, 270)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setText(title)

    def show_frame(self, img_bgr: np.ndarray):
        """Display a BGR frame in the pane."""
        if img_bgr is None:
            return
        qimg = np_bgr_to_qimage(img_bgr)
        pix = QtGui.QPixmap.fromImage(qimg).scaled(
            self.width(), self.height(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        self.setPixmap(pix)
