# -*- coding: utf-8 -*-
"""统一风格的对话框（与主窗口同一套深色主题、同样无系统标题栏）。

主窗口是「无边框 + 自定义标题栏」的；如果弹框继续用系统标题栏，
深色界面里就会冒出浅色的 Windows 标题栏，风格割裂。这里统一提供：

- :class:`StyledDialog`      无边框圆角外壳 + 自定义标题栏（可拖动、✕ 关闭、Esc 关闭）
- :class:`MessageDialog`     信息 / 警告 / 错误 / 询问
- :class:`AboutDialog`       关于（富文本）
- :class:`StyledFileDialog`  把 ``QFileDialog`` 嵌进统一外壳（禁用原生文件框）
- :class:`ProgressDialog`    带取消按钮的进度框

以及便捷函数 :func:`show_info` / :func:`show_warning` / :func:`show_error` /
:func:`ask_yes_no` / :func:`show_about` / :func:`pick_directory` / :func:`pick_open_file`。
"""
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFileDialog, QProgressBar,
                             QGraphicsDropShadowEffect, QApplication)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from src.layout.square_close_button import SquareCloseButton


# 阴影外扩留白（窗口半透明区域，用来放投影）
SHADOW_MARGIN = 14

DIALOG_QSS = """
    #dialogRoot {
        background-color: #1e1e2e;
        border: 1px solid #45475a;
        border-radius: 10px;
    }
    #dialogTitleBar {
        background-color: #181825;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        border-bottom: 1px solid #313244;
    }
    #dialogTitle {
        background: transparent;
        color: #cdd6f4;
        font-size: 13px;
        font-weight: bold;
    }
    #dialogBody {
        background: transparent;
    }
    #dialogText {
        background: transparent;
        color: #cdd6f4;
        font-size: 13px;
    }
    QPushButton#dialogPrimaryBtn {
        background-color: #89b4fa;
        color: #1e1e2e;
        border: 1px solid #89b4fa;
        border-radius: 4px;
        padding: 4px 14px;
        min-height: 22px;
        font-size: 13px;
        font-weight: bold;
    }
    QPushButton#dialogPrimaryBtn:hover {
        background-color: #b4d0fb;
        border-color: #b4d0fb;
    }
    QPushButton#dialogPrimaryBtn:pressed {
        background-color: #74c7ec;
        border-color: #74c7ec;
    }
    QProgressBar {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
        min-height: 14px;
        text-align: center;
        font-size: 11px;
    }
    QProgressBar::chunk {
        background-color: #89b4fa;
        border-radius: 3px;
    }
    QFileDialog QTreeView, QFileDialog QListView {
        background-color: #181825;
        color: #cdd6f4;
        border: 1px solid #313244;
        border-radius: 4px;
    }
    QFileDialog QTreeView::item:selected, QFileDialog QListView::item:selected {
        background-color: #89b4fa;
        color: #1e1e2e;
    }
    QFileDialog QComboBox, QFileDialog QLineEdit {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
    }
    QFileDialog QToolButton {
        background: transparent;
        border: none;
        color: #cdd6f4;
    }
    QFileDialog QToolButton:hover {
        background-color: #45475a;
        border-radius: 4px;
    }
"""


