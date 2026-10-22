# -*- coding: utf-8 -*-
"""解码器检测与自动安装模块（Windows 专用）。

视频播放依赖系统已安装的 DirectShow 解码器，本模块负责：
1. 检测本机是否已安装 LAV Filters（或等效解码器）
2. 未安装时自动下载并静默安装
3. 下载失败时引导用户手动安装

下载源采用多源 fallback 策略，依次尝试国内 GitHub 镜像和官方直连，
尽量规避网络限制。下载过程通过 on_progress 回调实时上报速度、已下载大小、总大小。
"""
import os
import sys
import time
import subprocess
import tempfile
import urllib.request
import urllib.error

from loguru import logger

# ---------------------------------------------------------------------------
# 解码器版本与下载源
# ---------------------------------------------------------------------------

# 目标 LAVFilters 版本
LAV_VERSION = '0.73.1'

# GitHub Release 资产名（官方发布页里的文件名）
GITHUB_ASSET = f'LAVFilters-{LAV_VERSION}-Installer.exe'

# 下载源：按优先级排序，前面的失败自动尝试后面的
# 国内镜像加速（ghproxy 系列，对 GitHub Release 做中转）→ GitHub 官方直连
DOWNLOAD_SOURCES = [
    f'https://ghproxy.net/https://github.com/Nevcairiel/LAVFilters/releases/download/{LAV_VERSION}/{GITHUB_ASSET}',
    f'https://gh-proxy.com/https://github.com/Nevcairiel/LAVFilters/releases/download/{LAV_VERSION}/{GITHUB_ASSET}',
    f'https://mirror.ghproxy.com/https://github.com/Nevcairiel/LAVFilters/releases/download/{LAV_VERSION}/{GITHUB_ASSET}',
    f'https://github.com/Nevcairiel/LAVFilters/releases/download/{LAV_VERSION}/{GITHUB_ASSET}',
]

# 官方 Releases 页（下载失败时给用户手动下载）
GITHUB_RELEASES_URL = 'https://github.com/Nevcairiel/LAVFilters/releases'

# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _format_size(num_bytes):
    """把字节数格式化为人类可读字符串。"""
    if num_bytes is None or num_bytes < 0:
        return '未知'
    units = ['B', 'KB', 'MB', 'GB']
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f'{size:.1f}{unit}' if unit != 'B' else f'{int(size)}{unit}'
        size /= 1024


def _format_speed(bps):
    """把字节/秒格式化为速度字符串。"""
    if bps <= 0:
        return '0 B/s'
    return f'{_format_size(bps)}/s'


# ---------------------------------------------------------------------------
# 检测
# ---------------------------------------------------------------------------

def is_lavfilters_installed():
    """检测本机是否已安装 LAV Filters。

    判定依据（满足任一即可）：
    1. 注册表中存在 LAV Filters 安装项（HKLM / HKCU，含 WOW6432Node）
    2. 常见安装目录下存在 LAVVideo.ax / LAVAudio.ax / LAVSplitter.ax
    3. LAV 相关的 COM CLSID 已在注册表注册
    """
    if sys.platform != 'win32':
        # 非 Windows 平台不做检测（macOS / Linux 有各自的解码框架）
        return True

    try:
        import winreg
    except ImportError:
        return False

    # 1) 注册表安装项
    reg_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\LAV Filters'),
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\LAV Filters'),
        (winreg.HKEY_CURRENT_USER, r'SOFTWARE\LAV Filters'),
    ]
    for root, subkey in reg_roots:
        try:
            with winreg.OpenKey(root, subkey):
                logger.info(f'检测到 LAV Filters 注册表项: {subkey}')
                return True
        except OSError:
            continue

    # 2) 常见安装目录
    install_dirs = [
        os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'LAV Filters'),
        os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'LAV Filters'),
    ]
    ax_files = ('LAVVideo.ax', 'LAVAudio.ax', 'LAVSplitter.ax')
    for d in install_dirs:
        if os.path.isdir(d):
            for ax in ax_files:
                if os.path.exists(os.path.join(d, ax)):
                    logger.info(f'检测到 LAV Filters 安装目录: {d}')
                    return True

    # 3) COM CLSID 注册（LAVVideo 的 CLSID）
    lav_clsids = [
        '{EE30215D-164F-4A92-A4EB-1A8CB80B5C0F}',  # LAV Video Decoder
        '{E8E73B6B-4CB3-44A4-BE99-4F7BC4711D79}',  # LAV Audio Decoder
        '{171252A0-8820-4AFE-9DF8-51B12A3A0C10}',  # LAV Splitter
    ]
    for clsid in lav_clsids:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f'CLSID\\{clsid}'):
                logger.info(f'检测到 LAV Filters COM 注册: {clsid}')
                return True
        except OSError:
            continue

    return False


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------

