"""播放进度 + 剪切范围 二合一的滑条。

背景：原来视频区有两行滑条 —— 上面是播放进度（QSlider），下面是剪切范围（QRangeSlider），
两行都表示"整段视频的时间轴"，重复占地方。这里合成一个控件：

- 白色圆点  = 播放头，点击/拖动进度条任意位置即可跳转；
- 蓝色双竖条 = 剪切范围的起点/终点，拖动它们调整剪切区间（区间用半透明蓝带高亮）；
- 左侧标签显示已播放时间，右侧标签显示总时长（由外层布局提供，控件本身不画文字）。

信号：
- `seekRequested(int)`     用户拖动/点击 → 请求跳转到该毫秒位置；
- `cutRangeChanged(int,int)` 剪切范围变化 → (起点毫秒, 终点毫秒)。
"""

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QSizePolicy, QWidget


class SeekCutSlider(QWidget):
    seekRequested = pyqtSignal(int)
    cutRangeChanged = pyqtSignal(int, int)

    HANDLE_MARGIN = 10        # 左右留白，保证 0% / 100% 处的手柄完整可见
    TRACK_HEIGHT = 6
    HANDLE_HIT_AREA = 8       # 手柄命中半径（像素）
    CUT_HANDLE_WIDTH = 8
    CUT_HANDLE_HEIGHT = 20
    PLAYHEAD_RADIUS = 6
    MIN_CUT_GAP_MS = 200      # 剪切区间最短长度，避免起点=终点

    COLOR_TRACK = QColor('#313244')
    COLOR_PLAYED = QColor('#585b70')
    COLOR_CUT_BAND = QColor(137, 180, 250, 70)
    COLOR_CUT_HANDLE = QColor('#89b4fa')
    COLOR_CUT_HANDLE_ACTIVE = QColor('#f5c2e7')
    COLOR_PLAYHEAD = QColor('#f5f5f5')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 0          # 毫秒
        self._position = 0          # 毫秒
        self._cut_start = 0
        self._cut_end = 0
        self._drag_target = None    # 'position' / 'start' / 'end'
        self.setMouseTracking(True)
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def sizeHint(self):
        return QSize(420, 28)

    def minimumSizeHint(self):
        return QSize(120, 24)

    def duration(self):
        return self._duration

    def position(self):
        return self._position

    def cutRange(self):
        return self._cut_start, self._cut_end

    def is_dragging(self):
        """正在拖动播放头（定时器此时不要再回写位置，避免打架）"""
        return self._drag_target == 'position'

    def reset(self):
        """换视频时清空（不发射信号）"""
        self._duration = 0
        self._position = 0
        self._cut_start = 0
        self._cut_end = 0
        self._drag_target = None
        self.update()

    def setDuration(self, duration):
        """设置总时长（毫秒）。时长变化时把剪切范围重置为整段视频。"""
        duration = max(0, int(duration))
        if duration == self._duration:
            return
        self._duration = duration
        self._position = min(self._position, duration)
        self._cut_start = 0
        self._cut_end = duration
        self.update()
        if duration > 0:
            self.cutRangeChanged.emit(self._cut_start, self._cut_end)

    def setPosition(self, position):
        """外部（播放定时器）同步播放位置，不发射信号"""
        if self._duration <= 0:
            return
        position = max(0, min(int(position), self._duration))
        if position == self._position:
            return
        self._position = position
        self.update()

    def setCutRange(self, start, end, emit=True):
        """设置剪切范围（毫秒），自动夹取并保证 start < end"""
        if self._duration <= 0:
            return
        start = max(0, min(int(start), self._duration))
        end = max(0, min(int(end), self._duration))
        if start > end:
            start, end = end, start
        if end - start < self.MIN_CUT_GAP_MS:
            end = min(self._duration, start + self.MIN_CUT_GAP_MS)
            if end - start < self.MIN_CUT_GAP_MS:
                start = max(0, end - self.MIN_CUT_GAP_MS)
        self._cut_start, self._cut_end = start, end
        self.update()
        if emit:
            self.cutRangeChanged.emit(start, end)

    # ------------------------------------------------------------------
    # 坐标换算
    # ------------------------------------------------------------------
    def _track_rect(self):
        width = max(1, self.width() - 2 * self.HANDLE_MARGIN)
        top = (self.height() - self.TRACK_HEIGHT) / 2.0
        return QRectF(self.HANDLE_MARGIN, top, width, self.TRACK_HEIGHT)

    def _x(self, value):
        rect = self._track_rect()
        if self._duration <= 0:
            return rect.left()
        return rect.left() + (float(value) / self._duration) * rect.width()

    def _value_at(self, x):
        rect = self._track_rect()
        if self._duration <= 0 or rect.width() <= 0:
            return 0
        ratio = (x - rect.left()) / rect.width()
        ratio = min(1.0, max(0.0, ratio))
        return int(round(ratio * self._duration))

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._track_rect()
        radius = rect.height() / 2.0

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.COLOR_TRACK)
        painter.drawRoundedRect(rect, radius, radius)

        if self._duration <= 0:
            return

        # 已播放部分
        played_width = self._x(self._position) - rect.left()
        if played_width > 0:
            painter.setBrush(self.COLOR_PLAYED)
            painter.drawRoundedRect(
                QRectF(rect.left(), rect.top(), played_width, rect.height()),
                radius, radius)

        # 剪切范围（半透明蓝带）
        cut_left = self._x(self._cut_start)
        cut_width = self._x(self._cut_end) - cut_left
        if cut_width > 0:
            painter.setBrush(self.COLOR_CUT_BAND)
            painter.drawRoundedRect(
                QRectF(cut_left, rect.top() - 3, cut_width, rect.height() + 6),
                4, 4)

        # 剪切范围两端的手柄
        for target, value in (('start', self._cut_start), ('end', self._cut_end)):
            x = self._x(value)
            color = self.COLOR_CUT_HANDLE_ACTIVE if self._drag_target == target else self.COLOR_CUT_HANDLE
            painter.setBrush(color)
            painter.drawRoundedRect(
                QRectF(x - self.CUT_HANDLE_WIDTH / 2.0,
                       rect.center().y() - self.CUT_HANDLE_HEIGHT / 2.0,
                       self.CUT_HANDLE_WIDTH, self.CUT_HANDLE_HEIGHT),
                3, 3)

        # 播放头
        painter.setBrush(self.COLOR_PLAYHEAD)
        painter.drawEllipse(QPointF(self._x(self._position), rect.center().y()),
                            self.PLAYHEAD_RADIUS, self.PLAYHEAD_RADIUS)

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._duration <= 0:
            return
        x = event.x()
        dist_start = abs(x - self._x(self._cut_start))
        dist_end = abs(x - self._x(self._cut_end))
        dist_pos = abs(x - self._x(self._position))

        if min(dist_start, dist_end) <= self.HANDLE_HIT_AREA:
            self._drag_target = 'start' if dist_start <= dist_end else 'end'
            self.update()
        else:
            # 命中不到剪切手柄时，一律当作"定位播放位置"
            self._drag_target = 'position'
            if dist_pos > self.HANDLE_HIT_AREA:
                self._seek_to(x)

    def mouseMoveEvent(self, event):
        if self._duration <= 0:
            return
        x = event.x()
        if self._drag_target == 'start':
            self.setCutRange(self._value_at(x), self._cut_end)
        elif self._drag_target == 'end':
            self.setCutRange(self._cut_start, self._value_at(x))
        elif self._drag_target == 'position':
            self._seek_to(x)
        else:
            self._update_cursor(x)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_target = None
            self.update()

    def leaveEvent(self, event):
        if self._drag_target is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def _seek_to(self, x):
        value = self._value_at(x)
        if value == self._position:
            return
        self._position = value
        self.update()
        self.seekRequested.emit(value)

    def _update_cursor(self, x):
        near_cut = (abs(x - self._x(self._cut_start)) <= self.HANDLE_HIT_AREA or
                    abs(x - self._x(self._cut_end)) <= self.HANDLE_HIT_AREA)
        if near_cut:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.PointingHandCursor)