class DialogTitleBar(QWidget):
    """对话框标题栏：标题 + 方形 ✕（与主窗口标题栏同色系），按住可拖动整个对话框。"""

    closeRequested = pyqtSignal()

    HEIGHT = 34

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("dialogTitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        self._drag_offset = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("dialogTitle")
        layout.addWidget(self._title_label)
        layout.addStretch(1)

        self._close_btn = SquareCloseButton(self, size=18, tooltip="关闭")
        self._close_btn.clicked.connect(self.closeRequested)
        layout.addWidget(self._close_btn)

    def setTitle(self, text):
        self._title_label.setText(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class StyledDialog(QDialog):
    """统一外观的对话框基类：无边框 + 深色圆角 + 自定义标题栏。

    用法：``dialog = StyledDialog(self, "标题", width=420)``，
    往 :attr:`body_layout` 里加内容，需要确认按钮时调 :meth:`make_button_row`。
    """

    def __init__(self, parent=None, title="", width=None):
        super().__init__(parent)
        # 去掉系统标题栏（否则会出现浅色 Windows 边框，与主窗口风格不一致）
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setWindowTitle(title)
        self.setStyleSheet(DIALOG_QSS)
        self._centered = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        outer.setSpacing(0)

        self._root = QWidget(self)
        self._root.setObjectName("dialogRoot")
        self._root.setAttribute(Qt.WA_StyledBackground, True)
        if width:
            self._root.setFixedWidth(width)
        outer.addWidget(self._root)

        shadow = QGraphicsDropShadowEffect(self._root)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 160))
        self._root.setGraphicsEffect(shadow)

        root_layout = QVBoxLayout(self._root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = DialogTitleBar(title, self._root)
        self.title_bar.closeRequested.connect(self.reject)
        root_layout.addWidget(self.title_bar)

        self.body = QWidget(self._root)
        self.body.setObjectName("dialogBody")
        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(18, 16, 18, 14)
        self._body_layout.setSpacing(12)
        root_layout.addWidget(self.body)

    @property
    def body_layout(self):
        return self._body_layout

    def make_button_row(self, ok_text="确定", cancel_text="取消"):
        """生成右下角按钮行（主按钮为蓝底），返回 QHBoxLayout 供调用方添加。"""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addStretch(1)
        if cancel_text:
            cancel_btn = QPushButton(cancel_text)
            cancel_btn.setMinimumWidth(76)
            cancel_btn.setFixedHeight(30)
            cancel_btn.clicked.connect(self.reject)
            row.addWidget(cancel_btn)
        ok_btn = QPushButton(ok_text)
        ok_btn.setObjectName("dialogPrimaryBtn")
        ok_btn.setMinimumWidth(76)
        ok_btn.setFixedHeight(30)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        row.addWidget(ok_btn)
        return row

    def showEvent(self, event):
        """首次显示时居中到父窗口（并夹在屏幕可用区域内）。"""
        super().showEvent(event)
        if self._centered:
            return
        self._centered = True
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            geo = parent.window().frameGeometry()
            target = geo.center() - self.rect().center()
        else:
            target = None
        screen = None
        if parent is not None:
            try:
                screen = parent.window().screen().availableGeometry()
            except Exception:
                screen = None
        if screen is None:
            screen = QApplication.primaryScreen().availableGeometry()
        if target is None:
            target = screen.center() - self.rect().center()
        x = max(screen.left(), min(target.x(), screen.right() - self.width()))
        y = max(screen.top(), min(target.y(), screen.bottom() - self.height()))
        self.move(x, y)


class MessageDialog(StyledDialog):
    """信息 / 警告 / 错误 / 询问对话框（替代 QMessageBox 的静态方法）。"""

    # kind -> (图标字符, 图标底色)
    KINDS = {
        "info": ("i", "#89b4fa"),
        "warning": ("!", "#f9e2af"),
        "error": ("x", "#f38ba8"),
        "question": ("?", "#a6e3a1"),
    }

    def __init__(self, parent, title, text, kind="info",
                 buttons=(("确定", QDialog.Accepted),), width=460):
        super().__init__(parent, title, width=width)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        icon_text, icon_color = MessageDialog.KINDS.get(kind, MessageDialog.KINDS["info"])
        icon = QLabel(icon_text)
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            "background-color: %s; color: #1e1e2e; border-radius: 13px;"
            "font-size: 15px; font-weight: bold;" % icon_color)
        row.addWidget(icon, 0, Qt.AlignTop)

        label = QLabel(text)
        label.setObjectName("dialogText")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setMinimumWidth(width - 100)
        row.addWidget(label, 1)
        self._body_layout.addLayout(row)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        for index, (text_, result) in enumerate(buttons):
            btn = QPushButton(text_)
            if index == 0:
                btn.setObjectName("dialogPrimaryBtn")
                btn.setDefault(True)
            btn.setMinimumWidth(76)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _checked=False, r=result: self.done(r))
            btn_row.addWidget(btn)
        self._body_layout.addLayout(btn_row)


class AboutDialog(StyledDialog):
    """关于对话框：富文本展示版本与运行环境。"""

    def __init__(self, parent, title, html_text):
        super().__init__(parent, title, width=480)
        label = QLabel(html_text)
        label.setObjectName("dialogText")
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._body_layout.addWidget(label)
        self._body_layout.addLayout(self.make_button_row(ok_text="确定", cancel_text=None))


