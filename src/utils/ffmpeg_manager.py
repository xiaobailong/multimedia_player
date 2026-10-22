# -*- coding: utf-8 -*-
"""ffmpeg.exe 检测与自动下载模块。

视频截图 / 裁剪依赖 ffmpeg.exe。本模块负责：
1. 检测本地 libs/ffmpeg/ffmpeg.exe 是否存在
2. 不存在时从网络下载（多线程并行，多源 fallback 规避防火墙）
3. 下载 zip 包后解压提取 ffmpeg.exe 到本地

注意：本模块只在「开发环境运行」和「构建脚本」中使用；
正式打包的 app 已通过 --add-data 携带 ffmpeg.exe，不需要检测下载。
"""
import os
import sys
import shutil
import zipfile
import tempfile

from loguru import logger

# BtbN/FFmpeg-Builds 的 latest release 资产（持续更新，始终指向最新构建）
FFMPEG_ZIP_NAME = 'ffmpeg-master-latest-win64-gpl.zip'
FFMPEG_INNER_BIN = 'ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe'

# 下载源 fallback：国内镜像 → GitHub 直连
FFMPEG_DOWNLOAD_SOURCES = [
    f'https://ghproxy.net/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{FFMPEG_ZIP_NAME}',
    f'https://gh-proxy.com/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{FFMPEG_ZIP_NAME}',
    f'https://mirror.ghproxy.com/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{FFMPEG_ZIP_NAME}',
    f'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{FFMPEG_ZIP_NAME}',
]


def get_ffmpeg_target_path():
    """返回本地 ffmpeg.exe 目标路径：项目根目录/libs/ffmpeg/ffmpeg.exe。"""
    # 本文件位于 src/utils/，项目根 = 上三级目录（utils -> src -> 项目根）
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, 'libs', 'ffmpeg', 'ffmpeg.exe')


def is_ffmpeg_available():
    """检测本地 libs/ffmpeg/ffmpeg.exe 是否存在。"""
    return os.path.exists(get_ffmpeg_target_path())


def download_ffmpeg(on_progress=None):
    """下载 ffmpeg.exe 到本地 libs/ffmpeg/。

    :param on_progress: 下载进度回调 fn(downloaded, total, speed_bps, source_url)
    :return: (success, message)
    """
    from src.utils.multipart_downloader import download_from_sources

    target = get_ffmpeg_target_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)

    # 下载 zip 到临时目录
    tmp_dir = tempfile.mkdtemp(prefix='ffmpeg_dl_')
    zip_path = os.path.join(tmp_dir, FFMPEG_ZIP_NAME)

    try:
        ok = download_from_sources(FFMPEG_DOWNLOAD_SOURCES, zip_path,
                                   on_progress=on_progress, num_threads=8,
                                   log_name='ffmpeg下载')
        if not ok:
            return False, '所有 ffmpeg 下载源均失败，可能是网络受限'

        # 解压提取 ffmpeg.exe
        logger.info(f'正在解压 ffmpeg zip: {zip_path}')
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # 找 bin/ffmpeg.exe（兼容目录结构变化）
            exe_in_zip = None
            for name in zf.namelist():
                if name.endswith('/bin/ffmpeg.exe') or name == FFMPEG_INNER_BIN:
                    exe_in_zip = name
                    break
            if not exe_in_zip:
                return False, '下载的 zip 中未找到 ffmpeg.exe'

            with zf.open(exe_in_zip) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst)

        # 校验：至少 10MB
        if os.path.getsize(target) < 10 * 1024 * 1024:
            try:
                os.remove(target)
            except OSError:
                pass
            return False, '解压后的 ffmpeg.exe 过小，可能下载不完整'

        logger.info(f'ffmpeg.exe 已就位: {target} ({os.path.getsize(target) // (1024*1024)}MB)')
        return True, 'ffmpeg.exe 下载成功'

    except (zipfile.BadZipFile, OSError) as e:
        logger.exception(f'ffmpeg 解压失败: {e}')
        return False, f'解压失败: {e}'
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except OSError:
            pass


def ensure_ffmpeg(on_progress=None):
    """确保本地有 ffmpeg.exe；没有则下载。

    只在开发环境 / 构建时调用，打包后的 app 不检测。

    :param on_progress: 下载进度回调
    :return: (success, message)
    """
    # 打包环境直接跳过（app 已内置 ffmpeg）
    if getattr(sys, 'frozen', False):
        return True, '已打包，跳过检测'

    if is_ffmpeg_available():
        logger.info('ffmpeg.exe 已存在，无需下载')
        return True, 'ffmpeg.exe 已就绪'

    logger.info('本地未找到 ffmpeg.exe，开始下载')
    return download_ffmpeg(on_progress=on_progress)