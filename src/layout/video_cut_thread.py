import os
from loguru import logger

from PyQt5.QtCore import QThread, pyqtSignal

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")

class VideoCutThread(QThread):
    finished = pyqtSignal(str)

    def __init__(self, command, file_name, parent=None):
        super(VideoCutThread, self).__init__(parent)
        self.command = command
        self.file_name = file_name

    def run(self) -> None:

        p = os.popen(self.command)

        logger.info(p)

        self.finished.emit(self.file_name)