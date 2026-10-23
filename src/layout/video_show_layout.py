import os
import math
import time
import subprocess

import send2trash
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import QFontDatabase, QPainter, QPixmap, QColor, QPolygonF, QIcon, QPen

from loguru import logger

from src.data_manager.config_manager import ConfigManager
from src.data_manager.position_manager import PositionManager
from src.layout.floating_control_panel import FloatingControlPanel
from src.layout.media_scan_thread import (VIDEO_SUFFIXES, MediaScanThread,
                                          collect_media_files)
from src.layout.video_cut_thread import VideoCutThread
from src.layout.seek_cut_slider import SeekCutSlider
from src.utils.utils import get_ffmpeg_path as utils_get_ffmpeg_path


def _create_media_icon(paint_func, size=22, color='#cdd6f4'):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    paint_func(painter, size, color)
    painter.end()
    return QIcon(pixmap)


def _paint_play(p, s, c):
    p.setBrush(QColor(c))
    p.setPen(Qt.NoPen)
    m = s * 0.22
    pts = QPolygonF([QPointF(m, m), QPointF(s - m, s / 2), QPointF(m, s - m)])
    p.drawPolygon(pts)


def _paint_pause(p, s, c):
    p.setBrush(QColor(c))
    p.setPen(Qt.NoPen)
    w = s * 0.22
    gap = s * 0.14
    left = (s - 2 * w - gap) / 2
    p.drawRect(QRectF(left, s * 0.2, w, s * 0.6))
    p.drawRect(QRectF(left + w + gap, s * 0.2, w, s * 0.6))


def _paint_triangle_right(p, s, c):
    p.setBrush(QColor(c))
    p.setPen(Qt.NoPen)
    m = s * 0.18
    h = s - 2 * m
    w = h * 0.55
    gap = s * 0.08
    total_w = 2 * w + gap
    start_x = (s - total_w) / 2
    for i in range(2):
        x = start_x + i * (w + gap)
        pts = QPolygonF([QPointF(x, m), QPointF(x + w, s / 2), QPointF(x, s - m)])
        p.drawPolygon(pts)


def _paint_triangle_left(p, s, c):
    p.setBrush(QColor(c))
    p.setPen(Qt.NoPen)
    m = s * 0.18
    h = s - 2 * m
    w = h * 0.55
    gap = s * 0.08
    total_w = 2 * w + gap
    start_x = (s - total_w) / 2
    for i in range(2):
        x = start_x + i * (w + gap)
        pts = QPolygonF([QPointF(x + w, m), QPointF(x, s / 2), QPointF(x + w, s - m)])
        p.drawPolygon(pts)


def _paint_previous(p, s, c):
    p.setBrush(QColor(c))
    p.setPen(Qt.NoPen)
    m = s * 0.18
    h = s - 2 * m
    w = h * 0.5
    gap = s * 0.06
    bar_w = s * 0.1
    total_w = 2 * w + gap + bar_w
    start_x = (s - total_w) / 2
    x0 = start_x
    x1 = x0 + w + gap
    x_bar = x1 + w + gap
    pts0 = QPolygonF([QPointF(x0 + w, m), QPointF(x0, s / 2), QPointF(x0 + w, s - m)])
    pts1 = QPolygonF([QPointF(x1 + w, m), QPointF(x1, s / 2), QPointF(x1 + w, s - m)])
    p.drawPolygon(pts0)
    p.drawPolygon(pts1)
    p.drawRect(QRectF(x_bar, m, bar_w, s - 2 * m))


def _paint_next(p, s, c):
    p.setBrush(QColor(c))
    p.setPen(Qt.NoPen)
    m = s * 0.18
    h = s - 2 * m
    w = h * 0.5
    gap = s * 0.06
    bar_w = s * 0.1
    total_w = 2 * w + gap + bar_w
    start_x = (s - total_w) / 2
    x_bar = start_x
    x0 = x_bar + bar_w + gap
    x1 = x0 + w + gap
    p.drawRect(QRectF(x_bar, m, bar_w, s - 2 * m))
    pts0 = QPolygonF([QPointF(x0, m), QPointF(x0 + w, s / 2), QPointF(x0, s - m)])
    pts1 = QPolygonF([QPointF(x1, m), QPointF(x1 + w, s / 2), QPointF(x1, s - m)])
    p.drawPolygon(pts0)
    p.drawPolygon(pts1)


def _paint_list(p, s, c):
    p.setPen(QPen(QColor(c), s * 0.12, Qt.SolidLine, Qt.RoundCap))
    bar_w = s * 0.7
    gap = s * 0.16
    total_h = 3 * (s * 0.12) + 2 * gap
    y0 = (s - total_h) / 2 + s * 0.06
    x0 = (s - bar_w) / 2
    for i in range(3):
        y = y0 + i * (s * 0.12 + gap)
        p.drawLine(QPointF(x0, y), QPointF(x0 + bar_w, y))


def _paint_loop(p, s, c):
    p.setPen(QPen(QColor(c), s * 0.12, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    cx, cy = s / 2, s / 2
    r = s * 0.28
    start_angle = 45 * 16
    span_angle = 270 * 16
    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), start_angle, span_angle)
    arrow_size = s * 0.16
    angle_rad = math.radians(45)
    tip_x = cx + r * math.cos(angle_rad)
    tip_y = cy - r * math.sin(angle_rad)
    p.setBrush(QColor(c))
    p.setPen(Qt.NoPen)
    pts = QPolygonF([
        QPointF(tip_x, tip_y),
        QPointF(tip_x - arrow_size * 0.7, tip_y - arrow_size),
        QPointF(tip_x + arrow_size * 0.7, tip_y - arrow_size),
    ])
    p.drawPolygon(pts)


