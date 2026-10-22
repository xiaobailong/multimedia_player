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
import subprocess

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
# 下载（多线程并行，复用通用下载器）
# ---------------------------------------------------------------------------

def download_lavfilters(dest_dir, on_progress=None):
    """依次尝试多个下载源，把安装包下载到 dest_dir，返回文件路径或空串。

    采用多线程并行下载（HTTP Range 分块），服务器不支持时自动降级单线程。

    on_progress 回调签名：fn(downloaded_bytes, total_bytes, speed_bps, source_url)
    """
    from src.utils.multipart_downloader import download_from_sources

    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, GITHUB_ASSET)
    if download_from_sources(DOWNLOAD_SOURCES, dest, on_progress=on_progress,
                             num_threads=8, log_name='LAVFilters下载'):
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

def get_decoder_cache_path():
    """解码器安装包缓存目录（app data 下，持久化保存，避免每次启动重新下载）。"""
    from src.utils.utils import get_app_data_path
    cache_dir = os.path.join(get_app_data_path(), 'decoder_cache')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def get_cached_installer_path():
    """返回已缓存的安装包路径（大小 > 1MB 且文件名匹配当前版本），不存在返回空串。"""
    cache_dir = get_decoder_cache_path()
    cached = os.path.join(cache_dir, GITHUB_ASSET)
    if os.path.exists(cached) and os.path.getsize(cached) > 1024 * 1024:
        return cached
    # 兼容旧命名（不带 -Installer 后缀），找到任意大于 1MB 的 exe 也认
    try:
        for name in os.listdir(cache_dir):
            if name.lower().endswith('.exe'):
                p = os.path.join(cache_dir, name)
                if os.path.getsize(p) > 1024 * 1024:
                    return p
    except OSError:
        pass
    return ''


def download_and_install(on_progress=None):
    """纯下载+安装逻辑（无 GUI 弹窗），供后台线程调用。

    策略：
    1. 优先复用已缓存的安装包（上次下载成功但安装超时/失败时，下次直接安装）
    2. 无缓存时下载到持久化缓存目录
    3. 安装成功后删除缓存文件；安装失败则保留缓存供下次重试

    :param on_progress: 下载进度回调 fn(downloaded, total, speed_bps, source_url)
    :return: (success, message, used_cache)  used_cache=True 表示直接复用了已下载的安装包
    """
    cache_dir = get_decoder_cache_path()

    # 1) 复用已缓存的安装包
    installer = get_cached_installer_path()
    if installer:
        logger.info(f'复用已缓存的安装包: {installer}')
        ok, msg = install_lavfilters(installer, silent=True)
        if ok and is_lavfilters_installed():
            try:
                os.remove(installer)  # 安装成功后清理缓存
            except OSError:
                pass
            return True, 'LAV Filters 安装成功', True
        return False, msg or '安装后检测仍未通过', True

    # 2) 无缓存，下载到缓存目录
    downloaded = download_lavfilters(cache_dir, on_progress=on_progress)
    if not downloaded:
        return False, '所有下载源均失败，可能是网络受限', False

    # 3) 安装（失败时安装包保留在缓存目录，下次启动直接重试）
    ok, msg = install_lavfilters(downloaded, silent=True)
    if ok and is_lavfilters_installed():
        try:
            os.remove(downloaded)  # 安装成功后清理缓存
        except OSError:
            pass
        return True, 'LAV Filters 安装成功', False
    return False, msg or '安装后检测仍未通过', False


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

    ok, msg, used_cache = download_and_install(on_progress=on_progress)
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