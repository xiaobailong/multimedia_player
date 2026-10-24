# -*- coding: utf-8 -*-
"""媒体目录扫描（纯逻辑，不依赖 Qt）：**任务队列 + 线程池**。

调度模型（见 `ADR-023`）：
- 一个任务队列，每个任务 = 一个绝对路径目录；
- 线程池里的线程循环「领任务 → 扫该目录里的文件 → 把子目录入队 → 标记完成」；
- 队列按规范化路径**去重**，同一目录只会被扫一次（junction / 软链按真实路径去重，防环）；
- 队列空但仍有目录在扫 → 线程在 `Condition` 上**等待**，不是退出；
- 只有「队列空 **且** 没有目录在扫」才广播结束 —— 这正是"空队列 ≠ 扫描结束"的坑。

为什么不用"分层 BFS + 每层 submit 一批"：那种写法有层屏障，
同一层里只要有一个慢目录（网络盘 / 大目录），整层都得等它，
下一层的目录迟迟不下发，并行度会被最慢的那条分支拖住；
任务队列是流水线，慢目录不会阻塞其它分支。
"""
import collections
import os
import threading
import time

from loguru import logger

# 并发扫描目录数：scandir + stat 是 IO 密集，多线程能明显加快；
# 8 是折中值 —— 太小在大目录上收益有限，太大在机械盘 / 网络盘上会互相抢 IO。
DEFAULT_SCAN_WORKERS = 8
MAX_SCAN_WORKERS = 64


def _worker_count(max_workers):
    try:
        workers = int(max_workers or DEFAULT_SCAN_WORKERS)
    except (TypeError, ValueError):
        workers = DEFAULT_SCAN_WORKERS
    return max(1, min(workers, MAX_SCAN_WORKERS))


def _path_key(path):
    """去重键：绝对路径 + 大小写归一（Windows 大小写不敏感）。"""
    return os.path.normcase(os.path.abspath(path))


def _is_link_dir(entry):
    """是否是"目录形式的链接"（junction / 目录软链）。

    实测 Windows：junction 的 `is_dir(follow_symlinks=False)` 是 **True**、`is_symlink()` 是 False，
    只有 `is_junction()` 能认出来 —— 不特殊处理就会递归进环里。
    """
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, 'is_junction', None)
    try:
        return bool(is_junction is not None and is_junction())
    except OSError:
        return False


# MPEG-TS 系的扩展名和 TypeScript（.ts / .mts）撞了：
# 实测扫一次用户目录，把 8000+ 个 TypeScript 源文件当视频列了出来。
# 这类扩展名在扫描时按内容做一次廉价校验（只读 377 字节）。
_TS_LIKE_SUFFIXES = ('.ts', '.mts', '.m2ts')


def _looks_like_mpeg_ts(path):
    """判断是不是真正的 MPEG-TS / M2TS（而不是同名后缀的文本文件）。

    - 标准 TS：188 字节一个包，同步字节 0x47 在偏移 0、188、376…
    - M2TS（AVCHD / Blu-ray）：192 字节一个包，前面多 4 字节时间戳，同步字节在偏移 4、196…
    """
    try:
        with open(path, 'rb') as fh:
            head = fh.read(377)
    except OSError:
        return False
    if len(head) >= 189 and head[0] == 0x47 and head[188] == 0x47:
        return True
    if len(head) >= 197 and head[4] == 0x47 and head[196] == 0x47:
        return True
    return False


def _safe_cancelled(is_cancelled):
    """调用方传入的取消判定；任何异常都当作"未取消"，不能让它打断扫描线程。"""
    if is_cancelled is None:
        return False
    try:
        return bool(is_cancelled())
    except Exception as e:  # noqa: BLE001
        logger.warning(f'扫描取消判定异常（忽略）: {e}')
        return False


def _sort_key(item):
    """排序键：修改时间升序；时间相同再按路径，保证并发下顺序稳定。

    （只按 mtime 排序时，相同 mtime 的文件相对顺序取决于线程完成顺序 → 列表会抖动）
    """
    return item[1], os.path.normcase(item[0])


