# -*- coding: utf-8 -*-
"""私密模式批量加/解密的 QThread 包装。

加密/解密一个大目录可能几十秒，必须放到工作线程，否则窗口会假死。
线程内部自建 PrivateService（独立 sqlite 连接），避免和 UI 线程交叉使用同一连接。
"""

from PyQt5.QtCore import QThread, pyqtSignal
from loguru import logger

from src.private_mode.key_store import PrivateKeyStore
from src.private_mode.private_service import PrivateService


class PrivateBatchThread(QThread):
    """mode: 'encrypt' 加密路径 / 'decrypt' 解密路径。"""

    progress = pyqtSignal(int, int, str)   # 已完成, 总数, 当前文件名
    completed = pyqtSignal(dict)           # 统计结果
    failed = pyqtSignal(str)               # 整体异常

    def __init__(self, mode, target, db_path=None, cache_dir=None, parent=None):
        super(PrivateBatchThread, self).__init__(parent)
        self.mode = mode
        self.target = target
        self.db_path = db_path
        self.cache_dir = cache_dir
        self._service = None
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _should_cancel(self):
        return self._cancel

    def _on_progress(self, done, total, name):
        self.progress.emit(done, total, name)

    def run(self):
        try:
            self._service = PrivateService(
                store=PrivateKeyStore(self.db_path),
                cache_dir=self.cache_dir,
            )
            if self.mode == 'encrypt':
                stats = self._service.encrypt_path(
                    self.target,
                    progress=self._on_progress,
                    should_cancel=self._should_cancel,
                )
            else:
                stats = self._service.decrypt_path(
                    self.target,
                    progress=self._on_progress,
                    should_cancel=self._should_cancel,
                )
            self.completed.emit(stats)
        except Exception as e:
            logger.error(f'私密批量操作失败({self.mode} {self.target}): {e}')
            self.failed.emit(str(e))
        finally:
            if self._service is not None:
                self._service.close()
