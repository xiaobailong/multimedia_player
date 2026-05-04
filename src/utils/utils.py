# -*- coding: utf-8 -*-
"""
路径工具模块：处理 PyInstaller 打包后的资源路径解析
"""
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
    确保该目录存在且有写入权限。
    """
    if sys.platform == 'darwin':
        data_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', '多媒体播放器')
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