class StyledFileDialog(StyledDialog):
    """统一外观的文件 / 目录选择框。

    Qt 的原生文件框是 Windows 自己画的（浅色标题栏 + 浅色主题），
    所以这里强制 ``DontUseNativeDialog`` 并把 QFileDialog 当成子控件嵌进我们的外壳；
    选中结果通过 :attr:`selected_files` 读取。
    """

    def __init__(self, parent=None, title="选择文件", directory=False,
                 start_dir="", filters=None, caption=None):
        super().__init__(parent, title)
        self._body_layout.setContentsMargins(12, 12, 12, 12)

        self._fd = QFileDialog(self.body, caption or title, start_dir or "")
        self._fd.setOption(QFileDialog.DontUseNativeDialog, True)
        self._fd.setWindowFlags(Qt.Widget)
        self._fd.setModal(False)
        self._fd.setMinimumSize(720, 440)

        if directory:
            self._fd.setFileMode(QFileDialog.Directory)
            self._fd.setOption(QFileDialog.ShowDirsOnly, True)
            self._fd.setAcceptMode(QFileDialog.AcceptOpen)
            self._fd.setLabelText(QFileDialog.Accept, "选择")
            self._fd.setLabelText(QFileDialog.FileName, "文件夹")
            # 目录模式下 Qt 默认显示 "Directories" 过滤器名，换成中文
            try:
                self._fd.setNameFilters(["目录"])
            except Exception:
                pass
        else:
            self._fd.setFileMode(QFileDialog.ExistingFile)
            self._fd.setAcceptMode(QFileDialog.AcceptOpen)
            self._fd.setLabelText(QFileDialog.Accept, "打开")
            self._fd.setLabelText(QFileDialog.FileName, "文件名")
            if filters:
                self._fd.setNameFilters(list(filters))

        self._fd.setLabelText(QFileDialog.Reject, "取消")
        self._fd.setLabelText(QFileDialog.LookIn, "位置")
        self._fd.setLabelText(QFileDialog.FileType, "文件类型")

        self._body_layout.addWidget(self._fd)
        self.selected_files = []

        self._fd.accepted.connect(self._on_accept)
        self._fd.rejected.connect(self.reject)

    def _on_accept(self):
        files = self._fd.selectedFiles()
        if not files:
            return
        self.selected_files = files
        self.accept()


class ProgressDialog(StyledDialog):
    """带取消按钮的进度框（替代 QProgressDialog，避免系统标题栏）。"""

    canceled = pyqtSignal()

    def __init__(self, parent, title, label, maximum=100):
        super().__init__(parent, title, width=420)
        self.setWindowModality(Qt.WindowModal)
        self._canceled = False

        self._label = QLabel(label)
        self._label.setObjectName("dialogText")
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._body_layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, max(1, int(maximum)))
        self._bar.setValue(0)
        self._body_layout.addWidget(self._bar)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setMinimumWidth(76)
        self._cancel_btn.setFixedHeight(30)
        self._cancel_btn.clicked.connect(self.reject)
        row.addWidget(self._cancel_btn)
        self._body_layout.addLayout(row)

    def setLabelText(self, text):
        self._label.setText(text)

    def setMaximum(self, value):
        self._bar.setMaximum(max(1, int(value)))

    def maximum(self):
        return self._bar.maximum()

    def setValue(self, value):
        self._bar.setValue(int(value))

    def reject(self):
        """取消按钮 / Esc / 标题栏 ✕ 都视为取消任务。"""
        if not self._canceled:
            self._canceled = True
            self.canceled.emit()
        super().reject()

    def close(self):
        """任务正常结束时关闭：不算作取消，不触发 canceled。"""
        self._canceled = True
        super().close()


# ------------------------- 便捷函数（替代 QMessageBox / QFileDialog） -------------------------

def show_message(parent, title, text, kind="info"):
    """显示一条信息 / 警告 / 错误提示。"""
    MessageDialog(parent, title, text, kind=kind).exec_()


def show_info(parent, title, text):
    show_message(parent, title, text, kind="info")


def show_warning(parent, title, text):
    show_message(parent, title, text, kind="warning")


def show_error(parent, title, text):
    show_message(parent, title, text, kind="error")


def ask_yes_no(parent, title, text, default_yes=True):
    """询问框：是 / 否。返回 True 表示用户点了「是」。"""
    yes = ("是", QDialog.Accepted)
    no = ("否", QDialog.Rejected)
    buttons = (yes, no) if default_yes else (no, yes)
    dialog = MessageDialog(parent, title, text, kind="question", buttons=buttons)
    return dialog.exec_() == QDialog.Accepted


def show_about(parent, title, html_text):
    AboutDialog(parent, title, html_text).exec_()


def pick_directory(parent=None, title="选择文件夹", start_dir=""):
    """选择目录，返回路径（取消返回空串）。"""
    dialog = StyledFileDialog(parent, title, directory=True, start_dir=start_dir)
    if dialog.exec_() == QDialog.Accepted and dialog.selected_files:
        return dialog.selected_files[0]
    return ""


def pick_open_file(parent=None, title="选择文件", filters=None, start_dir=""):
    """选择单个文件，返回路径（取消返回空串）。"""
    dialog = StyledFileDialog(parent, title, directory=False,
                              start_dir=start_dir, filters=filters)
    if dialog.exec_() == QDialog.Accepted and dialog.selected_files:
        return dialog.selected_files[0]
    return ""