def _paint_fullscreen(p, s, c):
    m = s * 0.15
    arm = s * 0.26
    lw = s * 0.11
    p.setPen(QPen(QColor(c), lw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    corners = [
        (m, m, 1, 1),
        (s - m, m, -1, 1),
        (m, s - m, 1, -1),
        (s - m, s - m, -1, -1),
    ]
    for cx, cy, dx, dy in corners:
        p.drawLine(QPointF(cx, cy), QPointF(cx + dx * arm, cy))
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * arm))


def _paint_cut(p, s, c):
    m = s * 0.15
    r = s * 0.12
    cx, cy = s * 0.32, s * 0.3
    p.setPen(QPen(QColor(c), s * 0.1, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 0 * 16, 270 * 16)
    p.drawArc(QRectF(s - cx - r, cy - r, 2 * r, 2 * r), 180 * 16, 270 * 16)
    p.setPen(QPen(QColor(c), s * 0.09, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(cx - r, cy), QPointF(s * 0.42, s - m))
    p.drawLine(QPointF(s - cx + r, cy), QPointF(s * 0.58, s - m))
    p.drawLine(QPointF(cx - r * 1.3, cy), QPointF(s * 0.35, s - m))
    p.drawLine(QPointF(s - cx + r * 1.3, cy), QPointF(s * 0.65, s - m))


def _paint_delete(p, s, c):
    m = s * 0.13
    bw = s * 0.6
    bx = (s - bw) / 2
    p.setPen(QPen(QColor(c), s * 0.1, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(bx - s * 0.08, m + s * 0.06), QPointF(bx + bw + s * 0.08, m + s * 0.06))
    handle_x = s / 2
    p.drawLine(QPointF(handle_x - s * 0.06, m), QPointF(handle_x + s * 0.06, m))
    p.drawLine(QPointF(handle_x - s * 0.06, m), QPointF(handle_x - s * 0.06, m + s * 0.06))
    p.drawLine(QPointF(handle_x + s * 0.06, m), QPointF(handle_x + s * 0.06, m + s * 0.06))
    top = m + s * 0.1
    bot = s - m
    p.drawLine(QPointF(bx, top), QPointF(bx, bot))
    p.drawLine(QPointF(bx + bw, top), QPointF(bx + bw, bot))
    p.drawLine(QPointF(bx - s * 0.04, bot - s * 0.02), QPointF(bx + bw + s * 0.04, bot - s * 0.02))
    p.drawLine(QPointF(bx + s * 0.13, top), QPointF(bx + s * 0.13, bot - s * 0.02))
    p.drawLine(QPointF(bx + s * 0.27, top), QPointF(bx + s * 0.27, bot - s * 0.02))
    p.drawLine(QPointF(bx + s * 0.40, top), QPointF(bx + s * 0.40, bot - s * 0.02))


def _paint_screenshot(p, s, c):
    m = s * 0.14
    bw, bh = s * 0.68, s * 0.52
    bx, by = (s - bw) / 2, s * 0.28
    p.setPen(QPen(QColor(c), s * 0.1, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(bx, by, bw, bh), s * 0.06, s * 0.06)
    r = s * 0.12
    p.drawEllipse(QPointF(s / 2, by + bh / 2 + s * 0.01), r, r)
    flash_left = bx + bw * 0.68
    flash_top = by + bh * 0.05
    flash_w = bw * 0.22
    flash_h = bh * 0.22
    p.drawRoundedRect(QRectF(flash_left, flash_top, flash_w, flash_h), s * 0.03, s * 0.03)


class VideoShowLayout(QVBoxLayout):
    video_show_list_key = 'video.show.list'
    video_show_path_key = 'video.show.path'
    video_screenshot_path_key = 'video.screenshot.path'
    video_cut_path_key = 'video.cut.path'
    ffmpeg_path_key = "video.ffmpeg.path"
    play_mode_one = 0       # 单次播放
    play_mode_list = 1      # 列表播放
    play_mode_one_loop = 2  # 单视频循环播放

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window
        self.path = ''
        self.cut_start = 0
        self.cut_end = 1000
        self.play_state = False
        self.config_manager = ConfigManager()
        self.play_list = []
        self.play_list_index = 0
        self.play_mode = VideoShowLayout.play_mode_one
        self._list_reset_mode = False  # 列表播放完毕后的"重播列表"状态

        # 视频列表扫描（后台线程）：token 用于丢弃过期结果，_scan_threads 持有运行中的线程
        self._scan_token = 0
        self._scan_threads = set()

        # 播放位置记忆（使用 PositionManager 统一管理）
        self._position_save_count = 0  # 每 5 秒保存一次
        self.position_manager = PositionManager()

        self.get_ffmpeg_path()

        self.titleQLabel = QLabel("标题")
        self.titleQLabel.setText("标题")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.titleQLabel.setVisible(False)  # 路径已移至窗口标题栏显示
        self.addWidget(self.titleQLabel)

        self.player = QMediaPlayer()
        self.video_widget = QVideoWidget()
        # 方向键快捷键要能冒泡到主窗口：视频画面本身不参与键盘焦点
        self.video_widget.setFocusPolicy(Qt.NoFocus)
        self.player.setVideoOutput(self.video_widget)

        # 媒体状态变化信号：加载完成后跳转到记忆位置
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self._pending_seek_position = -1  # 待跳转的播放位置（-1 表示无跳转）
        self._pending_seek_attempts = 0   # 已重试次数（timer 后备）

        self.qscrollarea = QScrollArea()
        # 同上：滚动区域不抢焦点，否则方向键会被它吃掉（滚动条已隐藏）
        self.qscrollarea.setFocusPolicy(Qt.NoFocus)

        # Use PyQt5 QDesktopWidget instead of PIL.ImageGrab for screen size
        desktop = QApplication.desktop()
        screen_width = desktop.width()
        screen_height = desktop.height()
        self.screen_width = int(screen_width * main_window.left / (main_window.left + main_window.right))
        self.screen_height = int(screen_height * main_window.left / (main_window.left + main_window.right))
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))

        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.video_widget)

        # ---- 时间轴行：左「已播放」 + 合并滑条 + 右「总时长」 ----
        self.bar_hbox = QHBoxLayout()
        self.bar_hbox.setObjectName("bar_hbox")
        self.bar_hbox.setContentsMargins(2, 4, 2, 2)
        self.bar_hbox.setSpacing(8)

        # 左右时间用等宽字体 + 固定宽度，数字跳动时布局不抖
        time_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        time_font.setPointSize(10)

        # 左侧只显示已播放时间、右侧只显示总时长（不带「已播放/总时长」文字）
        self.bar_label = QLabel("00:00:00")
        self.bar_label.setObjectName("bar_time_current")
        self.bar_label_all = QLabel("00:00:00")
        self.bar_label_all.setObjectName("bar_time_total")
        for label, tip in ((self.bar_label, '已播放时间'), (self.bar_label_all, '视频总时长')):
            label.setFont(time_font)
            label.setFixedWidth(78)
            label.setAlignment(Qt.AlignCenter)
            label.setToolTip(tip)

        self.seek_slider = SeekCutSlider()
        self.seek_slider.setObjectName("seek_cut_slider")
        self.seek_slider.seekRequested.connect(self.on_seek_requested)
        self.seek_slider.cutRangeChanged.connect(self.on_cut_range_changed)

        self.bar_hbox.addWidget(self.bar_label)
        self.bar_hbox.addWidget(self.seek_slider, 1)
        self.bar_hbox.addWidget(self.bar_label_all)

        # ---- 预生成图标 ----
        self._play_icon = _create_media_icon(_paint_play)
        self._pause_icon = _create_media_icon(_paint_pause)
        _rewind_icon = _create_media_icon(_paint_triangle_left)
        _forward_icon = _create_media_icon(_paint_triangle_right)
        _previous_icon = _create_media_icon(_paint_previous)
        _next_icon = _create_media_icon(_paint_next)
        _list_icon = _create_media_icon(_paint_list)
        _loop_icon = _create_media_icon(_paint_loop)
        _fullscreen_icon = _create_media_icon(_paint_fullscreen)
        _cut_icon = _create_media_icon(_paint_cut)
        _delete_icon = _create_media_icon(_paint_delete)
        _screenshot_icon = _create_media_icon(_paint_screenshot)

        def _icon_btn(icon, tooltip='', min_w=36, obj_name='', checkable=False):
            btn = QPushButton()
            btn.setIcon(icon)
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(tooltip)
            btn.setMinimumWidth(min_w)
            btn.setFixedHeight(30)
            # 鼠标专用按钮：不抢键盘焦点，保证方向键等快捷键始终落到主窗口
            btn.setFocusPolicy(Qt.NoFocus)
            if obj_name:
                btn.setObjectName(obj_name)
            if checkable:
                btn.setCheckable(True)
            return btn

        # ---- 单行控制栏：播放控制 + 剪切编辑 + 工具按钮 ----
        self.controal_hbox = QHBoxLayout()
        self.controal_hbox.setObjectName("controal_hbox")
        self.controal_hbox.setContentsMargins(2, 2, 2, 2)
        self.controal_hbox.setSpacing(4)

        # -- 左：播放控制按钮组 --
        self.previous_btn = _icon_btn(_previous_icon, '上一个视频（W / ←）')
        self.previous_btn.clicked.connect(self.previous)
        self.controal_hbox.addWidget(self.previous_btn)

        self.down_btn = _icon_btn(_rewind_icon, '快退（↓）')
        self.down_btn.clicked.connect(self.down_time)
        self.controal_hbox.addWidget(self.down_btn)

        self.stop_btn = _icon_btn(self._play_icon, '播放 / 暂停（空格）', min_w=44, obj_name='video_primary_btn')
        self.stop_btn.clicked.connect(self.run_or_stop)
        self.controal_hbox.addWidget(self.stop_btn)

        self.up_btn = _icon_btn(_forward_icon, '快进（↑）')
        self.up_btn.clicked.connect(self.up_time)
        self.controal_hbox.addWidget(self.up_btn)

        self.next_btn = _icon_btn(_next_icon, '下一个视频（E / →）')
        self.next_btn.clicked.connect(self.next)
        self.controal_hbox.addWidget(self.next_btn)

        self.list_btn = _icon_btn(_list_icon, '加载 / 重播当前目录的视频列表', min_w=40)
        self.list_btn.clicked.connect(self.run_list)
        self.controal_hbox.addWidget(self.list_btn)

        self.loop_btn = _icon_btn(_loop_icon, '循环播放当前视频（按钮按下=开启）', min_w=40, checkable=True)
        self.loop_btn.toggled.connect(self._toggle_loop)
        self.controal_hbox.addWidget(self.loop_btn)

        self.controal_hbox.addStretch(1)

        # -- 中：剪切编辑区 --
        self.cut_bar_label_start = QPushButton("开始:")
        self.cut_bar_label_start.setToolTip('把剪切起点设为当前播放位置')
        self.cut_bar_label_start.clicked.connect(self.get_video_start)
        self.cut_bar_label_start.setFixedHeight(30)
        self.cut_bar_label_start.setFocusPolicy(Qt.NoFocus)
        self.controal_hbox.addWidget(self.cut_bar_label_start)

        self.cut_bar_edit_start = QLineEdit()
        self.cut_bar_edit_start.setFixedSize(QSize(100, 30))
        self.cut_bar_edit_start.setObjectName("cut_bar_label_start")
        self.cut_bar_edit_start.setText("00:00:00")
        self.cut_bar_edit_start.setCursorPosition(0)
        self.cut_bar_edit_start.setAlignment(Qt.AlignCenter)
        self.cut_bar_edit_start.setToolTip('剪切起点')
        self.controal_hbox.addWidget(self.cut_bar_edit_start)

        self.cut_bar_label_end = QPushButton("结束:")
        self.cut_bar_label_end.setToolTip('把剪切终点设为当前播放位置')
        self.cut_bar_label_end.clicked.connect(self.get_video_end)
        self.cut_bar_label_end.setFixedHeight(30)
        self.cut_bar_label_end.setFocusPolicy(Qt.NoFocus)
        self.controal_hbox.addWidget(self.cut_bar_label_end)

        self.cut_bar_edit_end = QLineEdit()
        self.cut_bar_edit_end.setFixedSize(QSize(100, 30))
        self.cut_bar_edit_end.setObjectName("cut_bar_label_end")
        self.cut_bar_edit_end.setText("00:00:00")
        self.cut_bar_edit_end.setCursorPosition(0)
        self.cut_bar_edit_end.setAlignment(Qt.AlignCenter)
        self.cut_bar_edit_end.setToolTip('剪切终点')
        self.controal_hbox.addWidget(self.cut_bar_edit_end)

        self.cut_btn = _icon_btn(_cut_icon, '按当前起止时间裁剪视频', min_w=40)
        self.cut_btn.clicked.connect(self.video_cut)
        self.controal_hbox.addWidget(self.cut_btn)

        self.controal_hbox.addStretch(1)

        # -- 右：工具按钮组 --
        self.delete_btn = _icon_btn(_delete_icon, '删除当前视频（Delete）', min_w=40)
        self.delete_btn.clicked.connect(self.delete)
        self.controal_hbox.addWidget(self.delete_btn)

        self.screenshot_button = _icon_btn(_screenshot_icon, '截取当前画面（S）', min_w=40)
        self.screenshot_button.clicked.connect(self.screenshot)
        self.controal_hbox.addWidget(self.screenshot_button)

        self.fullScreenBtn = _icon_btn(_fullscreen_icon, '全屏 / 退出全屏（F）', min_w=40)
        self.controal_hbox.addWidget(self.fullScreenBtn)
        self.fullScreenBtn.pressed.connect(main_window.full_screen_custom)

        self.bar_hbox_qwidget = QWidget()
        self.bar_hbox_qwidget.setLayout(self.bar_hbox)

        self.controal_hbox_qwidget = QWidget()
        self.controal_hbox_qwidget.setLayout(self.controal_hbox)

        self.addWidget(self.qscrollarea)
        self._control_widget_start_index = self.count()
        self.addWidget(self.bar_hbox_qwidget)
        self.addWidget(self.controal_hbox_qwidget)

        # 全屏悬浮控制面板（初始不添加控件）
        self.floating_panel = FloatingControlPanel(main_window)
        self.floating_panel.setWindowOpacity(1.0)
        self.floating_panel.hide()
        self._is_fullscreen = False

        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.onTimerOut)

        # 监听窗口大小变化：视频 QScrollArea 自适应
        self.main_window.installEventFilter(self)
        # 点视频画面时把键盘焦点交还主窗口（方向键快捷键）
        self.qscrollarea.viewport().installEventFilter(self)
        self.video_widget.installEventFilter(self)

    def enter_fullscreen_mode(self):
        """进入全屏模式：将控制控件移动到悬浮面板，只保留视频画面"""
        self._is_fullscreen = True
        # 隐藏标题（全屏时不需要显示文件路径）
        self.titleQLabel.setVisible(False)

        # 将控制控件从主布局移除并添加到悬浮面板
        self._move_controls_to_panel()

        # 显示悬浮面板
        QTimer.singleShot(500, self._show_floating_panel)

    def exit_fullscreen_mode(self):
        """退出全屏模式：恢复到普通布局"""
        self._is_fullscreen = False
        # 隐藏悬浮面板并从面板中移除控件
        self.floating_panel.hide()
        self.floating_panel.clearControlWidgets()

        # 将控制控件恢复到主布局中的正确位置
        self._restore_controls_from_panel()

        # 恢复标题显示
        self.titleQLabel.setVisible(True)
        self.bar_hbox_qwidget.setVisible(True)
        self.controal_hbox_qwidget.setVisible(True)

    def _move_controls_to_panel(self):
        """将控制控件从主布局移动到悬浮面板"""
        for w in [self.bar_hbox_qwidget, self.controal_hbox_qwidget]:
            self.removeWidget(w)
            w.setParent(None)

        self.floating_panel.addControlWidget(self.bar_hbox_qwidget)
        self.floating_panel.addControlWidget(self.controal_hbox_qwidget)
        self.bar_hbox_qwidget.setVisible(True)
        self.controal_hbox_qwidget.setVisible(True)

    def _restore_controls_from_panel(self):
        """将控制控件从悬浮面板恢复到主布局"""
        index = self._control_widget_start_index
        self.insertWidget(index, self.bar_hbox_qwidget)
        self.insertWidget(index + 1, self.controal_hbox_qwidget)

    def _show_floating_panel(self):
        """延迟显示悬浮面板（等待全屏切换完成）"""
        if not self._is_fullscreen:
            return
        self.floating_panel.resizeToFitContent()
        self.floating_panel.repositionDefault()
        self.floating_panel.setWindowOpacity(1.0)
        self.floating_panel.show()

    def previous(self):
        if len(self.play_list) == 0 or len(self.play_list) == self.play_list_index:
            self.main_window.notice('列表未加载或已全部播放完毕')
            self.play_mode = VideoShowLayout.play_mode_one
            return
        self.play_list_index -= 1
        if self.play_list_index <= 0:
            self.play_list_index = 0
        self.play(self.play_list[self.play_list_index])

    def next(self):
        if len(self.play_list) == 0 or len(self.play_list) == self.play_list_index:
            self.main_window.notice('列表未加载或已全部播放完毕')
            self.play_mode = VideoShowLayout.play_mode_one
            return
        self.play_list_index += 1
        if self.play_list_index >= len(self.play_list):
            self.play_list_index = len(self.play_list) - 1
        self.play(self.play_list[self.play_list_index])

    def run_list(self):
        # 列表还在后台扫描时点「列表」按钮：别提示"未加载"，告诉用户稍等
        if not self.play_list and any(t.isRunning() for t in self._scan_threads):
            self.main_window.notice('正在扫描视频列表（含子目录），请稍候…')
            return
        if self._list_reset_mode:
            self.play_list_index = 0
            self._list_reset_mode = False
            self.list_btn.setToolTip('加载 / 重播当前目录的视频列表')
            self.play_state = True
            self.stop_btn.setIcon(self._pause_icon)
            self.play_mode = VideoShowLayout.play_mode_list
            if len(self.play_list) > 0:
                self.play(self.play_list[0])
            return

        if len(self.play_list) == 0 or self.play_list_index >= len(self.play_list):
            self._list_reset_mode = True
            self.list_btn.setToolTip('列表已全部播放完毕，点击重播列表')
            self.main_window.notice('列表已全部播放完毕，点击"重播列表"重新播放')
            self.play_mode = VideoShowLayout.play_mode_one
            self.play_state = False
            self.stop_btn.setIcon(self._play_icon)
            return

        self.play_state = True
        self.stop_btn.setIcon(self._pause_icon)
        self.play_mode = VideoShowLayout.play_mode_list
        self.play(self.play_list[self.play_list_index])

    def up_time(self):
        num = self.player.position() + int(self.player.duration() / 100)
        self.player.setPosition(num)
        self.onTimerOut()

    def down_time(self):
        num = self.player.position() - int(self.player.duration() / 80)
        self.player.setPosition(num)
        self.onTimerOut()

    def pause(self):
        if self.play_state:
            self._save_position()
            self.player.pause()
            self.play_state = False
            self.stop_btn.setIcon(self._play_icon)
        else:
            self.player.play()
            self.play_state = True
            self.stop_btn.setIcon(self._pause_icon)

    def run_or_stop(self):
        if self.play_state:
            self._save_position()
            self.player.pause()
            self.timer.stop()
            self.play_state = False
            self.stop_btn.setIcon(self._play_icon)
        else:
            if self.player.position() < self.player.duration():
                self.player.play()
                self.timer.start()
                self.play_state = True
                self.stop_btn.setIcon(self._pause_icon)
            else:
                self.timer.start()
                self.seek_slider.setPosition(0)
                self.player.setPosition(0)
                self.player.play()

    def play(self, filePath):
        self.titleQLabel.setText(filePath)
        self.path = filePath

        # 换视频：清空合并滑条（播放位置 0 / 剪切范围等时长确定后再重置为整段）
        self.seek_slider.reset()
        self.bar_label.setText("00:00:00")
        self.bar_label_all.setText("00:00:00")

        # 更新标题栏：显示文件名和播放进度
        self._update_title_bar(filePath)

        # 先加载上次播放位置（必须在 setMedia 之前，因为 durationChanged 信号可能在
        # setMedia 时立刻触发，需要 _pending_seek_position 已就绪）
        saved_pos = self._load_position()
        self._pending_seek_position = saved_pos if saved_pos > 0 else -1
        if saved_pos > 0:
            self.main_window.notice(f"正在恢复上次播放位置...")

        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(r'' + filePath)))
        self.player.play()
        self.play_state = True
        self.stop_btn.setIcon(self._pause_icon)

        self.timer.start()

        # 播放开始后把键盘焦点交还主窗口（方向键 / 空格等快捷键才能生效）
        self.main_window.setFocus()
        # 状态栏右侧显示该视频已有的评分（按内容指纹查库，移动 / 改名后仍能识别）
        self.main_window.refresh_rating_status(filePath)

    def _update_title_bar(self, filePath):
        """更新窗口标题栏显示文件名和播放进度"""
        basename = os.path.basename(filePath) if filePath else ""
        filename = os.path.splitext(basename)[0]
        total = len(self.play_list)
        if total > 0 and 0 <= self.play_list_index < total:
            progress = f"({self.play_list_index + 1}/{total})"
        else:
            progress = ""
        try:
            self.main_window.title_bar.setInfo(filename, progress)
        except Exception as e:
            logger.warning(f"更新标题栏失败: {e}")

    def refresh_title_bar(self):
        """按当前视频 / 列表位置刷新标题栏（切到视频模式时调用）。

        没播放过视频时回到默认标题，不残留图片文件名的幻灯片进度。
        """
        if not self.path:
            self.main_window.title_bar.setInfo('', '')
            return
        self._update_title_bar(self.path)

    def _seek_to_saved_position(self, saved_pos, duration=None):
        """
        跳转到保存的播放位置。
        
        Args:
            saved_pos: 要跳转的位置（毫秒）
            duration: 当前视频时长（毫秒），可选。传 None 时从 player.duration() 获取
        """
        if duration is None:
            duration = self.player.duration()
        if saved_pos > 0 and saved_pos < duration:
            self.player.setPosition(saved_pos)
            self.main_window.notice(f"已恢复上次播放位置")
            return True
        return False

    def _on_media_status_changed(self, status):
        """
        媒体状态变化时，尝试执行待跳转。
        QMediaPlayer 状态枚举：
            2=LoadingMedia, 3=LoadedMedia, 4=StalledMedia, 
            5=BufferingMedia, 6=BufferedMedia, 7=EndOfMedia, 8=InvalidMedia
        macOS AVFoundation 上，bufferedMedia(6) 是确认媒体已完全可操作的最佳时机。
        """
        if self._pending_seek_position > 0:
            if status in (QMediaPlayer.BufferedMedia, QMediaPlayer.LoadedMedia):
                # 延迟 200ms 确保播放器内部状态已就绪，setPosition 不会丢失
                QTimer.singleShot(200, lambda: self._try_pending_seek())
        elif status in (QMediaPlayer.InvalidMedia, QMediaPlayer.EndOfMedia):
            self._pending_seek_position = -1

    def _on_duration_changed(self, duration):
        """
        durationChanged 作为 _on_media_status_changed 的后备。
        如果 _pending_seek_position 还未被消费，在此处触发延迟跳转。
        """
        # 时长确定后同步合并滑条与右侧总时长（剪切范围自动重置为整段）
        self.seek_slider.setDuration(duration)
        if duration > 0:
            self.bar_label_all.setText(self._format_time(duration))

        if self._pending_seek_position > 0 and duration > 0:
            QTimer.singleShot(200, lambda: self._try_pending_seek())

    @staticmethod
    def _format_time(milliseconds):
        """毫秒 → HH:MM:SS"""
        m, s = divmod(int(milliseconds) / 1000, 60)
        h, m = divmod(m, 60)
        return "%02d:%02d:%02d" % (h, m, s)

    @staticmethod
    def _set_time_edit(edit, text):
        """写入时间文本。

        QLineEdit.setText() 会把光标放到末尾，窄输入框会因此横向滚动，
        看起来像"首字符被裁掉"；写入后把光标移回开头即可固定显示完整时间。
        """
        if edit.text() == text:
            return
        edit.setText(text)
        edit.setCursorPosition(0)

    def on_seek_requested(self, position):
        """合并滑条：用户点击/拖动播放头 → 跳转（不改变播放/暂停状态）"""
        duration = self.player.duration()
        if duration <= 0:
            return
        position = max(0, min(int(position), duration))
        self.player.setPosition(position)
        self.seek_slider.setPosition(position)
        self.bar_label.setText(self._format_time(position))

    def on_cut_range_changed(self, start, end):
        """合并滑条：剪切范围变化 → 同步 cut_start/cut_end 与两个时间输入框"""
        self.cut_start = int(start // 1000)
        self.cut_end = int(end // 1000)
        self._set_time_edit(self.cut_bar_edit_start, self._format_time(start))
        self._set_time_edit(self.cut_bar_edit_end, self._format_time(end))

    def _try_pending_seek(self):
        """
        执行待跳转。仅当播放器处于 BufferedMedia/LoadedMedia 状态时才跳转，
        否则延迟重试。macOS AVFoundation 在 Loading 状态下调用 setPosition 会被忽略。
        """
        if self._pending_seek_position <= 0:
            return
        
        # 检查播放器状态：仅在 BufferedMedia(6) 或 LoadedMedia(3) 时才能安全 seek
        media_status = self.player.mediaStatus()
        if media_status not in (QMediaPlayer.BufferedMedia, QMediaPlayer.LoadedMedia):
            # 每秒重试一次，最多重试 5 次
            self._pending_seek_attempts += 1
            if self._pending_seek_attempts <= 5:
                QTimer.singleShot(1000, self._try_pending_seek)
            else:
                logger.warning(f"等待播放器就绪超时，放弃跳转 position={self._pending_seek_position}")
                self._pending_seek_position = -1
            return
        
        saved_pos = self._pending_seek_position
        self._pending_seek_position = -1  # 清除标记，避免重复跳转
        self._pending_seek_attempts = 0
        success = self._seek_to_saved_position(saved_pos)
        if success:
            logger.info(f"已恢复上次播放位置: {saved_pos}")

    def onTimerOut(self):
        position = self.player.position()
        duration = self.player.duration()

        if duration == 0:
            return

        # 合并滑条：定时器同步播放位置（用户正在拖动播放头时不抢），并刷新左右时间标签
        if self.seek_slider.duration() != duration:
            self.seek_slider.setDuration(duration)
        if not self.seek_slider.is_dragging():
            self.seek_slider.setPosition(position)
        self.bar_label.setText(self._format_time(position))
        self.bar_label_all.setText(self._format_time(duration))

        # 每 5 秒保存一次播放位置
        self._position_save_count += 1
        if self._position_save_count >= 5:
            self._position_save_count = 0
            self._save_position()

        if self.player.position() == self.player.duration():
            if self.play_mode == VideoShowLayout.play_mode_list:
                self.play_list_index += 1
                self.run_list()
                return
            elif self.play_mode == VideoShowLayout.play_mode_one_loop:
                self.player.setPosition(0)
                self.player.play()
                self.play_state = True
                self.stop_btn.setIcon(self._pause_icon)
                return
            self.stop_btn.setIcon(self._play_icon)
            self.play_state = False
            self.timer.stop()

    def _toggle_loop(self, checked):
        """切换单视频循环模式"""
        if checked:
            self.play_mode = VideoShowLayout.play_mode_one_loop
            self.main_window.notice("已开启单曲循环")
        else:
            self.play_mode = VideoShowLayout.play_mode_one
            self.main_window.notice("已关闭单曲循环")

    def is_video(self, path):
        return bool(path) and path.lower().endswith(VIDEO_SUFFIXES)

    def setVisible(self, visible):
        self.titleQLabel.setVisible(visible)
        self.video_widget.setStyleSheet("border:none;")
        self.bar_hbox_qwidget.setVisible(visible)
        self.controal_hbox_qwidget.setVisible(visible)

    def screenshot(self):
        try:
            (path, filename) = os.path.split(self.path)
            (file, ext) = os.path.splitext(filename)
            new_path = os.path.expanduser('~') + os.sep + 'Downloads' + os.sep + file + '_'
            if self.config_manager.exist(VideoShowLayout.video_screenshot_path_key):
                new_path = self.config_manager.get(VideoShowLayout.video_screenshot_path_key) + os.sep + file + '_'

            save_path = new_path + '_' + str(self.player.position()) + '.jpg'

            ffmpeg_path = self.get_ffmpeg_path()
            if not os.path.exists(ffmpeg_path):
                self.main_window.notice('ffmpeg路径获取错误： ' + ffmpeg_path)
                return

            position_sec = self.player.position() / 1000
            command = [
                ffmpeg_path,
                '-ss', str(position_sec),
                '-i', self.path,
                '-vframes', '1',
                '-q:v', '2',
                '-y',
                save_path
            ]
            subprocess.run(command, capture_output=True, timeout=30)

            if os.path.exists(save_path):
                self.main_window.notice('截图成功，保存到 ' + save_path)
                self.main_window.model.refresh()
            else:
                self.main_window.notice("截图失败!!!")
        except subprocess.TimeoutExpired:
            self.main_window.notice("截图超时!!!")
        except Exception as e:
            logger.error(f"截图失败: {e}")
            self.main_window.notice(f"截图失败: {e}")

    def get_video_start(self):
        # 「开始:」= 把剪切起点设为当前播放位置（合并滑条的左端手柄）
        _, end = self.seek_slider.cutRange()
        self.seek_slider.setCutRange(self.player.position(), end)

    def get_video_end(self):
        # 「结束:」= 把剪切终点设为当前播放位置（合并滑条的右端手柄）
        start, _ = self.seek_slider.cutRange()
        self.seek_slider.setCutRange(start, self.player.position())

    def video_cut(self):
        (path, filename) = os.path.split(self.path)
        (file, ext) = os.path.splitext(filename)
        new_path = os.path.expanduser('~') + os.sep + 'Downloads' + os.sep + file + '_'
        if self.config_manager.exist(VideoShowLayout.video_cut_path_key):
            new_path = self.config_manager.get(VideoShowLayout.video_cut_path_key) + os.sep + file + '_'

        file_name = new_path + self.cut_bar_edit_start.text().replace(':',
                                                                      '') + '-' + self.cut_bar_edit_end.text().replace(
            ':', '') + ext
        ffmpeg_path = self.get_ffmpeg_path()
        if not os.path.exists(ffmpeg_path):
            self.main_window.notice('ffmpeg路径获取错误： ' + ffmpeg_path)
            return
        get_video_max_time = self.get_video_max_time()
        if self.cut_bar_edit_start.text() >= self.cut_bar_edit_end.text() or self.cut_bar_edit_end.text() > get_video_max_time:
            self.main_window.notice(
                '时间设置错误： ' + self.cut_bar_edit_start.text() + '-' + self.cut_bar_edit_end.text())
            return
        command = ffmpeg_path + ' -ss ' + self.cut_bar_edit_start.text() + ' -to ' + self.cut_bar_edit_end.text() + ' -i "' + self.path + '" -vcodec copy -acodec copy "' + file_name + '"'
        logger.info(command)

        self.video_cut_thread = VideoCutThread(command, file_name)
        self.video_cut_thread.finished.connect(self.video_cut_thread_finished)
        self.video_cut_thread.start()

    def get_video_max_time(self):
        m, s = divmod(self.player.duration() / 1000, 60)
        h, m = divmod(m, 60)
        return "%02d:%02d:%02d" % (h, m, s)

    def get_ffmpeg_path(self):
        if self.config_manager.exist(self.ffmpeg_path_key):
            ffmpeg_path = self.config_manager.get(self.ffmpeg_path_key)
            if os.path.exists(ffmpeg_path):
                return ffmpeg_path
            else:
                self.config_manager.remove(self.ffmpeg_path_key)

        ffmpeg_path = utils_get_ffmpeg_path()
        if os.path.exists(ffmpeg_path):
            if not self.config_manager.exist(self.ffmpeg_path_key):
                self.config_manager.add_or_update(self.ffmpeg_path_key, ffmpeg_path)
            return ffmpeg_path

        path_env = os.environ.get('PATH') or os.environ.get('Path', '')
        for item in path_env.split(os.pathsep):
            candidate = os.path.join(item, 'ffmpeg')
            if os.path.exists(candidate):
                if not self.config_manager.exist(self.ffmpeg_path_key):
                    self.config_manager.add_or_update(self.ffmpeg_path_key, candidate)
                return candidate

        return ffmpeg_path

    def video_cut_thread_finished(self, file_name, count):
        while not os.path.exists(file_name):
            if count > 60:
                return
            time.sleep(1)
            if os.path.exists(file_name):
                self.main_window.notice('视频剪切成功，保存到 ' + file_name)
                self.main_window.model.refresh()
                return
            count + -1

    def loadData(self, path):
        """加载目录下的视频列表：递归包含子目录，后台扫描，按修改时间升序。

        扫描放后台线程（`MediaScanThread`），避免大目录把 GUI 卡成"未响应"（`ISSUE-007`）；
        连续切换目录时旧扫描会被中断，只接受最新一次请求的结果。
        """
        self._scan_token += 1
        token = self._scan_token
        self._interrupt_scans()

        if len(self.play_list) > 0:
            self.play_list.clear()
            self.play_list_index = 0

        self._list_reset_mode = False
        self.list_btn.setToolTip('加载 / 重播当前目录的视频列表（含子目录）')

        if not path or not os.path.isdir(path):
            logger.warning(f'视频列表目录无效: {path}')
            return

        thread = MediaScanThread(token, path, VIDEO_SUFFIXES)
        self._scan_threads.add(thread)
        thread.scanned.connect(self._on_list_scanned)
        thread.finished.connect(lambda t=thread: self._scan_threads.discard(t))
        thread.finished.connect(thread.deleteLater)
        thread.start()
        logger.info(f'开始扫描视频目录: {path}')
        if self.main_window is not None:
            self.main_window.notice('正在扫描视频列表（含子目录）：' + path)

    def _interrupt_scans(self):
        """中断正在运行的扫描线程（不改变 token）。"""
        for thread in list(self._scan_threads):
            try:
                thread.requestInterruption()
            except RuntimeError:
                continue

    def cancel_scan(self, wait_ms=0):
        """放弃正在进行的列表扫描（关闭窗口时调用，避免 QThread 未结束就被销毁）。"""
        self._scan_token += 1
        for thread in list(self._scan_threads):
            try:
                thread.requestInterruption()
            except RuntimeError:
                continue
            if wait_ms:
                thread.wait(wait_ms)

    def _on_list_scanned(self, token, path, files):
        """后台扫描完成：只接受最新一次请求的结果。"""
        if token != self._scan_token:
            logger.info(f'忽略过期的视频扫描结果: {path}')
            return
        self.play_list.clear()
        self.play_list.extend(files)
        self.play_list_index = 0
        self._list_reset_mode = False
        logger.info(f'视频扫描完成: {path} 共 {len(files)} 个')
        if self.main_window is not None:
            self.main_window.notice('视频列表已加载：%d 个（含子目录）' % len(files))

    def delete(self):
        if len(self.path) > 0 and self.is_video(self.path):
            (path, filename) = os.path.split(self.path)
            deleted_file_path = self.path
            deleted_file_index = -1
            # 记录被删除文件在播放列表中的位置
            for i, p in enumerate(self.play_list):
                if p == deleted_file_path:
                    deleted_file_index = i
                    break
            # 从播放列表中移除被删除的文件
            if deleted_file_index >= 0:
                self.play_list.pop(deleted_file_index)
                if self.play_list_index > deleted_file_index:
                    self.play_list_index -= 1
                elif self.play_list_index == deleted_file_index:
                    # 当前播放的被删除了，尝试播放下一个
                    if self.play_list_index >= len(self.play_list):
                        self.play_list_index = len(self.play_list) - 1

            # 释放媒体资源，删除和播放下一个延迟到媒体释放完成后执行
            self.player.setMedia(QMediaContent())
            self.player.setVideoOutput(None)
            QTimer.singleShot(200, lambda: self._do_delete(path, filename, deleted_file_path))
        else:
            self.next()

    def _save_position(self):
        """保存当前播放位置到数据库"""
        if not self.path or not os.path.exists(self.path):
            return
        position = self.player.position()
        duration = self.player.duration()
        self.position_manager.save_position(self.path, position, duration)

    def _load_position(self):
        """从数据库加载上次播放位置，返回 position（毫秒），无记录则返回 0"""
        return self.position_manager.load_position(self.path)

    def eventFilter(self, obj, event):
        """监听窗口大小变化事件，视频 QVideoWidget 自适应"""
        if event.type() == QEvent.Resize:
            # QScrollArea 的 setWidgetResizable(True) 会自动处理
            pass  # 交由 QScrollArea 自身处理自适应
        elif event.type() == QEvent.MouseButtonPress:
            # 点到视频画面 / 滚动区时把键盘焦点交还主窗口，方向键快捷键才生效
            if obj in (self.video_widget, self.qscrollarea.viewport()):
                self.main_window.setFocus()
        return super().eventFilter(obj, event)

    def _do_delete(self, path, filename, deleted_file_path):
        """实际执行文件删除并播放下一个（在媒体释放后调用）"""
        try:
            # 清理数据库中的播放位置记录
            self.position_manager.delete_position(deleted_file_path)

            os.chdir(path)
            send2trash.send2trash(filename)
            self.main_window.notice(deleted_file_path + ' 文件已删除!!!')
            self.main_window.model.refresh()

            # 首先尝试从播放列表播放下一个
            if len(self.play_list) > 0 and 0 <= self.play_list_index < len(self.play_list):
                self.player.setVideoOutput(self.video_widget)
                self.play(self.play_list[self.play_list_index])
            else:
                # 播放列表为空：只看当前目录这一层（同步扫、很快），按修改时间找下一个视频
                candidates = collect_media_files(path, VIDEO_SUFFIXES, recursive=False)
                file_date_tuple_list = [(x, os.path.getmtime(x)) for x in candidates]

                # 找到删除文件的位置，播放下一个
                found = False
                next_file = None
                for file in file_date_tuple_list:
                    if found:
                        next_file = file[0]
                        break
                    if file[0] == deleted_file_path:
                        found = True

                # 如果没有下一个，播放下一个前一个
                if not next_file and len(file_date_tuple_list) > 0:
                    next_file = file_date_tuple_list[-1][0]

                if next_file and os.path.exists(next_file):
                    self.player.setVideoOutput(self.video_widget)
                    self.play(next_file)
                else:
                    self.player.setVideoOutput(self.video_widget)
        except Exception as e:
            self.player.setVideoOutput(self.video_widget)
            self.main_window.notice("文件删除异常!!!" + str(e))