def _download_to(url, dest_path, on_progress=None, timeout=120):
    """从 url 下载到 dest_path，返回 True 表示成功。

    on_progress 回调签名：fn(downloaded_bytes, total_bytes, speed_bps, source_url)
    """
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) multimedia_player'})
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
                    # 日志每 3 秒最多打印一条，避免刷屏
                    if now - last_log_time >= 3:
                        logger.info(
                            f'解码器下载中: {_format_size(downloaded)}/'
                            f'{_format_size(total)} 速度 {_format_speed(speed)}')
                        last_log_time = now
        if total is None:
            logger.info(f'解码器下载完成: {_format_size(downloaded)} (总大小未知)')
        else:
            logger.info(f'解码器下载完成: {_format_size(downloaded)}/{_format_size(total)}')
        # 简单校验：安装包至少 1MB
        return downloaded > 1024 * 1024
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        logger.warning(f'下载失败 {url}: {e}')
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except OSError:
            pass
        return False


def download_lavfilters(dest_dir, on_progress=None):
    """依次尝试多个下载源，把安装包下载到 dest_dir，返回文件路径或空串。

    on_progress 回调签名：fn(downloaded_bytes, total_bytes, speed_bps, source_url)
    """
    os.makedirs(dest_dir, exist_ok=True)
    for url in DOWNLOAD_SOURCES:
        logger.info(f'尝试下载 LAV Filters: {url}')
        dest = os.path.join(dest_dir, GITHUB_ASSET)
        if _download_to(url, dest, on_progress=on_progress):
            logger.info(f'下载成功: {dest}')
            return dest
    return ''


# ---------------------------------------------------------------------------
# 安装
# ---------------------------------------------------------------------------

def install_lavfilters(installer_path, silent=True):
    """执行 LAVFilters 安装包。

    :param installer_path: 安装包 .exe 路径
    :param silent: 是否静默安装（/S）
    :return: (success, message)
    """
    if not os.path.exists(installer_path):
        return False, f'安装包不存在: {installer_path}'

    args = [installer_path]
    if silent:
        args.append('/S')

    try:
        proc = subprocess.run(args, capture_output=True, timeout=300)
        if proc.returncode == 0:
            return True, '安装成功'
        return False, f'安装返回非零退出码: {proc.returncode}'
    except subprocess.TimeoutExpired:
        return False, '安装超时（超过 300 秒）'
    except OSError as e:
        return False, f'执行安装包失败: {e}'


# ---------------------------------------------------------------------------
# 综合：检测 + 下载 + 安装
# ---------------------------------------------------------------------------

def download_and_install(on_progress=None):
    """纯下载+安装逻辑（无 GUI 弹窗），供后台线程调用。

    :param on_progress: 下载进度回调 fn(downloaded, total, speed_bps, source_url)
    :return: (success, message)
    """
    tmp_dir = tempfile.mkdtemp(prefix='lavfilters_')
    downloaded = download_lavfilters(tmp_dir, on_progress=on_progress)
    if not downloaded:
        return False, '所有下载源均失败，可能是网络受限'
    ok, msg = install_lavfilters(downloaded, silent=True)
    if ok and is_lavfilters_installed():
        return True, 'LAV Filters 安装成功'
    return False, msg or '安装后检测仍未通过'


def ensure_decoder(parent=None, on_progress=None):
    """确保系统有可用解码器；没有则尝试自动下载安装。

    注意：本函数在调用线程同步执行下载+安装，**会阻塞调用线程**。
    GUI 中应使用 ``DecoderInstallThread`` 走后台线程，避免界面卡死。

    :param parent: 用于弹框的父窗口
    :param on_progress: 进度回调，签名 fn(downloaded, total, speed_bps, source_url)，可选
    :return: True 表示已有或安装成功，False 表示失败（需用户手动处理）
    """
    from src.layout.styled_dialogs import ask_yes_no, show_info, show_warning

    if is_lavfilters_installed():
        logger.info('解码器检测通过：LAV Filters 已安装')
        return True

    if sys.platform != 'win32':
        return True

    # 询问用户是否自动安装
    want_install = ask_yes_no(
        parent, '解码器检测',
        '检测到系统未安装 LAV Filters 解码器，\n'
        '部分视频格式可能无法正常播放。\n\n'
        '是否现在自动下载并安装 LAV Filters？\n'
        '（安装需要管理员权限，可能弹出 UAC 确认）')
    if not want_install:
        show_warning(
            parent, '解码器未安装',
            '已跳过解码器安装。\n\n'
            '如后续视频无法播放，请手动安装 LAV Filters：\n'
            f'下载地址：{GITHUB_RELEASES_URL}')
        return False

    ok, msg = download_and_install(on_progress=on_progress)
    if ok:
        show_info(parent, '解码器安装', 'LAV Filters 安装成功，现在可以正常播放视频了。')
        return True

    # 全部失败，提示手动安装
    show_warning(
        parent, '解码器安装失败',
        f'自动下载 / 安装 LAV Filters 失败：{msg}\n'
        '可能是网络受限或权限不足。\n\n'
        f'请手动下载安装：\n{GITHUB_RELEASES_URL}')
    return False