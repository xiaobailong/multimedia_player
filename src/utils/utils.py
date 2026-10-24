# -*- coding: utf-8 -*-
"""
路径工具模块：处理 PyInstaller 打包后的资源路径解析
"""
import hashlib
import os
import sys


def get_resource_base_path():
    """
    获取应用程序的资源根目录。

    在 PyInstaller 打包的 .app 中，资源文件位于 .app/Contents/Resources/ 下，
    可通过 sys._MEIPASS 获取该路径。
    在未打包的开发环境中，使用项目根目录。
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的路径
        return sys._MEIPASS
    else:
        # 开发环境路径：项目根目录
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_app_data_path():
    """
    获取应用程序的数据存储目录（数据库、日志等）。

    在 macOS 下使用 ~/Library/Application Support/多媒体播放器/
    在 Windows/PyInstaller 打包后使用可执行文件所在目录下的 data/ 子目录
    确保该目录存在且有写入权限。
    """
    if sys.platform == 'darwin':
        data_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', '多媒体播放器')
    elif getattr(sys, 'frozen', False):
        data_dir = os.path.join(os.path.dirname(sys.executable), 'data')
    else:
        data_dir = os.path.join(os.path.dirname(get_resource_base_path()), 'data')

    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_log_path():
    """
    获取日志文件存储目录。
    """
    log_dir = os.path.join(get_app_data_path(), 'log')
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def get_db_path():
    """
    获取数据库文件路径。
    """
    db_dir = get_app_data_path()
    return os.path.join(db_dir, 'player.db')


def get_private_key_db_path():
    """**旧版**私密密钥库路径（`data/private_keys.db`）。

    `ADR-028` 之后密钥表已并入 `data/player.db`（`key_material` / `media_keys`），
    这个路径只用于「启动时把旧库一次性并进主库」的迁移逻辑，不再作为运行时数据库。
    """
    db_dir = get_app_data_path()
    return os.path.join(db_dir, 'private_keys.db')


def get_private_cache_path():
    """
    获取私密模式解密缓存目录。

    加密文件要先解密成带正确扩展名的明文才能交给现有播放/展示逻辑，
    这些明文只应在本次运行期间存在（启动与退出时清空）。
    """
    cache_dir = os.path.join(get_app_data_path(), 'private_cache')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def get_ffmpeg_path():
    """
    获取 ffmpeg 可执行文件路径。
    优先使用打包在 app 内的 ffmpeg，其次搜索 PATH 环境变量。
    """
    base_path = get_resource_base_path()

    # 尝试 app 包内的 ffmpeg
    ffmpeg_path = os.path.join(base_path, 'ffmpeg', 'ffmpeg')
    if os.path.exists(ffmpeg_path):
        return ffmpeg_path

    # 尝试项目目录下的 ffmpeg
    ffmpeg_path = os.path.join(base_path, 'libs', 'ffmpeg', 'ffmpeg')
    if os.path.exists(ffmpeg_path):
        return ffmpeg_path

    # 搜索 PATH 环境变量
    path_env = os.environ.get('PATH') or os.environ.get('Path', '')
    for item in path_env.split(os.pathsep):
        candidate = os.path.join(item, 'ffmpeg')
        if os.path.exists(candidate):
            return candidate

    return 'ffmpeg'  # 返回默认值，让系统去 PATH 找


def file_fingerprint(path, sample_size=1024 * 1024):
    """计算文件内容指纹：`blake2b(文件大小 + 首尾各 sample_size 字节)`。

    用途：媒体评分等数据按「文件内容」而不是「路径」索引，
    文件被移动到别的目录 / 改名后仍然能识别出同一份文件。

    视频文件可能很大，不做全量哈希；首尾各取 1MB 已足以区分不同文件，
    且读盘量恒定（最多 2MB），切换文件时不会明显卡顿。

    :param path: 文件路径
    :param sample_size: 头 / 尾采样字节数
    :return: 32 位十六进制指纹字符串；文件不可读时返回空串
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return ''

    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(str(size).encode('ascii'))
    try:
        with open(path, 'rb') as fh:
            head = fh.read(sample_size)
            hasher.update(head)
            if size > sample_size * 2:
                # 大文件：再取尾部一段
                fh.seek(-sample_size, os.SEEK_END)
                hasher.update(fh.read(sample_size))
            elif len(head) < size:
                # 小于 2*sample_size 的文件：把头之后剩下的内容读完，等价于全量哈希
                hasher.update(fh.read())
    except OSError:
        return ''
    return hasher.hexdigest()