# 扫描系统目录（C:\Users、C:\Windows…）时会遇到大量"拒绝访问"的目录：
# 前 N 条用 WARNING，之后的降级成 DEBUG 并给一条汇总，避免日志被刷屏。
_MAX_ACCESS_WARNINGS = 10
_access_warn = {'count': 0}
_access_warn_lock = threading.Lock()


def _reset_access_warnings():
    with _access_warn_lock:
        _access_warn['count'] = 0


def _log_access_warning(message):
    with _access_warn_lock:
        _access_warn['count'] += 1
        count = _access_warn['count']
    if count <= _MAX_ACCESS_WARNINGS:
        logger.warning(message)
    elif count == _MAX_ACCESS_WARNINGS + 1:
        logger.warning('还有更多无法读取的目录，已省略逐条提示（需要细节请把日志级别调到 DEBUG）')
    else:
        logger.debug(message)


def _scan_one_dir(directory, suffixes, should_stop=None):
    """扫描单个目录，返回 ([(file_path, mtime), ...], [(subdir_path, dedup_key), ...])。"""
    files = []
    subdirs = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if should_stop is not None and should_stop():
                    return files, subdirs
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if _is_link_dir(entry):
                            # 目录链接（junction / 软链）：**扫真实路径**，并用真实路径做去重键。
                            # 为什么不能扫链接路径：Windows 上 `Local Settings` / `Application Data`
                            # / `Cookies` 这类老 junction 本身是"拒绝访问"的，而它们指向的正是
                            # `AppData\Local` 等真实目录。若先按链接路径入队、又用 realpath 记键，
                            # 真实目录后来被发现时会被判成"重复"跳过 ⇒ 整个 AppData 漏扫（ISSUE-014）。
                            try:
                                real = os.path.realpath(entry.path)
                            except OSError:
                                continue
                            subdirs.append((real, _path_key(real)))
                        else:
                            subdirs.append((entry.path, None))
                        continue
                    if not entry.name.lower().endswith(suffixes):
                        continue
                    # .ts / .mts / .m2ts 要和 TypeScript 源文件区分开（见 _looks_like_mpeg_ts）
                    if (entry.name.lower().endswith(_TS_LIKE_SUFFIXES)
                            and not _looks_like_mpeg_ts(entry.path)):
                        continue
                    # scandir 的 stat 结果在 Windows 上会被缓存
                    files.append((entry.path, entry.stat(follow_symlinks=False).st_mtime))
                except OSError:
                    continue
    except OSError as e:
        _log_access_warning(f'跳过无法读取的目录 {directory}: {e}')
    return files, subdirs


class _ScanQueue:
    """目录任务队列：去重 + 空时等待 + 结束判定。

    三个状态必须区分清楚（否则一定会漏扫）：
      - 队列有任务            → 直接取；
      - 队列空、但有目录在扫  → 等待（那些目录随时可能把自己的子目录放进来）；
      - 队列空且没有目录在扫  → 扫描真的结束，唤醒所有等待者退出。
    """

    def __init__(self):
        self._cond = threading.Condition()
        self._tasks = collections.deque()
        self._keys = set()      # 已入队（含正在扫）的规范化路径
        self._pending = 0       # 队列中 + 正在扫描的目录数
        self._closed = False

    def put(self, path, key=None):
        """入队一个目录；重复（或已关闭）则忽略，返回是否真的入队。"""
        key = key or _path_key(path)
        with self._cond:
            if self._closed or key in self._keys:
                return False
            self._keys.add(key)
            self._tasks.append(path)
            self._pending += 1
            self._cond.notify()
            return True

    def get(self):
        """取一个目录；返回 None 表示扫描结束（或已被关闭）。"""
        with self._cond:
            while True:
                if self._closed:
                    return None
                if self._tasks:
                    return self._tasks.popleft()
                if self._pending == 0:
                    # 队列空 + 无在途目录 = 真的扫完了，叫醒其它等待者一起退出
                    self._cond.notify_all()
                    return None
                self._cond.wait()

    def done(self):
        """一个目录处理完（它带来的子目录已经在 put 时计入 pending）。"""
        with self._cond:
            self._pending -= 1
            if self._pending <= 0:
                self._pending = 0
                self._cond.notify_all()

    def close(self):
        """取消：拒绝新任务并唤醒所有等待者尽快退出。"""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def pending(self):
        with self._cond:
            return self._pending


