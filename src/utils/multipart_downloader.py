# -*- coding: utf-8 -*-
"""通用多线程并行下载器。

支持 HTTP Range 分块下载：把文件切成多块，多个线程同时下载不同的块，最后合并。
服务器不支持 Range 时自动降级为单线程顺序下载。

解码器和 ffmpeg 的下载都通过本模块统一处理，享受同一套多源 fallback + 进度回调逻辑。
"""
import os
import time
import threading
import urllib.request
import urllib.error

from loguru import logger

DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) multimedia_player'

# 每个分块的最小大小（1MB），避免文件很小时线程太多
MIN_CHUNK_SIZE = 1024 * 1024


def _format_size(num_bytes):
    if num_bytes is None or num_bytes < 0:
        return '未知'
    units = ['B', 'KB', 'MB', 'GB']
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f'{size:.1f}{unit}' if unit != 'B' else f'{int(size)}{unit}'
        size /= 1024


def _format_speed(bps):
    if bps <= 0:
        return '0 B/s'
    return f'{_format_size(bps)}/s'


def _get_file_size(url, timeout=30):
    """获取远程文件大小，同时判断是否支持 Range。

    :return: (file_size, supports_range)  file_size 为 None 表示未知；不支持时也尽量拿到大小
    """
    try:
        req = urllib.request.Request(
            url, method='HEAD',
            headers={'User-Agent': DEFAULT_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = int(resp.headers.get('Content-Length', 0) or 0) or None
            accept_ranges = (resp.headers.get('Accept-Ranges') or '').lower()
            supports_range = accept_ranges == 'bytes'
            if total:
                logger.info(f'远程文件大小: {_format_size(total)}  支持Range: {supports_range}')
            return total, supports_range
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        logger.warning(f'HEAD 请求失败 {url}: {e}')
        return None, False


def _download_chunk(url, dest_path, start, end, progress_lock, progress_state, on_progress, log_name=''):
    """下载一个分块 [start, end]，写入 dest_path 的指定偏移。"""
    headers = {
        'User-Agent': DEFAULT_USER_AGENT,
        'Range': f'bytes={start}-{end}',
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp, \
                open(dest_path, 'r+b') as fh:
            fh.seek(start)
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                with progress_lock:
                    progress_state['downloaded'] += len(chunk)
                    downloaded = progress_state['downloaded']
                    total = progress_state['total']
                    start_time = progress_state['start_time']
                elapsed = time.time() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0
                if on_progress:
                    on_progress(downloaded, total, speed, url)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        with progress_lock:
            progress_state['error'] = f'{log_name}下载失败: {e}'
        logger.warning(f'{log_name}分块下载失败 {url} [{start}-{end}]: {e}')


def download_file(url, dest_path, on_progress=None, num_threads=8, log_name='下载'):
    """多线程并行下载 url 到 dest_path。

    :param url: 下载地址
    :param dest_path: 目标文件路径
    :param on_progress: 进度回调 fn(downloaded, total, speed_bps, source_url)
    :param num_threads: 并行线程数
    :param log_name: 日志前缀名
    :return: True 表示成功
    """
    os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)

    # 1) 获取文件大小 & 判断是否支持 Range
    total, supports_range = _get_file_size(url)

    # 不支持 Range 或文件过小 -> 单线程下载
    if not supports_range or total is None or total < MIN_CHUNK_SIZE * 2:
        return _single_thread_download(url, dest_path, on_progress, log_name=log_name)

    # 2) 分块并行下载
    num_threads = min(num_threads, max(1, total // MIN_CHUNK_SIZE))
    chunk_size = (total + num_threads - 1) // num_threads
    logger.info(f'{log_name}: 文件 {_format_size(total)}，{num_threads} 线程并行下载，'
                f'每块约 {_format_size(chunk_size)}')

    # 预分配文件
    with open(dest_path, 'wb') as fh:
        fh.truncate(total)

    progress_lock = threading.Lock()
    progress_state = {
        'downloaded': 0,
        'total': total,
        'start_time': time.time(),
        'error': None,
    }

    threads = []
    for i in range(num_threads):
        start = i * chunk_size
        end = min(start + chunk_size - 1, total - 1)
        if start > end:
            break
        t = threading.Thread(
            target=_download_chunk,
            args=(url, dest_path, start, end, progress_lock, progress_state,
                  on_progress, log_name),
            daemon=True)
        threads.append(t)
        t.start()

    last_log_time = time.time()
    while any(t.is_alive() for t in threads):
        time.sleep(0.2)
        now = time.time()
        if now - last_log_time >= 3:
            with progress_lock:
                downloaded = progress_state['downloaded']
            elapsed = now - progress_state['start_time']
            speed = downloaded / elapsed if elapsed > 0 else 0
            logger.info(f'{log_name}中: {_format_size(downloaded)}/{_format_size(total)} '
                        f'速度 {_format_speed(speed)}')
            last_log_time = now

    for t in threads:
        t.join(timeout=5)

    if progress_state['error']:
        logger.warning(f'{log_name}失败: {progress_state["error"]}')
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except OSError:
            pass
        return False

    # 校验文件大小
    actual = os.path.getsize(dest_path)
    logger.info(f'{log_name}完成: {_format_size(actual)}/{_format_size(total)}')
    return actual >= total - 1024  # 允许 1KB 误差


def _single_thread_download(url, dest_path, on_progress=None, timeout=120, log_name='下载'):
    """单线程顺序下载（服务器不支持 Range 时降级使用）。"""
    try:
        req = urllib.request.Request(
            url, headers={'User-Agent': DEFAULT_USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = int(resp.headers.get('Content-Length', 0) or 0) or None
            downloaded = 0
            start_time = time.time()
            last_log_time = start_time
            with open(dest_path, 'wb') as fh:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    elapsed = now - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    if on_progress:
                        on_progress(downloaded, total, speed, url)
                    if now - last_log_time >= 3:
                        logger.info(
                            f'{log_name}中: {_format_size(downloaded)}/'
                            f'{_format_size(total)} 速度 {_format_speed(speed)}')
                        last_log_time = now
        if total is None:
            logger.info(f'{log_name}完成: {_format_size(downloaded)} (总大小未知)')
        else:
            logger.info(f'{log_name}完成: {_format_size(downloaded)}/{_format_size(total)}')
        return downloaded > 1024 * 1024  # 至少 1MB 校验
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        logger.warning(f'{log_name}失败 {url}: {e}')
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except OSError:
            pass
        return False


def download_from_sources(sources, dest_path, on_progress=None, num_threads=8, log_name='下载'):
    """依次尝试多个下载源，返回 True 表示成功。"""
    for url in sources:
        logger.info(f'{log_name}: 尝试源 {url}')
        if download_file(url, dest_path, on_progress=on_progress,
                         num_threads=num_threads, log_name=log_name):
            logger.info(f'{log_name}成功: {dest_path}')
            return True
    return False