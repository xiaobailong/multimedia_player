# -*- coding: utf-8 -*-
"""
图片展示布局：管理图片/幻灯片播放

已重构为使用统一的 MediaDisplayWidget 组件进行图片渲染。
支持静态图片、GIF 动画、自动缩放、幻灯片模式。
兼容 macOS 10.9+ (2013年) 和 Windows 7+
"""
import os

import send2trash
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *

from loguru import logger

from src.layout.pic_input_layout import PicInputLayout
from src.core.media_display_widget import MediaDisplayWidget, is_image_file


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
        self.titleQLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.titleQLabel.setVisible(False)  # 路径已移至窗口标题栏显示
        self.addWidget(self.titleQLabel)

        # ---- 使用统一的 MediaDisplayWidget 替代原有 QLabel + QScrollArea ----
        self.media_widget = MediaDisplayWidget(self.main_window.mainQWidget)
        self.media_widget.mediaFinished.connect(self._on_media_finished)
        self.media_widget.errorOccurred.connect(self._on_media_error)

        # 将 MediaDisplayWidget 放入 QScrollArea，由布局自动管理大小
        self.qscrollarea = QScrollArea()
        self.qscrollarea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.qscrollarea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.qscrollarea.setWidgetResizable(True)  # 让 QScrollArea 自动调整内部 widget 大小
        self.qscrollarea.setWidget(self.media_widget)
        self.addWidget(self.qscrollarea, stretch=1)  # stretch=1 让滚动区域占据剩余空间

        # 监听窗口大小变化：窗口缩放时自动缩放到 MediaDisplayWidget
        self.main_window.installEventFilter(self)

        # 幻灯片模式标志
        self._slideshow_active = False

    def play(self, filePath):
        """播放图片或 GIF"""
        self.path = filePath
        self.titleQLabel.setText(filePath)

        # 更新标题栏
        self._update_title_bar(filePath)

        if is_image_file(filePath):
            self.media_widget.playMedia(filePath)
        else:
            logger.warning(f"不支持的媒体类型: {filePath}")

        # 播放开始后自动聚焦
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

    def _on_media_finished(self):
        """媒体播放完成回调（GIF 循环完成或幻灯片切换）"""
        if self._slideshow_active:
            self._advance_slideshow()

    def _on_media_error(self, error_msg: str):
        """媒体播放错误回调"""
        logger.error(f"图片显示错误: {error_msg}")
        if self._slideshow_active:
            self._advance_slideshow()

    def _advance_slideshow(self):
        """停止当前显示，启动幻灯片下一张"""
        if self._slideshow_active:
            self.inputAndExeLayout.timer.start()
            self.refreshPictures()

    def setVisible(self, visible):
        if visible:
            # 显示时不需要手动设置几何尺寸，由布局系统自动处理
            pass
        else:
            area_rect = QRect(0, 0, self.main_window.mainQWidget.width(), self.main_window.mainQWidget.height())
            self.qscrollarea.setGeometry(area_rect)
            self.media_widget.setGeometry(area_rect)
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
        self._slideshow_active = True
        self.inputAndExeLayout.timer.start()
        self.play(self.inputAndExeLayout.list_files[self.counter])

    def startProcessWithFullScreen(self):
        self.start_process()
        self.main_window.full_screen_custom()

    def pause(self):
        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()
            self._slideshow_active = False
        else:
            self.inputAndExeLayout.timer.start()
            self._slideshow_active = True

    def delete(self):
        try:
            if not is_image_file(self.path):
                return
            (path, filename) = os.path.split(self.path)
            os.chdir(path)
            send2trash.send2trash(filename)
            self.main_window.notice(self.path + ' 文件已删除!!!')
            self.main_window.model.refresh()
        except Exception as e:
            self.main_window.notice("文件删除异常!!!" + str(e))

    def eventFilter(self, obj, event):
        """监听窗口大小变化事件，让布局系统自动处理缩放"""
        if event.type() == QEvent.Type.Resize:
            # 更新 scale 相关的屏幕尺寸（由 MediaDisplayWidget 的 resizeEvent 自动缩放）
            new_w = int(self.main_window.width() * self.scale)
            new_h = int(self.main_window.height() * self.scale)
            if new_w > 0 and new_h > 0:
                self.screen_width = new_w
                self.screen_height = new_h
        return super().eventFilter(obj, event)

    def is_pic(self, path):
        """兼容旧接口，判断是否为图片文件"""
        return is_image_file(path)