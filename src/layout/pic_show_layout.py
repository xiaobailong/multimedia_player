import os

import send2trash
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import (QPixmap, QImage)

from loguru import logger

from src.layout.pic_input_layout import PicInputLayout
from src.utils import get_log_path


class PicShowLayout(QVBoxLayout):

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window
        self.counter = 0
        self.path = ''
        self.scale = (main_window.right * 4 + 3) / ((main_window.right + main_window.left) * 4)

        self.inputAndExeLayout = PicInputLayout(self)
        self.inputQWidget = QWidget()
        self.inputAndExeLayout.setContentsMargins(0, 0, 0, 0)
        self.inputQWidget.setLayout(self.inputAndExeLayout)
        self.addWidget(self.inputQWidget)

        self.inputAndExeLayout.btn.pressed.connect(self.start_process)
        self.inputAndExeLayout.fullScreenBtn.pressed.connect(main_window.full_screen_custom)
        self.inputAndExeLayout.startAndFullScreenBtn.pressed.connect(self.startProcessWithFullScreen)

        self.titleQLabel = QLabel("Title")
        self.titleQLabel.setText("Title")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.addWidget(self.titleQLabel)

        self.pictureQLabel = QLabel("Picture")
        self.pictureQLabel.setText("Picture")
        self.pictureQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self.qscrollarea = QScrollArea()

        self.screen_width = int(self.main_window.width() * self.scale)
        self.screen_height = int(self.main_window.height() * self.scale)
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))

        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.pictureQLabel)
        self.addWidget(self.qscrollarea)

    def play(self, filePath):
        self.path = filePath

        self.titleQLabel.setText(filePath)

        # 停止上一个 GIF 动画
        self._stop_gif()

        if filePath.lower().endswith('.gif'):
            self._play_gif(filePath)
        else:
            self._play_static(filePath)

    def _play_static(self, filePath):
        """播放静态图片文件"""
        fckimage = QImage(filePath)

        self.screen_width = int(self.main_window.width() * self.scale)
        self.screen_height = int(self.main_window.height() * self.scale)

        pil_image = self.m_resize(self.screen_width, self.screen_height, fckimage)

        pixmap = QPixmap.fromImage(pil_image)

        self.pictureQLabel.resize(pil_image.width(), pil_image.height())
        self.pictureQLabel.setPixmap(pixmap)

    # ------------------------------------------------------------
    # GIF 手动帧播放（使用 Pillow ImageQt —— 无 QMovie 崩溃）
    # ------------------------------------------------------------
    def _play_gif(self, filePath):
        """渐进式解码 GIF：先显示第一帧再后台逐批解码其余帧"""
        from PIL import Image

        self._gif_frames = []    # list of QPixmap (已缩放)
        self._gif_delays = []    # list of int (毫秒)
        self._gif_index = 0
        self._gif_decode_done = False
        self._gif_total_cycles = 1  # 记录完整循环次数（用于幻灯片自动切换）

        # 第 1 步：打开 GIF，只解码第一帧立刻显示
        img = Image.open(filePath)
        self._gif_img = img

        self._prep_and_append_frame(img)

        # 第 2 步：后台定时器逐帧解码剩余帧（每 30ms 解 10 帧）
        if not hasattr(self, '_gif_decode_timer'):
            self._gif_decode_timer = QTimer()
            self._gif_decode_timer.timeout.connect(self._decode_batch)
        else:
            self._gif_decode_timer.stop()

        self._gif_decode_timer.start(30)

        # 第 3 步：播放定时器（初始只有 1 帧等解码完后启动）
        if not hasattr(self, '_gif_timer'):
            self._gif_timer = QTimer()
            self._gif_timer.timeout.connect(self._next_gif_frame)
        else:
            self._gif_timer.stop()

    def _prep_and_append_frame(self, img):
        """将 Pillow Image 当前帧转为 QPixmap 并加入帧列表"""
        from PIL.ImageQt import ImageQt

        frame = img.copy().convert("RGBA")
        w, h = frame.size
        # 使用 Pillow 官方提供的 ImageQt 转换 —— 安全处理 stride/格式
        qimage = ImageQt(frame)
        scaled_size = self._gif_scaled_size(w, h)
        pixmap = QPixmap.fromImage(qimage).scaled(
            scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self._gif_frames.append(pixmap)
        self._gif_delays.append(max(img.info.get('duration', 60), 20))

        # 第一帧直接显示
        if len(self._gif_frames) == 1:
            self.pictureQLabel.setPixmap(pixmap)
            self.pictureQLabel.resize(pixmap.size())

    def _decode_batch(self):
        """每 tick 解码 10 帧，解码完毕转为循环播放"""
        _BATCH = 10
        for _ in range(_BATCH):
            try:
                idx = self._gif_img.tell()
                self._gif_img.seek(idx + 1)
            except EOFError:
                self._gif_img.close()
                self._gif_img = None
                self._gif_decode_done = True
                self._gif_decode_timer.stop()
                # 开始正常循环播放
                self._gif_index = 0
                self._gif_timer.setInterval(self._gif_delays[0])
                self._gif_timer.start()
                return

            try:
                self._prep_and_append_frame(self._gif_img)
            except Exception:
                continue

    def _next_gif_frame(self):
        self._gif_index += 1
        if self._gif_index >= len(self._gif_frames):
            self._gif_index = 0
            # 完成一个完整循环 —— 如果在幻灯片模式中，自动切到下一张
            if self.inputAndExeLayout.timer.isActive():
                self._schedule_next_slide()
                return
        self.pictureQLabel.setPixmap(self._gif_frames[self._gif_index])
        self._gif_timer.setInterval(self._gif_delays[self._gif_index])

    def _schedule_next_slide(self):
        """GIF 完整播放一圈后触发的下一次幻灯片切换"""
        self._gif_timer.stop()
        # 立即通知 refreshPictures 推进计数器
        QTimer.singleShot(0, self._do_next_slide)

    def _do_next_slide(self):
        """执行幻灯片下一张"""
        self._stop_gif()
        self.refreshPictures()

    def _gif_scaled_size(self, w, h):
        """计算 GIF 缩放尺寸"""
        self.screen_width = int(self.main_window.width() * self.scale)
        self.screen_height = int(self.main_window.height() * self.scale)

        if w == 0 or h == 0:
            return QSize(self.screen_width, self.screen_height)

        f1 = 1.0 * self.screen_width / w
        f2 = 1.0 * self.screen_height / h
        factor = min([f1, f2])
        return QSize(int(w * factor), int(h * factor))

    def _stop_gif(self):
        """停止当前 GIF 播放并释放帧内存（防御性 —— 不假设属性存在）"""
        getattr(self, '_gif_timer', QTimer()).stop()
        getattr(self, '_gif_decode_timer', QTimer()).stop()
        img = getattr(self, '_gif_img', None)
        if img is not None:
            img.close()
        self._gif_img = None
        if hasattr(self, '_gif_frames'):
            self._gif_frames.clear()
        self._gif_index = 0
        self._gif_decode_done = False

    def m_resize(self, w_box, h_box, pil_image):  # 参数是：要适应的窗口宽、高、Image.open后的图片

        w, h = pil_image.width(), pil_image.height()  # 获取图像的原始大小

        if w == 0 or h == 0:
            return pil_image.scaled(w_box, h_box)

        f1 = 1.0 * w_box / w
        f2 = 1.0 * h_box / h

        factor = min([f1, f2])

        width = int(w * factor)
        height = int(h * factor)

        return pil_image.scaled(width, height)

    def is_pic(self, path):
        if not path:
            return False
        return path.lower().endswith(
            ('.bmp', '.dib', '.png', '.jpg', '.jpeg', '.pbm', '.pgm', '.ppm', '.tif', '.tiff', '.webp', '.gif'))

    def setVisible(self, visible):
        if visible:
            self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))
        else:
            self.qscrollarea.setGeometry(
                QRect(0, 0, self.main_window.mainQWidget.width(), self.main_window.mainQWidget.height()))
        self.inputQWidget.setVisible(visible)
        self.titleQLabel.setVisible(visible)

    def refreshPictures(self):
        self.counter += 1
        self.refreshPicturesOnly()

    def refreshPicturesOnly(self):
        if len(self.inputAndExeLayout.list_files) == 0:
            return
        img_path = self.inputAndExeLayout.list_files[self.counter]
        self.play(img_path)

    def up(self):
        self.counter += 1
        self.refreshPicturesOnly()

    def down(self):
        self.counter -= 1
        self.refreshPicturesOnly()

    def start_process(self):
        if len(self.inputAndExeLayout.list_files) == 0:
            return
        self.inputAndExeLayout.timer.start()
        self.play(self.inputAndExeLayout.list_files[self.counter])

    def startProcessWithFullScreen(self):
        self.start_process()
        self.main_window.full_screen_custom()

    def pause(self):
        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()
        else:
            self.inputAndExeLayout.timer.start()

    def delete(self):
        try:
            if not self.is_pic(self.path):
                return
            (path, filename) = os.path.split(self.path)
            os.chdir(path)
            send2trash.send2trash(filename)
            self.main_window.notice(self.path + ' 文件已删除!!!')
            self.main_window.model.refresh()
        except Exception as e:
            self.main_window.notice("文件删除异常!!!" + str(e))
