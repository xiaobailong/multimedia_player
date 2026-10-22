# -*- coding: utf-8 -*-
"""归集后台线程：筛选 / 扫描文件，然后逐个拷贝到目标目录。

为什么放线程里：
    递归扫描（`ISSUE-007` → `ADR-012`）和拷贝大视频都会长时间阻塞，
    放在 GUI 线程会让窗口「未响应」。
"""
import os
import random
import shutil
import time

from PyQt5.QtCore import QThread, pyqtSignal
from loguru import logger

from src.collect.collect_service import iter_media_files, unique_destination


class CollectThread(QThread):
    """按参数收集文件并拷贝到目标目录。

    ``params`` 支持：
        mode      'rating' / 'keyword' / 'path'
        paths     rating 模式：已筛选好的文件列表（由主线程查库/校验后传入）
        root      keyword / path 模式：搜索根目录
        keyword   keyword 模式：文件名关键字（不区分大小写）
        kind      'all' / 'image' / 'video'
        limit     归集数量，0 表示不限制
        order     'sequence' / 'random'（仅 path 模式生效）
        skipped   预先跳过的数量（评分模式里文件已不存在等）
    """

    # done, total, message（total <= 0 表示只更新文字，不确定进度）
    progress = pyqtSignal(int, int, str)
    completed = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, params, dest_dir, parent=None):
        super().__init__(parent)
        self.params = dict(params or {})
        self.dest_dir = dest_dir or ''
        self._cancelled = False

    # ------------------------------------------------------------------
    def cancel(self):
        self._cancelled = True
        self.requestInterruption()

    def _is_cancelled(self):
        return self._cancelled or self.isInterruptionRequested()

    # ------------------------------------------------------------------
    def run(self):
        stats = {
            'found': 0,
            'copied': 0,
            'skipped': int(self.params.get('skipped') or 0),
            'failed': 0,
            'cancelled': False,
            'dest': self.dest_dir,
            'errors': [],
        }
        try:
            os.makedirs(self.dest_dir, exist_ok=True)
        except OSError as e:
            self.failed.emit('无法创建目标目录：%s' % e)
            return

        try:
            files = self._resolve_files(stats)
        except Exception as e:  # 扫描阶段的意外错误
            logger.exception(f'归集扫描失败: {e}')
            self.failed.emit('扫描失败：%s' % e)
            return

        stats['found'] = len(files)
        total = len(files)
        if total == 0:
            self.completed.emit(stats)
            return

        for index, src in enumerate(files):
            if self._is_cancelled():
                stats['cancelled'] = True
                break
            name = os.path.basename(src)
            self.progress.emit(index, total, '正在拷贝 (%d/%d)：%s' % (index + 1, total, name))
            try:
                target = unique_destination(self.dest_dir, name)
                shutil.copy2(src, target)
                stats['copied'] += 1
            except OSError as e:
                stats['failed'] += 1
                if len(stats['errors']) < 10:
                    stats['errors'].append('%s：%s' % (name, e))
                logger.warning(f'归集拷贝失败 {src}: {e}')

        self.progress.emit(stats['copied'], total, '拷贝完成')
        self.completed.emit(stats)

    # ------------------------------------------------------------------
    def _resolve_files(self, stats):
        """把「要拷贝的文件列表」准备好（评分模式直接用主线程传进来的 paths）。"""
        mode = self.params.get('mode') or 'path'
        if mode == 'rating':
            return [p for p in (self.params.get('paths') or []) if os.path.isfile(p)]

        root = self.params.get('root') or ''
        keyword = self.params.get('keyword') or ''
        kind = self.params.get('kind') or 'all'
        try:
            limit = int(self.params.get('limit') or 0)
        except (TypeError, ValueError):
            limit = 0
        order = self.params.get('order') or 'sequence'

        # 扫描阶段回报文字限频，避免上万次信号刷爆事件循环
        last_emit = [0.0]

        def on_dir(current):
            now = time.time()
            if now - last_emit[0] < 0.15:
                return
            last_emit[0] = now
            self.progress.emit(0, 0, '正在扫描：%s' % current)

        self.progress.emit(0, 0, '正在扫描：%s' % root)
        files = []
        for path in iter_media_files(root, kind=kind, keyword=keyword,
                                     is_cancelled=self._is_cancelled, on_dir=on_dir):
            files.append(path)
            if order != 'random' and limit > 0 and len(files) >= limit:
                break
            if len(files) % 200 == 0:
                self.progress.emit(0, 0, '正在扫描：已找到 %d 个文件' % len(files))

        if self._is_cancelled():
            stats['cancelled'] = True

        if order == 'random' and limit > 0 and len(files) > limit:
            files = random.sample(files, limit)

        files.sort()
        return files