def collect_media_files(root, suffixes, is_cancelled=None, recursive=True,
                        max_workers=None, on_progress=None):
    """递归收集 `root` 及其子目录下的媒体文件，返回按 (mtime, 路径) 升序的绝对路径列表。

    - 任务队列 + 线程池：`max_workers` 个线程从同一个队列领目录（默认 `DEFAULT_SCAN_WORKERS`）；
    - 队列按规范化路径去重；junction / 目录软链按真实路径去重（防环、同一目标只扫一次）；
    - 只有"队列空 + 没有目录在扫"才算结束，线程在 `Condition` 上等待、不空转；
    - `on_progress(found_count)`：每扫完一个目录最多回调一次（内部限频 0.1s，锁外调用）；
    - `recursive=False`：只扫 `root` 这一层（单目录，不开线程池）；
    - 取消返回 `None`；被删除 / 无权限的目录直接跳过，不影响其它分支。

    注意：同步 IO，必须在后台线程里调用（否则会卡住 GUI，见 `ISSUE-007`）。
    """
    if not root or not os.path.isdir(root):
        return []
    suffixes = tuple(suffixes)
    _reset_access_warnings()

    if not recursive:
        files, _subdirs = _scan_one_dir(root, suffixes, lambda: _safe_cancelled(is_cancelled))
        if _safe_cancelled(is_cancelled):
            return None
        files.sort(key=_sort_key)
        return [path for path, _ in files]

    workers = _worker_count(max_workers)
    task_queue = _ScanQueue()
    task_queue.put(root)

    found = []
    found_lock = threading.Lock()
    progress_state = {'last': 0.0}

    def should_stop():
        return _safe_cancelled(is_cancelled)

    def worker():
        local = []
        while True:
            directory = task_queue.get()
            if directory is None:
                break
            try:
                files, subdirs = _scan_one_dir(directory, suffixes, should_stop)
                if files:
                    local.extend(files)
                for sub_path, sub_key in subdirs:
                    # 去重 / 关闭判断都在队列里做；这里失败（重复、已取消）直接忽略
                    task_queue.put(sub_path, sub_key)
            except Exception as e:  # noqa: BLE001
                # 任何异常都不能让线程提前死掉：否则 pending 永不归零，其它线程会一直等
                logger.exception(f'扫描目录异常 {directory}: {e}')
            finally:
                task_queue.done()

            # 进度回调：锁外调用 + 限频 + 吞掉回调异常（回调是调用方的代码，不能影响扫描）
            if on_progress is not None:
                now = time.monotonic()
                if now - progress_state['last'] >= 0.1:
                    progress_state['last'] = now
                    with found_lock:
                        snapshot = len(found) + len(local)
                    try:
                        on_progress(snapshot)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f'扫描进度回调异常（忽略）: {e}')

        if local:
            with found_lock:
                found.extend(local)

    threads = [threading.Thread(target=worker, name='media-scan-%d' % index, daemon=True)
               for index in range(workers)]
    for thread in threads:
        thread.start()

    cancelled = False
    try:
        while True:
            alive = [thread for thread in threads if thread.is_alive()]
            if not alive:
                break
            for thread in alive:
                thread.join(0.05)
            if should_stop():
                cancelled = True
                task_queue.close()
    finally:
        # 兜底：主线程异常退出时也别让 worker 永久等待
        task_queue.close()
        for thread in threads:
            thread.join(1.0)

    if cancelled or _safe_cancelled(is_cancelled):
        return None
    found.sort(key=_sort_key)
    return [path for path, _ in found]

