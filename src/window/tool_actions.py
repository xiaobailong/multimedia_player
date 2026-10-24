# -*- coding: utf-8 -*-
"""环境与工具类动作：解码器 / ffmpeg 检测安装、幻灯片设置、图片控制栏、关于。"""
import os

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox
from loguru import logger

from src.layout.pic_input_layout import PicInputLayout
from src.layout.styled_dialogs import (ProgressDialog, StyledDialog, ask_yes_no, show_about,
                                       show_error, show_info, show_warning)
from src.utils.decoder_install_thread import DecoderInstallThread
from src.utils.decoder_manager import (GITHUB_RELEASES_URL, LAV_VERSION, _format_size,
                                       _format_speed, is_lavfilters_installed)
from src.utils.ffmpeg_download_thread import FfmpegDownloadThread
from src.utils.ffmpeg_manager import is_ffmpeg_available
from src.utils.utils import get_resource_base_path


class ToolActionsMixin:
    """解码器 / ffmpeg / 设置 / 关于 等窗口动作。"""

    def _check_decoder(self):
        """检测系统解码器，未安装 LAV Filters 时引导安装，下载/安装放后台线程避免卡死 UI。"""
        try:
            if is_lavfilters_installed():
                self.statusLabel.setText('解码器：LAV Filters 已就绪')
                return

            # 询问用户是否自动安装（弹窗在主线程，不会卡死）
            want_install = ask_yes_no(
                self, '解码器检测',
                '检测到系统未安装 LAV Filters 解码器，\n'
                '部分视频格式可能无法正常播放。\n\n'
                '是否现在自动下载并安装 LAV Filters？\n'
                '（安装需要管理员权限，可能弹出 UAC 确认）')
            if not want_install:
                self.statusLabel.setText('解码器：已跳过安装')
                show_warning(
                    self, '解码器未安装',
                    '已跳过解码器安装。\n\n'
                    '如后续视频无法播放，请手动安装 LAV Filters：\n'
                    f'下载地址：{GITHUB_RELEASES_URL}')
                return

            # 启动后台线程执行下载 + 安装
            self.decoder_thread = DecoderInstallThread(self)
            self.decoder_thread.status.connect(self._on_decoder_status)
            self.decoder_thread.progress.connect(self._on_decoder_progress)
            self.decoder_thread.completed.connect(self._on_decoder_completed)
            self.decoder_thread.failed.connect(self._on_decoder_failed)
            self.decoder_thread.start()
        except Exception as e:
            logger.exception(f'解码器检测异常: {e}')
            self.statusLabel.setText('解码器：检测异常')

    def _on_decoder_status(self, text):
        self.statusLabel.setText(f'解码器：{text}')

    def _on_decoder_progress(self, downloaded, total, speed_bps, source_url):
        msg = (f'解码器下载中：{_format_size(downloaded)}/'
               f'{_format_size(total) if total else "?"}  '
               f'速度 {_format_speed(speed_bps)}')
        self.statusLabel.setText(msg)

    def _on_decoder_completed(self, success, message):
        if success:
            self.statusLabel.setText('解码器：LAV Filters 安装成功')
            show_info(self, '解码器安装', 'LAV Filters 安装成功，现在可以正常播放视频了。')
        else:
            self.statusLabel.setText('解码器：安装失败，请手动安装')
            show_warning(
                self, '解码器安装失败',
                f'自动下载 / 安装 LAV Filters 失败：{message}\n'
                '可能是网络受限或权限不足。\n\n'
                f'请手动下载安装：\n{GITHUB_RELEASES_URL}')
        self.decoder_thread = None

    def _on_decoder_failed(self, message):
        self.statusLabel.setText('解码器：安装异常')
        show_error(self, '解码器安装异常', f'安装过程发生错误：{message}')
        self.decoder_thread = None

    def _check_ffmpeg(self):
        """检测本地 ffmpeg.exe，缺失则后台下载（仅开发环境，打包后已内置）。"""
        try:
            if is_ffmpeg_available():
                return
            # 启动后台线程下载，避免阻塞 UI
            self.ffmpeg_thread = FfmpegDownloadThread(self)
            self.ffmpeg_thread.status.connect(self._on_ffmpeg_status)
            self.ffmpeg_thread.progress.connect(self._on_ffmpeg_progress)
            self.ffmpeg_thread.completed.connect(self._on_ffmpeg_completed)
            self.ffmpeg_thread.failed.connect(self._on_ffmpeg_failed)
            self.ffmpeg_thread.start()
        except Exception as e:
            logger.exception(f'ffmpeg 检测异常: {e}')

    def _on_ffmpeg_status(self, text):
        self.statusLabel.setText(f'ffmpeg：{text}')

    def _on_ffmpeg_progress(self, downloaded, total, speed_bps, source_url):
        msg = (f'ffmpeg 下载中：{_format_size(downloaded)}/'
               f'{_format_size(total) if total else "?"}  '
               f'速度 {_format_speed(speed_bps)}')
        self.statusLabel.setText(msg)

    def _on_ffmpeg_completed(self, success, message):
        if success:
            self.statusLabel.setText('ffmpeg.exe 已就绪')
        else:
            self.statusLabel.setText('ffmpeg：下载失败，部分功能不可用')
            show_warning(
                self, 'ffmpeg 下载失败',
                f'自动下载 ffmpeg.exe 失败：{message}\n\n'
                '视频裁剪 / 截图等功能可能不可用。\n'
                '请手动下载 ffmpeg.exe 放到 libs/ffmpeg/ 目录下。')
        self.ffmpeg_thread = None

    def _on_ffmpeg_failed(self, message):
        self.statusLabel.setText('ffmpeg：下载异常')
        show_error(self, 'ffmpeg 下载异常', f'下载过程发生错误：{message}')
        self.ffmpeg_thread = None

    def _show_slideshow_settings(self):
        """「设置 → 幻灯片」：调整幻灯片自动播放的时间间隔（秒），确认后立即生效并持久化。"""
        layout = self.inputAndExeLayout

        dialog = StyledDialog(self, "幻灯片设置", width=400)

        spin = QSpinBox()
        spin.setRange(PicInputLayout.min_interval_seconds, PicInputLayout.max_interval_seconds)
        spin.setSuffix(" 秒")
        spin.setValue(layout.get_interval_seconds())

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        form.addRow("幻灯片播放时间间隔:", spin)

        tip = QLabel("设置后立即生效，下次启动沿用该间隔。")
        tip.setObjectName("dialogText")
        tip.setWordWrap(True)

        dialog.body_layout.addLayout(form)
        dialog.body_layout.addWidget(tip)
        dialog.body_layout.addLayout(dialog.make_button_row())

        if dialog.exec_() != QDialog.Accepted:
            return

        seconds = layout.set_interval_seconds(spin.value())
        self.notice("幻灯片时间间隔已设置为 %d 秒" % seconds)

    def _toggle_pic_control_panel(self, checked):
        """菜单「视图 → 显示控制器」：勾选显示、取消隐藏。"""
        if checked:
            self.pic_show_layout.show_control_panel()
        else:
            self.pic_show_layout.hide_control_panel()

    def _on_pic_control_panel_visibility_changed(self, visible):
        """点击悬浮面板上的 ✕ 隐藏后，同步菜单勾选状态。"""
        if hasattr(self, 'show_control_action'):
            self.show_control_action.setChecked(visible)

    def _show_decoder_info(self):
        """显示解码器信息对话框，支持自动安装与手动下载引导。"""
        installed = is_lavfilters_installed()
        dialog = StyledDialog(self, "解码器信息", width=440)

        if installed:
            status_html = '<span style="color:#a6e3a1; font-size:14px;">✓ 已安装 LAV Filters</span>'
            hint_html = (
                f'<p style="color:#bac2de;">视频解码器已就绪，可正常播放各种视频格式。</p>'
            )
        else:
            status_html = '<span style="color:#f38ba8; font-size:14px;">✗ 未安装 LAV Filters</span>'
            hint_html = (
                f'<p style="color:#bac2de;">未检测到 LAV Filters 解码器，部分视频格式可能无法正常播放。</p>'
                f'<p style="color:#bac2de;">目标版本：LAV Filters {LAV_VERSION}</p>'
            )

        status_label = QLabel(status_html)
        status_label.setOpenExternalLinks(False)
        dialog.body_layout.addWidget(status_label)

        hint_label = QLabel(hint_html)
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("margin-top: 4px;")
        dialog.body_layout.addWidget(hint_label)

        if not installed:
            link_label = QLabel(
                f'<a href="{GITHUB_RELEASES_URL}" style="color:#89b4fa;">手动下载页面：{GITHUB_RELEASES_URL}</a>'
            )
            link_label.setOpenExternalLinks(True)
            link_label.setWordWrap(True)
            link_label.setStyleSheet("margin-top: 4px;")
            dialog.body_layout.addWidget(link_label)

        dialog.body_layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        button_row.addStretch(1)

        if not installed:
            auto_btn = QPushButton("自动安装")
            auto_btn.setObjectName("dialogPrimaryBtn")
            auto_btn.setMinimumWidth(88)
            auto_btn.setFixedHeight(30)
            auto_btn.setDefault(True)

            manual_btn = QPushButton("手动下载")
            manual_btn.setMinimumWidth(88)
            manual_btn.setFixedHeight(30)

            def _auto_install():
                dialog.accept()
                self._ensure_decoder_auto()

            def _manual_download():
                QDesktopServices.openUrl(QUrl(GITHUB_RELEASES_URL))
                dialog.accept()

            auto_btn.clicked.connect(_auto_install)
            manual_btn.clicked.connect(_manual_download)
            button_row.addWidget(auto_btn)
            button_row.addWidget(manual_btn)

        close_btn = QPushButton("关闭")
        close_btn.setMinimumWidth(76)
        close_btn.setFixedHeight(30)
        close_btn.clicked.connect(dialog.reject)
        button_row.addWidget(close_btn)

        dialog.body_layout.addLayout(button_row)
        dialog.exec_()

    def _ensure_decoder_auto(self):
        """启动后台线程自动下载并安装 LAV Filters。"""
        thread = DecoderInstallThread(self)
        progress = ProgressDialog(self, "安装解码器", f"正在下载并安装 LAV Filters {LAV_VERSION}...")

        def _on_progress(downloaded, total, speed_bps, source_url):
            if total and total > 0:
                progress.setMaximum(total)
                progress.setValue(downloaded)
            speed_text = _format_speed(speed_bps)
            progress.setLabelText(
                f"正在下载 LAV Filters {LAV_VERSION}...  "
                f"{_format_size(downloaded)} / {_format_size(total)}  ({speed_text})"
            )

        thread.progress.connect(_on_progress)
        thread.status.connect(progress.setLabelText)
        thread.finished.connect(progress.close)

        def _on_done(success, msg):
            if success:
                show_info(self, "解码器安装", "LAV Filters 安装成功，现在可以正常播放视频了。")
            else:
                show_warning(
                    self, "解码器安装失败",
                    f"自动下载 / 安装 LAV Filters 失败：{msg}\n"
                    "可能是网络受限或权限不足。\n\n"
                    f"请手动下载安装：\n{GITHUB_RELEASES_URL}")

        thread.completed.connect(_on_done)
        thread.failed.connect(lambda msg: _on_done(False, msg))
        thread.start()
        progress.exec_()

    def _show_about_dialog(self):
        """显示关于对话框"""
        version = "未知"
        try:
            version_path = os.path.join(get_resource_base_path(), "VERSION")
            if os.path.exists(version_path):
                with open(version_path, "r", encoding="utf-8") as f:
                    version = f.read().strip()
        except Exception:
            pass

        import platform
        python_version = platform.python_version()
        try:
            from PyQt5.QtCore import QT_VERSION_STR
            pyqt_version = QT_VERSION_STR
        except ImportError:
            pyqt_version = "5.15.10"

        about_text = (
            f"<h2>多媒体播放器</h2>"
            f"<p><b>版本：</b>{version}</p>"
            f"<p><b>构建信息：</b></p>"
            f"<ul>"
            f"<li>Python 运行环境：{python_version}</li>"
            f"<li>Qt（PyQt5）版本：{pyqt_version}</li>"
            f"<li>操作系统：{platform.system()} {platform.release()}</li>"
            f"</ul>"
            f"<p>基于 PyQt5 与 OpenCV 的桌面多媒体播放器，<br>"
            f"支持视频/音频播放、裁剪、截图、幻灯片等功能。</p>"
        )

        show_about(self, "关于 多媒体播放器", about_text)

    def _show_shortcuts_dialog(self):
        """显示快捷键说明对话框。"""
        shortcuts_rows = [
            ("Space", "播放 / 暂停", "视频、图片"),
            ("← / →", "上一个 / 下一个", "视频、图片"),
            ("↑ / ↓", "快进 / 快退", "视频"),
            ("A / D", "快退 / 快进（同方向键）", "视频"),
            ("W / E", "上一个 / 下一个", "视频"),
            ("F", "全屏 / 退出全屏", "全局"),
            ("Esc", "退出全屏", "全局"),
            ("S", "截图", "视频"),
            ("Z", "设置裁剪起点", "视频"),
            ("X", "设置裁剪终点", "视频"),
            ("C", "执行视频裁剪", "视频"),
            ("1 ~ 5", "评分 1~5 星", "图片、视频"),
            ("Delete / Ctrl+D", "删除当前文件", "图片、视频"),
            ("Ctrl+B", "切换文件列表面板", "全局"),
            ("Ctrl+O", "打开目录作为树的根", "全局"),
            ("Ctrl+Q", "退出", "全局"),
        ]
        table_rows = "".join(
            f"<tr>"
            f"<td style='padding:4px 10px;'><code style='color:#89b4fa;'>{k}</code></td>"
            f"<td style='padding:4px 10px;'>{d}</td>"
            f"<td style='padding:4px 10px;color:#a6adc8;'>{s}</td>"
            f"</tr>"
            for k, d, s in shortcuts_rows
        )
        html = (
            "<h2>快捷键说明</h2>"
            "<p style='color:#bac2de;margin-bottom:10px;'>以下为常用快捷键，按适用范围可分为视频、图片与全局三类。</p>"
            "<table style='border-collapse:collapse;font-size:13px;'>"
            "<thead>"
            "<tr style='border-bottom:1px solid #45475a;'>"
            "<th style='text-align:left;padding:6px 10px;color:#cdd6f4;'>快捷键</th>"
            "<th style='text-align:left;padding:6px 10px;color:#cdd6f4;'>功能</th>"
            "<th style='text-align:left;padding:6px 10px;color:#cdd6f4;'>适用范围</th>"
            "</tr>"
            "</thead>"
            "<tbody>"
            f"{table_rows}"
            "</tbody>"
            "</table>"
        )
        show_about(self, "快捷键说明", html)