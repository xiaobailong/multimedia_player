from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import os

from loguru import logger

from src.data_manager.config_manager import ConfigManager
from src.layout.pic_scan_thread import PicScanThread


class PicInputLayout(QHBoxLayout):
    pic_show_list_key = 'pic.show.list'
    # 幻灯片时间间隔（秒）：由「设置 → 幻灯片」写入 config，下次启动沿用
    slideshow_interval_key = 'pic.show.slideshow.interval'
    default_interval_seconds = 5
    min_interval_seconds = 1
    max_interval_seconds = 3600

    def __init__(self, pic_show_layout, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.content_path = ''
        self.pic_show_layout = pic_show_layout
        self.list_files = list()
        self.config_manager = ConfigManager()

        # 文件路径 / 刷新间隔输入框、目录按钮均已移除：
        # 图片目录统一由左侧树选择（点击目录 / 右键「加载为幻灯片列表」），
        # 没有可用目录时点「幻灯片」会兜底弹出目录选择框；间隔由「设置 → 幻灯片」设置
        self.btn = QPushButton("幻灯片")
        self.addWidget(self.btn)

        self.startAndFullScreenBtn = QPushButton("幻灯片并全屏")
        self.addWidget(self.startAndFullScreenBtn)

        self.fullScreenBtn = QPushButton("全屏")
        self.addWidget(self.fullScreenBtn)

        self.setContentsMargins(0, 0, 0, 0)

        self.timer = QTimer()
        self.timer.setInterval(self.get_interval_seconds() * 1000)
        self.timer.timeout.connect(pic_show_layout.refreshPictures)

        # 目录扫描状态：扫描一律在后台线程执行，避免 GUI 线程被 os.walk 卡死
        self._scan_token = 0
        self._running_scans = set()
        self._pending_slideshow = False

        # 恢复上次选择的图片目录（只回填状态、不自动扫描，避免启动卡顿）
        if self.config_manager.exist(PicInputLayout.pic_show_list_key):
            self.content_path = self.config_manager.get(PicInputLayout.pic_show_list_key) or ''

    def set_content_path(self, path, start_slideshow=False):
        """由左侧树 / 私密模式指定图片目录：记住路径并在后台扫描图片列表。"""
        self.content_path = path or ''
        if self.content_path:
            self.config_manager.add_or_update(PicInputLayout.pic_show_list_key, self.content_path)
        self.loadData(start_slideshow=start_slideshow)
        logger.info(self.content_path)

    def choose_pic_list(self, start_slideshow=False):
        """兜底：没有可用的图片目录时弹出目录选择框（左侧树是主要入口）。"""
        start_dir = self.content_path if os.path.isdir(self.content_path) else ''
        selected_path = QFileDialog.getExistingDirectory(
            self.pic_show_layout.main_window, "选择图片目录", start_dir)
        if not selected_path:
            self._pending_slideshow = False
            return
        self.set_content_path(selected_path, start_slideshow=start_slideshow)

    def load_pic_list(self, start_slideshow=False):
        """按当前目录重新扫描图片列表；没有目录时让用户先选择。"""
        if not self.content_path or not os.path.isdir(self.content_path):
            self.choose_pic_list(start_slideshow=start_slideshow)
            return
        self.loadData(start_slideshow=start_slideshow)

    def get_interval_seconds(self):
        """读取幻灯片播放时间间隔（秒）：配置优先，非法值回落到默认值。"""
        value = None
        try:
            if self.config_manager.exist(PicInputLayout.slideshow_interval_key):
                value = int(float(self.config_manager.get(PicInputLayout.slideshow_interval_key)))
        except (TypeError, ValueError):
            logger.warning("幻灯片时间间隔配置非法，回落到默认值")
        if value is None:
            return PicInputLayout.default_interval_seconds
        return max(PicInputLayout.min_interval_seconds,
                   min(value, PicInputLayout.max_interval_seconds))

    def set_interval_seconds(self, seconds):
        """设置幻灯片播放时间间隔（秒）：立即作用到定时器并写入配置。"""
        try:
            value = int(seconds)
        except (TypeError, ValueError):
            logger.warning(f"幻灯片时间间隔非法: {seconds}")
            return self.get_interval_seconds()
        value = max(PicInputLayout.min_interval_seconds,
                    min(value, PicInputLayout.max_interval_seconds))
        self.timer.setInterval(value * 1000)
        self.config_manager.add_or_update(PicInputLayout.slideshow_interval_key, str(value))
        logger.info(f"幻灯片时间间隔已设置为 {value} 秒")
        return value

    def loadData(self, start_slideshow=False):
        """在后台线程扫描当前目录（大目录不再阻塞 GUI 线程）。"""
        path = self.content_path
        if not path or not os.path.isdir(path):
            self._pending_slideshow = False
            return

        self._pending_slideshow = bool(start_slideshow)
        self._scan_token += 1

        # 只保留最新一次扫描：旧请求立即中断（大目录下避免多线程抢 IO）
        for old_thread in list(self._running_scans):
            try:
                old_thread.requestInterruption()
            except RuntimeError:
                continue

        thread = PicScanThread(self._scan_token, path)
        self._running_scans.add(thread)
        thread.scanned.connect(self._on_scan_finished)
        thread.finished.connect(lambda t=thread: self._running_scans.discard(t))
        thread.finished.connect(thread.deleteLater)
        thread.start()
        logger.info(f'开始扫描图片目录: {path}')

    def _on_scan_finished(self, token, path, files):
        """后台扫描完成：只接受最新一次请求的结果。"""
        if token != self._scan_token:
            logger.info(f'忽略过期的图片扫描结果: {path}')
            return

        self.list_files.clear()
        self.list_files.extend(files)
        self.pic_show_layout.counter = 0
        logger.info(f'图片扫描完成: {path} 共 {len(files)} 张')

        if self._pending_slideshow:
            self._pending_slideshow = False
            if files:
                # 列表此时已就绪，直接走正常播放流程
                self.pic_show_layout.start_process()

    def cancel_scan(self, wait_ms=0):
        """放弃正在进行的扫描（私密模式手工填充列表 / 关闭窗口时调用）。"""
        self._scan_token += 1
        self._pending_slideshow = False
        for thread in list(self._running_scans):
            try:
                thread.requestInterruption()
            except RuntimeError:
                continue
            if wait_ms:
                thread.wait(wait_ms)

