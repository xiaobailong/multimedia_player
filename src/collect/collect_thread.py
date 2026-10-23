# -*- coding: utf-8 -*-
"""归集后台线程：多线程扫描 + 多线程拷贝。

为什么整条链路都放后台：
    递归扫描（`ISSUE-007` → `ADR-012`）和拷贝大视频都会长时间阻塞，
    放在 GUI 线程会让窗口「未响应」。

为什么还要再分线程：
    单个后台线程在"几万个文件 / 大目录树"上仍然慢。
    - 扫描：`utils.media_scan.collect_media_files` 按目录层级并发 `scandir`；
    - 拷贝：`shutil.copy2` 是纯 IO，多个线程并行读写能显著缩短总时间。
"""
import os
import random
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import QThread, pyqtSignal
from loguru import logger

from src.collect.collect_service import suffixes_for_kind, unique_destination
from src.utils.media_scan import DEFAULT_SCAN_WORKERS, collect_media_files

# 并行拷贝的默认线程数：拷贝是"读 + 写"的 IO 密集操作，4 个线程在机械盘 / SSD
# 上都能明显加速，又不像 16 个那样把磁盘寻道打散（可通过 params['copy_workers'] 覆盖）。
DEFAULT_COPY_WORKERS = 4
MAX_COPY_WORKERS = 32


class CollectThread(QThread):
    """按参数收集文件并拷贝到目标目录。

    ``params`` 支持：
        mode          'rating' / 'keyword' / 'path'
        paths         rating 模式：已筛选好的文件列表（由主线程查库/校验后传入）
        root          keyword / path 模式：搜索根目录
        keyword       keyword 模式：文件名关键字（不区分大小写）
        kind          'all' / 'image' / 'video'
        limit         归集数量，0 表示不限制
        order         'sequence' / 'random'（仅 path 模式生效）
        skipped       预先跳过的数量（评分模式里文件已不存在等）
        scan_workers  扫描并发目录数（默认 `DEFAULT_SCAN_WORKERS`）
        copy_workers  拷贝并发线程数（默认 `DEFAULT_COPY_WORKERS`）
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
        self.scan_workers = self._int_param('scan_workers', DEFAULT_SCAN_WORKERS)
        self.copy_workers = self._int_param('copy_workers', DEFAULT_COPY_WORKERS)

    # ------------------------------------------------------------------
    def _int_param(self, key, default):
        try:
            return int(self.params.get(key) or default)
        except (TypeError, ValueError):
            return default

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

        workers = max(1, min(self.copy_workers, MAX_COPY_WORKERS))
        self.progress.emit(0, total, '开始拷贝 %d 个文件（%d 线程）：%s'
                           % (total, workers, self.dest_dir))
        self._copy_files(files, stats, workers, total)

        if stats['cancelled']:
            self.progress.emit(stats['copied'], total,
                               '已取消：已拷贝 %d/%d' % (stats['copied'], total))
        else:
            self.progress.emit(stats['copied'], total, '拷贝完成')
        self.completed.emit(stats)

    # ------------------------------------------------------------------
    def _copy_files(self, files, stats, workers, total):
        """并行拷贝：每个文件一个任务，重名保护走「锁 + 预约集合」。"""
        lock = threading.Lock()
        reserved = set()          # 已分配给线程的目标路径（normcase）
        emit_state = {'done': 0, 'last': 0.0}

        def copy_one(src):
            # 取消后排队中的任务直接返回，不再动任何文件
            if self._is_cancelled():
                return
            name = os.path.basename(src)
            with lock:
                # unique_destination 在锁内调用，并把结果登记进 reserved，
                # 否则两个线程会同时选中同一个"尚未真正落盘"的目标名 → 互相覆盖
                target = unique_destination(self.dest_dir, name, reserved)
                reserved.add(os.path.normcase(target))
            try:
                shutil.copy2(src, target)
            except OSError as e:
                with lock:
                    stats['failed'] += 1
                    if len(stats['errors']) < 10:
                        stats['errors'].append('%s：%s' % (name, e))
                logger.warning(f'归集拷贝失败 {src}: {e}')
                return
            with lock:
                stats['copied'] += 1
                emit_state['done'] += 1
                done = emit_state['done']
                now = time.time()
                should_emit = (done == total) or (now - emit_state['last'] >= 0.1)
                if should_emit:
                    emit_state['last'] = now
            if should_emit:
                self.progress.emit(done, total, '正在拷贝 (%d/%d)：%s' % (done, total, name))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(copy_one, src) for src in files]
            for _future in as_completed(futures):
                if self._is_cancelled():
                    for pending in futures:
                        pending.cancel()

        if self._is_cancelled():
            stats['cancelled'] = True

    # ------------------------------------------------------------------
    def _resolve_files(self, stats):
        """把「要拷贝的文件列表」准备好（评分模式直接用主线程传进来的 paths）。"""
        mode = self.params.get('mode') or 'path'
        if mode == 'rating':
            return [p for p in (self.params.get('paths') or []) if os.path.isfile(p)]

        root = self.params.get('root') or ''
        keyword = (self.params.get('keyword') or '').strip().lower()
        kind = self.params.get('kind') or 'all'
        try:
            limit = int(self.params.get('limit') or 0)
        except (TypeError, ValueError):
            limit = 0
        order = self.params.get('order') or 'sequence'

        # 扫描阶段的文字回报限频，避免上万次信号刷爆事件循环
        last_emit = [0.0]

        def on_scan_progress(found_count):
            now = time.time()
            if now - last_emit[0] < 0.2:
                return
            last_emit[0] = now
            self.progress.emit(0, 0, '正在扫描：已找到 %d 个文件' % found_count)

        self.progress.emit(0, 0, '正在扫描（%d 线程）：%s' % (self.scan_workers, root))
        files = collect_media_files(root, suffixes_for_kind(kind),
                                    is_cancelled=self._is_cancelled,
                                    max_workers=self.scan_workers,
                                    on_progress=on_scan_progress)
        if files is None:
            stats['cancelled'] = True
            return []

        if keyword:
            files = [p for p in files if keyword in os.path.basename(p).lower()]
        files.sort()

        if limit > 0 and len(files) > limit:
            if order == 'random':
                files = random.sample(files, limit)
            else:
                files = files[:limit]

        if self._is_cancelled():
            stats['cancelled'] = True
        return files
