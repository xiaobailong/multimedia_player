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

    开发状态下：
        项目根目录/log/
    打包运行状态下：
        与可执行文件同级目录下的 log/
    """
    if getattr(sys, 'frozen', False):
        # 打包运行状态：可执行文件所在目录/log/
        base_dir = os.path.dirname(sys.executable)
    else:
        # 开发状态：项目根目录/log/
        # 从 src/utils/utils.py 向上三级到达项目根目录
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    log_dir = os.path.join(base_dir, 'log')
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def get_db_path():
    """
    获取数据库文件路径。

    开发状态下：
        Windows: data/win/player.db
        macOS:   data/mac/player.db
    打包运行状态下：
        macOS:   ~/Library/Application Support/多媒体播放器/player.db
        Windows: 与可执行文件同级目录下的 player.db
    """
    if getattr(sys, 'frozen', False):
        # 打包运行状态
        if sys.platform == 'darwin':
            data_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', '多媒体播放器')
        else:
            # Windows: 与可执行文件同级目录
            data_dir = os.path.dirname(sys.executable)
    else:
        # 开发状态 - 使用项目根目录下对应平台的 data 目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if sys.platform == 'win32':
            data_dir = os.path.join(project_root, 'data', 'win')
        else:
            data_dir = os.path.join(project_root, 'data', 'mac')

    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'player.db')

def get_ffmpeg_path():
    """
    获取 ffmpeg 可执行文件路径。
    优先使用打包在 app 内的 ffmpeg，其次搜索 PATH 环境变量。
    Windows 系统会自动添加 .exe 扩展名。
    """
    base_path = get_resource_base_path()

    # Windows 下 ffmpeg 可执行文件名
    ffmpeg_name = 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'

    # 尝试 app 包内的 ffmpeg
    ffmpeg_path = os.path.join(base_path, 'ffmpeg', ffmpeg_name)
    if os.path.isfile(ffmpeg_path):
        return ffmpeg_path

    # 尝试项目根目录下的 libs/ffmpeg/（非打包开发环境）
    # base_path = src/，需要往上一级到项目根目录
    parent_path = os.path.dirname(base_path)
    ffmpeg_path = os.path.join(parent_path, 'libs', 'ffmpeg', ffmpeg_name)
    if os.path.isfile(ffmpeg_path):
        return ffmpeg_path

    # 尝试项目目录下的 libs/ffmpeg/
    ffmpeg_path = os.path.join(base_path, 'libs', 'ffmpeg', ffmpeg_name)
    if os.path.isfile(ffmpeg_path):
        return ffmpeg_path

    # 尝试 libs/ffmpeg/ffmpeg.exe （无文件夹嵌套的情况）
    ffmpeg_path = os.path.join(base_path, 'libs', 'ffmpeg', 'ffmpeg', ffmpeg_name)
    if os.path.isfile(ffmpeg_path):
        return ffmpeg_path

    # 搜索 PATH 环境变量
    path_env = os.environ.get('PATH') or os.environ.get('Path', '')
    for item in path_env.split(os.pathsep):
        candidate = os.path.join(item, ffmpeg_name)
        if os.path.isfile(candidate):
            return candidate

    # 最后兜底：返回默认名，让系统去 PATH 找
    return ffmpeg_name

if __name__ == '__main__':
    print(get_ffmpeg_path())