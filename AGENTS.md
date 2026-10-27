# 多媒体播放器 (multimedia_player) – Architecture Guide

## Overview

基于 PyQt5 的桌面多媒体播放器，支持视频/音频播放、裁剪、截图等功能，可跨平台（Windows/macOS）运行。

---

## Entry Points

**Main Entry** (`Player.py`):
应用程序启动入口，初始化 QApplication、加载配置、启动主窗口。

---

## Architecture

```
multimedia_player/
├── Player.py                         # 主入口，应用程序启动
├── VERSION                           # 版本号唯一真源
├── requirement.txt                   # Windows 依赖
├── requirement_mac.txt               # macOS 依赖
├── src/
│   ├── __init__.py
│   ├── data_manager/
│   │   ├── config_manager.py         # 配置管理
│   │   ├── position_manager.py       # 窗口位置管理
│   │   └── sqlite3_client.py         # SQLite 客户端
│   ├── layout/
│   │   ├── custom_slider.py          # 自定义滑块组件
│   │   ├── custom_title_bar.py       # 自定义标题栏
│   │   ├── floating_control_panel.py  # 浮动控制面板
│   │   ├── pic_input_layout.py       # 图片输入布局
│   │   ├── pic_show_layout.py        # 图片展示布局
│   │   ├── range_slider.py           # 范围滑块
│   │   ├── video_cut_thread.py       # 视频裁剪线程
│   │   └── video_show_layout.py      # 视频展示布局
│   └── utils/
│       └── utils.py                  # 工具函数
├── scripts/
│   ├── build.bat                     # Windows 一键构建 + 打包
│   ├── build_mac.sh                  # macOS 构建脚本
│   ├── push_release.bat              # 单独补发 GitHub Release
│   └── start.sh                      # 启动脚本
└── memory-bank/                      # 知识库
```

---

## Component Tree

```
Player.py (QApplication)
├── CustomTitleBar          # 自定义标题栏（最小化/最大化/关闭）
├── VideoShowLayout         # 视频播放区域（OpenCV 帧渲染）
│   ├── CustomSlider        # 播放进度条
│   └── FloatingControlPanel # 浮动控制面板（播放/暂停/音量）
├── PicShowLayout           # 图片展示区域（Pillow 渲染）
├── PicInputLayout          # 图片导入布局
├── RangeSlider             # 视频裁剪范围选择
└── VideoCutThread          # 视频裁剪后台线程（QThread）
```

---

## Data Flow

```
1. User opens media file → Player loads via OpenCV/Pillow
2. Video: frame-by-frame rendering via QTimer + OpenCV
3. Audio: synchronized playback
4. Settings persisted via config_manager.py → SQLite
5. Window position: position_manager.py saves/restores geometry
```

---

## Build

- **打包**: PyInstaller 6.15+（onedir + onefile + zip）
- **版本号**: `VERSION` 文件是唯一真源
- **日志**: `build\build_full.log`（build.bat 自动双写）
- **完整构建**: `scripts\build.bat`
- **自测**: `python -m py_compile <文件>`

---

## Key Dependencies

| Dependency | Purpose |
|-----------|---------|
| PyQt5 5.15.10 | GUI 框架 |
| OpenCV 4.8+ | 视频处理 |
| Pillow 10.4+ | 图像处理 |
| loguru 0.7.0 | 日志 |
| apsw | SQLite 客户端 |
| send2trash 1.8.3 | 安全删除 |
| pywin32 | Windows API |