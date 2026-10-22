import os

import send2trash
from PIL import Image
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import (QPixmap, QImage, QColor)

from loguru import logger

from src.layout.pic_input_layout import PicInputLayout
from src.layout.square_close_button import SquareCloseButton


class PicShowLayout(QVBoxLayout):
    # 悬浮控制面板显隐变化，供菜单「视图 → 显示控制器」同步勾选状态
    controlPanelVisibilityChanged = pyqtSignal(bool)
    # 悬浮控制面板距图片区底部的间距（像素）
    CONTROL_PANEL_BOTTOM_MARGIN = 24

    # 暗黑透明玻璃风格：半透明底 + 细描边 + 圆角
    # （Qt5 无法做真实高斯模糊，用半透明叠色 + 描边 + 投影模拟）
    CONTROL_PANEL_QSS = """
        #picControlPanel {
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(58, 58, 80, 150),
                stop:0.5 rgba(36, 36, 54, 140),
                stop:1 rgba(22, 22, 34, 158));
            border: 1px solid rgba(205, 214, 244, 55);
            border-radius: 14px;
        }
        #picControlPanel QPushButton {
            background-color: rgba(255, 255, 255, 20);
            color: #cdd6f4;
            border: 1px solid rgba(205, 214, 244, 35);
            border-radius: 9px;
            padding: 4px 12px;
            font-size: 12px;
        }
        #picControlPanel QPushButton:hover {
            background-color: rgba(137, 180, 250, 70);
            border-color: rgba(137, 180, 250, 150);
            color: #ffffff;
        }
        #picControlPanel QPushButton:pressed {
            background-color: rgba(137, 180, 250, 120);
        }
    """

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window
        self.counter = 0
        self.path = ''
        # 右侧工作区占窗口宽度的比例（普通模式树可见时），实际渲染以 viewport 为准
        self.scale = (main_window.right * 4 + 3) / ((main_window.right + main_window.left) * 4)

        self.inputAndExeLayout = PicInputLayout(self)
        # 控制按钮不再放在顶部：改为悬浮在图片区底部居中的玻璃面板（见 _setup_control_panel）
        self.inputQWidget = QWidget()
        self.inputQWidget.setLayout(self.inputAndExeLayout)
        self.control_panel = self.inputQWidget
        self.control_panel_visible = True

        self.inputAndExeLayout.btn.pressed.connect(self.start_process)
        self.inputAndExeLayout.fullScreenBtn.pressed.connect(main_window.full_screen_custom)
        self.inputAndExeLayout.startAndFullScreenBtn.pressed.connect(self.startProcessWithFullScreen)

        self.titleQLabel = QLabel("标题")
        self.titleQLabel.setText("标题")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.titleQLabel.setVisible(False)  # 路径已移至窗口标题栏显示
        self.addWidget(self.titleQLabel)

        self.pictureQLabel = QLabel("图片")
        self.pictureQLabel.setText("图片")
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
        # 滚动区不抢焦点：否则方向键会被它吃掉（快捷键要冒泡到主窗口）
        self.qscrollarea.setFocusPolicy(Qt.NoFocus)
        self.addWidget(self.qscrollarea)

        # 悬浮控制面板：覆盖在图片区底部居中（暗黑透明玻璃效果）
        self._setup_control_panel()

        # 监听窗口大小变化：窗口缩放时自动等比例缩放当前显示内容
        self.main_window.installEventFilter(self)

    def _setup_control_panel(self):
        """把控制按钮做成悬浮在图片区底部居中、右上角带关闭徽标的暗黑玻璃面板。"""
        # 面板以 viewport 为父控件：只在图片区域内浮动，且始终盖在图片之上
        self.control_panel.setParent(self.qscrollarea.viewport())
        self.control_panel.setObjectName("picControlPanel")
        # 显式开启样式表背景绘制（对纯 QWidget 更稳妥）
        self.control_panel.setAttribute(Qt.WA_StyledBackground, True)
        self.control_panel.setStyleSheet(self.CONTROL_PANEL_QSS)

        # 关闭按钮与操作按钮同一行、排在最右侧（方形自绘样式，与视频全屏悬浮面板共用）
        self.inputAndExeLayout.setContentsMargins(12, 6, 8, 6)
        self.inputAndExeLayout.setSpacing(8)

        self.close_control_btn = SquareCloseButton(
            size=24, tooltip="隐藏控制栏（菜单「控制 → 显示控制器」可恢复）")
        self.close_control_btn.clicked.connect(self.hide_control_panel)
        self.inputAndExeLayout.addWidget(self.close_control_btn)

        try:
            shadow = QGraphicsDropShadowEffect(self.control_panel)
            shadow.setBlurRadius(26)
            shadow.setOffset(0, 4)
            shadow.setColor(QColor(0, 0, 0, 150))
            self.control_panel.setGraphicsEffect(shadow)
        except Exception as e:
            logger.warning(f"控制面板阴影效果创建失败: {e}")

        self.control_panel.show()
        self.qscrollarea.viewport().installEventFilter(self)
        QTimer.singleShot(0, self._position_control_panel)

    def _position_control_panel(self):
        """把控制面板定位到图片区底部居中。"""
        panel = getattr(self, 'control_panel', None)
        if panel is None:
            return
        viewport = self.qscrollarea.viewport()
        if viewport is None or viewport.width() <= 0 or viewport.height() <= 0:
            return
        panel.adjustSize()
        x = max(0, (viewport.width() - panel.width()) // 2)
        y = max(0, viewport.height() - panel.height() - self.CONTROL_PANEL_BOTTOM_MARGIN)
        panel.move(x, y)
        panel.raise_()

    def show_control_panel(self):
        """显示悬浮控制面板（菜单「视图 → 显示控制器」）。"""
        self.control_panel_visible = True
        self.control_panel.show()
        self.control_panel.raise_()
        self._position_control_panel()
        self.controlPanelVisibilityChanged.emit(True)

    def hide_control_panel(self):
        """隐藏悬浮控制面板（点击面板上的 ✕）。"""
        self.control_panel_visible = False
        self.control_panel.hide()
        self.controlPanelVisibilityChanged.emit(False)

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

        # 播放开始后把键盘焦点交还主窗口（方向键 / 空格等快捷键才能生效）
        self.main_window.setFocus()
        # 状态栏右侧显示该图片已有的评分（按内容指纹查库，移动 / 改名后仍能识别）
        self.main_window.refresh_rating_status(filePath)

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

            # 显示第一帧（使用视口实际尺寸，适配普通/私密模式）
            viewport = self.qscrollarea.viewport()
            if viewport:
                screen_w = viewport.width()
                screen_h = viewport.height()
            else:
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
        # 控制面板是 viewport 的子控件，随图片区一起显隐；自身显隐由 ✕ / 菜单控制
        self.titleQLabel.setVisible(False)
        self._position_control_panel()

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
        # 目录扫描在后台线程执行：列表为空时先请求扫描，
        # 扫描完成的回调（PicInputLayout._on_scan_finished）里会自动开始播放
        if len(self.inputAndExeLayout.list_files) == 0:
            self.inputAndExeLayout.load_pic_list(start_slideshow=True)
            return
        if self.counter < 0 or self.counter >= len(self.inputAndExeLayout.list_files):
            self.counter = 0
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
            # 图片区尺寸变化后重新把控制面板贴到底部居中
            self._position_control_panel()
            # GIF 帧缩放由 _advance_gif_frame 每次绘制时获取最新窗口尺寸处理
        elif event.type() == QEvent.MouseButtonPress:
            # 点到图片区域（viewport）时把键盘焦点交还主窗口，方向键快捷键才生效
            if obj is self.qscrollarea.viewport():
                self.main_window.setFocus()
        return super().eventFilter(obj, event)