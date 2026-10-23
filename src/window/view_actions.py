# -*- coding: utf-8 -*-
"""窗口显示相关的动作：全屏切换、快捷键、窗口状态、显示切换、关闭清理。

``keyPressEvent`` / ``closeEvent`` / ``eventFilter`` / ``changeEvent`` 这些
Qt 虚函数要求本 mixin 排在 ``QMainWindow`` 之前（MRO），否则会被基类实现遮蔽。
"""
import os

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtMultimedia import QMediaContent
from PyQt5.QtWidgets import QApplication
from loguru import logger

from src.window.theme import CENTRAL_WIDGET_FULLSCREEN_STYLE, CENTRAL_WIDGET_STYLE


class ViewActionsMixin:
    """全屏 / 快捷键 / 窗口状态 / 普通与私密显示切换。"""

    def change_screen_full(self):
        if self.full_screen_state % 2 == self.full:
            self.full_screen_custom()
        else:
            self.screen_normal()

    def screen_normal(self):
        # 先退出全屏模式（将控制控件从悬浮面板恢复到主布局）
        if hasattr(self, 'video_show_layout') and self.video_show_layout._is_fullscreen:
            self.video_show_layout.exit_fullscreen_mode()

        if self.video_show_qwidget.isVisible():
            self.video_show_layout.setVisible(True)
        if self.pic_show_qwidget.isVisible():
            self.pic_show_layout.setVisible(True)
        if self.private_mode:
            self.treeView.setVisible(False)
            self.private_tree_view.setVisible(True)
        else:
            self.treeView.setVisible(True)
        self.statusbar.setVisible(True)
        # 恢复标题栏
        self.title_bar.setVisible(True)
        # 恢复菜单栏（全屏时被隐藏）
        self.menu_bar.setVisible(True)
        self._central_widget.setStyleSheet(CENTRAL_WIDGET_STYLE)
        self.mainQWidget.setStyleSheet(self.style_sheet)
        self.full_screen_state = self.normal

        # 如果全屏前是最大化状态，恢复最大化
        if getattr(self, '_was_maximized_before_fullscreen', False):
            self.showMaximized()
        elif hasattr(self, 'normal_rect'):
            x, y, w, h = self.normal_rect
            self.showNormal()
            # macOS 退出原生全屏有动画，动画完成后会重置窗口尺寸
            # 延迟 1 秒确保动画完全结束后再恢复原始大小和位置
            QTimer.singleShot(1000, lambda: self.setGeometry(x, y, w, h))
        else:
            self.showNormal()

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_Escape):
            self.full_screen_state = self.normal
            self.screen_normal()
        if (event.key() == Qt.Key_Left):
            # ← 上一个：图片 / 视频都支持
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.down()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.previous()
        if (event.key() == Qt.Key_Right):
            # → 下一个：图片 / 视频都支持
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.up()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.next()
        if (event.key() == Qt.Key_Up):
            # ↑ 快进：仅视频
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.up_time()
        if (event.key() == Qt.Key_Down):
            # ↓ 快退：仅视频
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.down_time()
        if (event.key() == Qt.Key_Space):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.pause()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.pause()
        if (event.key() == Qt.Key_W):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.previous()
        if (event.key() == Qt.Key_E):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.next()
        if (event.key() == Qt.Key_F):
            self.full_screen_state += 1
            self.change_screen_full()
        if (event.key() == Qt.Key_Delete):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.delete()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.delete()
        elif (event.key() == Qt.Key_D and QApplication.keyboardModifiers() == Qt.ControlModifier):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.delete()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.delete()
        elif (event.key() == Qt.Key_D):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.up()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.up_time()
        if (event.key() == Qt.Key_A):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.down_time()
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.down()
        if (event.key() == Qt.Key_S):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.screenshot()
        if (event.key() == Qt.Key_Z):
            self.video_show_layout.get_video_start()
        if (event.key() == Qt.Key_X):
            self.video_show_layout.get_video_end()
        if (event.key() == Qt.Key_C):
            self.video_show_layout.video_cut()
        if (event.key() == Qt.Key_B) and QApplication.keyboardModifiers() == Qt.ControlModifier:
            self.toggle_tree()
        # 数字键 1~5：给当前图片 / 视频评分（小键盘数字是 Key_1~5 + KeypadModifier，同样命中）
        if Qt.Key_0 <= event.key() <= Qt.Key_9:
            digit = event.key() - Qt.Key_0
            modifiers = QApplication.keyboardModifiers()
            if 1 <= digit <= 5 and not (modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier)):
                self._apply_rating(digit)
        if (event.key() == Qt.Key_O) and QApplication.keyboardModifiers() == Qt.ShiftModifier:
            self.notice("快捷键：Shift + O")

    def full_screen_custom(self):
        if self.video_show_qwidget.isVisible():
            self.video_show_layout.setVisible(False)
        if self.pic_show_qwidget.isVisible():
            self.pic_show_layout.setVisible(False)

        self.treeView.setVisible(False)
        self.private_tree_view.setVisible(False)
        self.statusbar.setVisible(False)
        # 隐藏标题栏
        self.title_bar.setVisible(False)
        # 全屏时隐藏菜单栏（Esc / F 退出全屏后恢复）
        self.menu_bar.setVisible(False)
        self._central_widget.setStyleSheet(CENTRAL_WIDGET_FULLSCREEN_STYLE)
        self.mainQWidget.setStyleSheet("border:none;")
        self.full_screen_state = self.full
        # 保存窗口状态用于退出全屏时恢复（支持正常/最大化/全屏等多种状态）
        self._saved_window_state = self.saveGeometry()
        # 如果当前是最大化状态，额外保存客户区几何参数用于 setGeometry 恢复
        if self.isMaximized():
            self._was_maximized_before_fullscreen = True
            # 先取消最大化获取正常几何参数
            self.showNormal()
            self.normal_rect = (self.x(), self.y(), self.width(), self.height())
            # 再回到最大化状态以便进入全屏
            self.showMaximized()
        else:
            self._was_maximized_before_fullscreen = False
            self.normal_rect = (self.x(), self.y(), self.width(), self.height())
        self.showFullScreen()

        # 视频全屏时使用悬浮控制面板
        if self.video_show_qwidget.isVisible():
            QTimer.singleShot(300, self.video_show_layout.enter_fullscreen_mode)

    def change_show(self, show_type):
        if show_type == self.show_type_pic:
            self.pic_show_qwidget.setVisible(True)
            self.video_show_qwidget.setVisible(False)
        if show_type == self.show_type_video:
            self.video_show_qwidget.setVisible(True)
            self.pic_show_qwidget.setVisible(False)
            # 图片区已经被隐藏：必须停掉幻灯片 / GIF 定时器，
            # 否则图片会在后台继续翻页（改写窗口标题、状态栏评分）
            self.pic_show_layout.pause_slideshow()
        # 切换显示后，状态栏右侧跟着显示对应媒体的评分
        self.refresh_rating_status()

    def closeEvent(self, event):
        """关闭窗口时清理视频播放器资源，防止 macOS AVFoundation 崩溃"""
        # 停止后台目录扫描线程，避免退出时 QThread 仍在运行
        if hasattr(self, 'inputAndExeLayout'):
            self.inputAndExeLayout.cancel_scan(wait_ms=1500)
        # 停止后台归集线程（扫描 / 拷贝）
        if getattr(self, 'collect_thread', None) is not None and self.collect_thread.isRunning():
            self.collect_thread.cancel()
            self.collect_thread.wait(3000)
        if hasattr(self, 'video_show_layout'):
            # 关闭前先保存当前播放位置（无论是否处于暂停状态）
            if self.video_show_layout.path and os.path.exists(self.video_show_layout.path):
                pos = self.video_show_layout.player.position()
                dur = self.video_show_layout.player.duration()
                self.video_show_layout.position_manager.save_position(
                    self.video_show_layout.path, pos, dur
                )

            if self.video_show_layout.timer.isActive():
                self.video_show_layout.timer.stop()
            # 停止播放并释放媒体资源
            self.video_show_layout.player.stop()
            self.video_show_layout.player.setMedia(QMediaContent())
            # 断开视频输出，防止 CVDisplayLink 回调访问已释放对象
            self.video_show_layout.player.setVideoOutput(None)

        # 退出时清掉私密模式的解密缓存（明文不应落盘留存）
        try:
            if hasattr(self, 'private_service'):
                self.private_service.clear_cache()
                self.private_service.close()
        except Exception as e:
            logger.warning(f'退出时清理私密缓存失败: {e}')

        event.accept()

    def toggle_tree(self):
        if self.private_mode:
            return
        if self.tree_visible:
            self.tree_sizes = self.mainQWidget.sizes()
            self.treeView.setVisible(False)
            self.tree_visible = False
        else:
            self.treeView.setVisible(True)
            self.tree_visible = True
            self.mainQWidget.setSizes(self.tree_sizes)
        if hasattr(self, 'toggle_tree_action'):
            self.toggle_tree_action.setChecked(self.tree_visible)

    def eventFilter(self, obj, event):
        """全局事件过滤器：全屏模式下始终能捕获键盘快捷键，不受焦点控件影响"""
        if event.type() == QEvent.KeyPress:
            # Esc：退出全屏
            if event.key() == Qt.Key_Escape and self.full_screen_state == self.full:
                self.full_screen_state = self.normal
                self.screen_normal()
                return True
            # M：全屏时切换悬浮控制面板显示/隐藏
            if event.key() == Qt.Key_M and self.full_screen_state != self.normal:
                if hasattr(self, 'video_show_layout') and hasattr(self.video_show_layout, 'floating_panel'):
                    panel = self.video_show_layout.floating_panel
                    if panel.isVisible():
                        panel.hide_panel()
                    else:
                        panel.resizeToFitContent()
                        panel.repositionDefault()
                        panel.show_panel()
                return True
        return super().eventFilter(obj, event)

    def _on_restored(self):
        """从最大化还原后更新标题栏按钮图标"""
        self.title_bar.updateMaximizeIcon()

    def changeEvent(self, event):
        """窗口状态变化时更新标题栏按钮图标"""
        if event.type() == QEvent.WindowStateChange:
            self.title_bar.updateMaximizeIcon()
        super().changeEvent(event)

    def notice(self, content):
        self.statusLabel.setText(content)
