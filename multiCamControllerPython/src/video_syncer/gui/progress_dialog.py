"""Progress dialog for long-running operations."""

from PySide6 import QtWidgets


class ProgressDialog(QtWidgets.QDialog):
    """Progress dialog for long-running operations."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(400, 150)

        layout = QtWidgets.QVBoxLayout()

        self.label = QtWidgets.QLabel("Preparing...")
        layout.addWidget(self.label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)
        self.cancelled = False

    def update_progress(self, value: int, text: str = ""):
        """Update progress bar and text."""
        self.progress_bar.setValue(value)
        if text:
            self.label.setText(text)

        # Change button to "OK" when complete
        if value >= 100:
            self.cancel_button.setText("OK")
            self.cancel_button.clicked.disconnect()
            self.cancel_button.clicked.connect(self.accept)

        QtWidgets.QApplication.processEvents()

    def reject(self):
        """Handle cancel button."""
        self.cancelled = True
        super().reject()
