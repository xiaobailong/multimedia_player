# -*- coding: utf-8 -*-
"""媒体扩展名清单：扫描列表 / 播放判定 / 归集共用同一份。

这里只放扩展名（纯数据，不依赖 PyQt），所以 `src/collect/collect_service.py`
这类纯逻辑模块也能安全引用，不会再出现"列表只认 mp4、归集认 17 种"的口径分裂。
"""
# 支持的图片扩展名（与 `PicShowLayout.is_pic()` / 图片列表扫描 / 归集共用）
# 口径：只要能显示就收 —— Qt 原生可读的放前面，需要 Pillow 兜底解码的单独标注
IMAGE_SUFFIXES = (
    # JPEG 家族 / PNG / BMP / GIF / WebP
    '.jpg', '.jpeg', '.jpe', '.jfif',
    '.png',
    '.bmp', '.dib',            # .dib：Qt 不认这个扩展名，走 Pillow 兜底
    '.gif', '.webp',
    # TIFF / 图标 / TGA
    '.tif', '.tiff', '.ico', '.tga',
    # Netpbm / X11 / WBMP（Qt 原生可读）
    '.pbm', '.pgm', '.ppm', '.pnm',
    '.xpm', '.xbm', '.wbmp',
    # 矢量（依赖 QtSvg 插件，开发环境已验证可读）
    '.svg', '.svgz',
    # 需要 Pillow 兜底解码（QImage 读不了 / 直接读会崩）
    '.apng', '.pcx', '.avif')

# 显示时直接交给 Pillow、不要先试 QImage 的扩展名。
# 判据：`QImageReader.supportedImageFormats()` 里没有这些名字（Qt5 没有对应插件）。
# 为什么必须绕开：窗口里已经加载了图标类（ico/icns/cur…）图片插件后，
# 拿"Qt 不认识的扩展名"让 Qt 逐个插件嗅探，会在 C++ 层直接访问冲突崩溃
# （实测 .dib / .pcx / .pnm / .apng 都会崩，见 ISSUE-011）。
PILLOW_ONLY_SUFFIXES = ('.jpe', '.jfif', '.dib', '.pnm', '.pcx', '.avif', '.apng')


# 常见视频扩展名（与 `VideoShowLayout.is_video()`、视频列表扫描、归集共用）
# 注意：能否真正解码取决于系统解码器 / LAV Filters，这里只决定"要不要当视频列出来"
VIDEO_SUFFIXES = (
    # 最常见容器
    '.mp4', '.m4v', '.mkv', '.mov', '.avi', '.wmv', '.flv', '.webm',
    # MPEG 系
    '.mpg', '.mpeg', '.mpe', '.m2v', '.vob', '.ts', '.mts', '.m2ts',
    # 手机 / 其它常见
    '.3gp', '.3g2', '.rmvb', '.rm', '.ogv', '.asf', '.f4v', '.divx')
