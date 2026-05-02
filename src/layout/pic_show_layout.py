import os

import send2trash
from PIL import Image
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import (QPixmap, QImage, QMovie)

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
        self.titleQLabel.setVisible(False)  # 路径已移至窗口标题栏显示
        self.addWidget(self.titleQLabel)

        self.pictureQLabel = QLabel("Picture")
        self.pictureQLabel.setText("Picture")
        self.pictureQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self.qscrollarea = QScrollArea()
        # 禁用滚动条：图片已自动等比缩放至填满区域，无需滚动
        self.qscrollarea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.qscrollarea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.screen_width = int(self.main_window.width() * self.scale)
        self.screen_height = int(self.main_window.height() * self.scale)
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))

        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.pictureQLabel)
        self.addWidget(self.qscrollarea)

        # 监听窗口大小变化：窗口缩放时自动等比例缩放当前显示内容
        self.main_window.installEventFilter(self)

    def play(self, filePath):
        self.path = filePath
        self.titleQLabel.setText(filePath)

        # 更新标题栏：显示文件名和播放进度
        self._update_title_bar(filePath)

        # 停止任何正在进行的 GIF 定时帧切换
        self._stop_gif()

        if filePath.lower().endswith('.gif'):
            QTimer.singleShot(0, lambda: self._play_gif(filePath))
        else:
            QTimer.singleShot(0, lambda: self._play_static(filePath))

        # 播放开始后自动聚焦到播放区域（方便键盘快捷键操作）
        self.qscrollarea.setFocus()

    def _update_title_bar(self, filePath):
        """更新窗口标题栏显示文件名和播放进度"""
        basename = os.path.basename(filePath) if filePath else ""
        filename = os.path.splitext(basename)[0]
        total = len(self.inputAndExeLayout.list_files)
        if total > 0 and 0 <= self.counter < total:
            progress = f"({self.counter + 1}/{total})"
        else:
            progress = ""
        try:
            self.main_window.title_bar.setInfo(filename, progress)
        except Exception as e:
            logger.warning(f"更新标题栏失败: {e}")

    def _play_static(self, filePath):
        """播放静态图片文件"""
        try:
            fckimage = QImage(filePath)
            if fckimage.isNull():
                logger.warning(f"无法加载图片: {filePath}")
                self._advance_slideshow()
                return

            self._current_static_image = fckimage  # 保存原始图片引用用于窗口缩放时重绘
            self._render_static_image()
        except Exception as e:
            logger.error(f"静态图片显示失败: {e}")
            self._advance_slideshow()

    def _render_static_image(self):
        """根据当前窗口尺寸重新渲染静态图片（用于窗口缩放时）"""
        if not hasattr(self, '_current_static_image') or self._current_static_image is None:
            return
        try:
            # 使用 QScrollArea 视口大小（已禁用滚动条，即等于可见区域）
            viewport = self.qscrollarea.viewport()
            if viewport:
                target_w = viewport.width()
                target_h = viewport.height()
            else:
                target_w = int(self.main_window.width() * self.scale)
                target_h = int(self.main_window.height() * self.scale)

            if target_w <= 0 or target_h <= 0:
                return

            pil_image = self.m_resize(target_w, target_h, self._current_static_image)

            pixmap = QPixmap.fromImage(pil_image)

            self.pictureQLabel.resize(pil_image.width(), pil_image.height())
            self.pictureQLabel.setPixmap(pixmap)
        except Exception as e:
            logger.error(f"静态图片重绘失败: {e}")

    # ------------------------------------------------------------
    # GIF 播放：Pillow 解码 + QPixmap 帧切换 + QTimer（完全避免 Qt5 QMovie 崩溃）
    # ------------------------------------------------------------
    def _play_gif(self, filePath):
        """使用 Pillow 解码 GIF 帧，QMovie 完全不用"""
        if not os.path.isfile(filePath):
            self._advance_slideshow()
            return

        # 记录幻灯片状态并暂停
        slideshow_active = self.inputAndExeLayout.timer.isActive()
        self._gif_slideshow_active = slideshow_active
        if slideshow_active:
            self.inputAndExeLayout.timer.stop()

        # 用 Pillow 解码所有帧
        try:
            pil_img = Image.open(filePath)
            frames = []
            durations = []

            while True:
                # 当前帧 → RGBA → QImage → QPixmap
                frame_rgba = pil_img.convert("RGBA")
                data = frame_rgba.tobytes("raw", "RGBA")
                qimg = QImage(data, frame_rgba.width, frame_rgba.height, QImage.Format_RGBA8888)
                frames.append(QPixmap.fromImage(qimg))

                # 帧延迟（毫秒），PIL 返回的是百分秒（centiseconds），Qt5 QMovie 默认 100ms 兜底
                try:
                    delay = pil_img.info.get("duration", 100)
                    if delay < 20:
                        delay = 100
                except Exception:
                    delay = 100
                durations.append(delay)

                # 尝试跳到下一帧
                try:
                    pil_img.seek(pil_img.tell() + 1)
                except EOFError:
                    break

            if not frames:
                logger.warning(f"GIF 无帧: {filePath}")
                self._advance_slideshow()
                return

            self._gif_frames = frames
            self._gif_durations = durations
            self._gif_idx = 0
            self._gif_playing = True

            # 显示第一帧
            screen_w = int(self.main_window.width() * self.scale)
            screen_h = int(self.main_window.height() * self.scale)
            self.pictureQLabel.resize(screen_w, screen_h)
            self.pictureQLabel.setPixmap(self._gif_frames[0].scaled(
                screen_w, screen_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            logger.error(f"GIF 解码失败: {e}")
            self._advance_slideshow()
            return

        # 启动帧切换定时器（非信号上下文，安全）
        self._gif_timer = QTimer(self.main_window)
        self._gif_timer.setSingleShot(True)
        self._gif_timer.timeout.connect(self._advance_gif_frame)
        self._gif_timer.start(self._gif_durations[0])

    def _advance_gif_frame(self):
        """切换到 GIF 下一帧"""
        if not getattr(self, '_gif_playing', False):
            return

        self._gif_idx += 1

        # 检查是否完成一个完整循环
        if self._gif_idx >= len(self._gif_frames):
            self._gif_idx = 0

            # 幻灯片模式下，一个循环结束后切到下一张图片
            if self._gif_slideshow_active:
                self._stop_gif()
                self._advance_slideshow()
                return

        # 显示当前帧（使用视口实际尺寸）
        try:
            viewport = self.qscrollarea.viewport()
            if viewport:
                target_w = viewport.width()
                target_h = viewport.height()
            else:
                target_w = int(self.main_window.width() * self.scale)
                target_h = int(self.main_window.height() * self.scale)

            if target_w <= 0 or target_h <= 0:
                self._gif_timer.start(self._gif_durations[self._gif_idx])
                return

            self.pictureQLabel.setPixmap(self._gif_frames[self._gif_idx].scaled(
                target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            # 继续下一帧
            self._gif_timer.start(self._gif_durations[self._gif_idx])
        except Exception as e:
            logger.error(f"GIF 帧切换失败: {e}")
            self._stop_gif()

    def _advance_slideshow(self):
        """停止当前显示，启动幻灯片下一张"""
        # 停止 GIF 定时器
        self._stop_gif()

        if getattr(self, '_gif_slideshow_active', False):
            self._gif_slideshow_active = False
            self.inputAndExeLayout.timer.start()
            self.refreshPictures()

    def _stop_gif(self):
        """停止 GIF 帧切换并清理"""
        t = getattr(self, '_gif_timer', None)
        if t is not None:
            try:
                t.stop()
            except RuntimeError:
                pass
            try:
                t.timeout.disconnect()
            except (TypeError, RuntimeError):
                pass
        self._gif_timer = None
        self._gif_playing = False
        self._gif_frames = None
        self._gif_durations = None
        self._gif_idx = 0
        self.pictureQLabel.setPixmap(QPixmap())

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
        files = self.inputAndExeLayout.list_files
        if len(files) == 0:
            return
        # 边界保护：超出范围则停止幻灯片
        if self.counter < 0 or self.counter >= len(files):
            logger.info(f"幻灯片播放完毕，当前索引 {self.counter} 超出范围 (0~{len(files)-1})")
            self.inputAndExeLayout.timer.stop()
            self.counter = max(0, min(self.counter, len(files) - 1))
            return
        img_path = files[self.counter]
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

    def eventFilter(self, obj, event):
        """监听窗口大小变化事件，自动等比例缩放当前显示的图片"""
        if event.type() == QEvent.Resize:
            # 窗口缩放时重绘静态图片
            if hasattr(self, '_current_static_image') and self._current_static_image is not None:
                self._render_static_image()
            # GIF 帧缩放由 _advance_gif_frame 每次绘制时获取最新窗口尺寸处理
        return super().eventFilter(obj, event)
