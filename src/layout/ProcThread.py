import time

from PyQt5.QtCore import QThread, pyqtSignal
from moviepy.video.io.VideoFileClip import VideoFileClip
from proglog import ProgressBarLogger


class ProcThread(QThread):
    progress = pyqtSignal(int)
    message = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, input_path, cut_start, cut_end, parent=None):
        super(ProcThread, self).__init__(parent)
        self.input_path = input_path
        self.cut_start = cut_start
        self.cut_end = cut_end

    def run(self) -> None:
        file_name = (self.input_path.replace('.mp4', "_")
                     + str(int(self.cut_start * 1000)).replace('.', '') + '-'
                     + str(int(self.cut_end * 1000)).replace('.', '') + '-'
                     + time.strftime("%Y%m%d%H%M%S") + '.mp4')

        my_logger = BarLogger(self.message, self.progress)

        video = VideoFileClip(self.input_path)
        video = video.subclip(self.cut_start, self.cut_end)
        video.write_videofile(file_name, threads=5, logger=my_logger)
        video.close()

        self.finished.emit()

class BarLogger(ProgressBarLogger):
    actions_list = []

    def __init__(self, message, progress):
        self.message = message
        self.progress = progress
        super(BarLogger, self).__init__()

    def callback(self, **changes):
        bars = self.state.get('bars')
        index = len(bars.values()) - 1
        if index > -1:
            bar = list(bars.values())[index]
            progress = int(bar['index'] / bar['total'] * 100)
            self.progress.emit(progress)
        if 'message' in changes: self.message.emit(changes['message'])
