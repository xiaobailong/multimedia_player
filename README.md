[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

# 多媒体播放器

基于 PyQt5 的桌面多媒体播放器，支持视频/音频播放、图片浏览、视频裁剪截图、媒体评分、文件归集，以及与「密册」兼容的私密媒体加密功能。可跨平台（Windows / macOS）运行。

![版本](https://img.shields.io/badge/version-1.0.10-blue)
![Python](https://img.shields.io/badge/python-3.14%2B-green)
![PyQt5](https://img.shields.io/badge/PyQt5-5.15.10-green)

## 功能特性

### 🎬 视频播放
- 支持常见视频格式（mp4 / mkv / mov / avi / flv / webm 等）及音频格式
- 播放 / 暂停、上一个 / 下一个、快进 / 快退
- 列表播放：加载当前目录下所有视频依次播放
- 单视频循环播放（按钮切换）
- 全屏播放 + 悬浮控制面板（Esc 退出）
- 视频截图（保存为 jpg，可自定义输出目录）
- 视频裁剪（指定起止时间，无损裁剪）
- 播放进度记忆（关闭时自动保存，下次打开续播）

### 🖼️ 图片浏览
- 支持常见图片格式（bmp / png / jpg / webp / gif 等）
- 幻灯片自动播放（通过「设置 → 幻灯片」自定义播放间隔，立即生效并持久化）
- 上一张 / 下一张、暂停
- 悬浮玻璃风格控制面板（可通过「视图 → 显示控制器」切换显隐）

### 📁 文件管理
- 左侧目录树浏览，文件名截断 + 悬浮显示全名和大小
- 打开目录（Ctrl+O）：选择目录作为左侧树的根，启动时优先恢复上次打开的目录
- 右键菜单：复制到、移动、删除（移至回收站）、刷新
- 加载为幻灯片列表 / 视频列表
- 设置为截图路径 / 剪切路径
- 设置默认展开目录

### 🔐 密册模式（私密媒体加密）
与「密册」应用完全兼容的 AES-256-GCM 加解密方案，支持密钥包互导。

- **密钥管理**：导入 / 导出密钥包（SQLite `.db` 格式，兼容旧版 JSON）、查看密钥状态
- **文件加密**：批量加密目录下的图片和视频，同时加密文件内容与文件名（32 位随机 hex）
- **文件解密**：批量解密，恢复原文件名
- **解密即播**：密册模式下点击密文文件自动解密到内存缓存并播放，关闭时自动清理明文
- **密钥安全**：KEK 包裹 DEK，密钥包可离线备份；退出时自动清理解密缓存

### ⭐ 媒体评分
- 数字键 1~5 为当前图片 / 视频打分
- 按内容指纹存库，文件移动或改名后评分仍保留
- 状态栏实时显示当前媒体评分

### 📦 归集功能
按条件批量拷贝媒体文件到指定目录：
- 按评分归集（筛选指定星级的媒体）
- 按关键字归集（文件名匹配）
- 按路径归集（指定源目录）
- 支持图片 / 视频 / 全部类型过滤
- 后台线程执行，不卡界面

### 🎨 界面与交互
- 全局暗色主题（Catppuccin Mocha 风格）
- 无边框窗口 + 自定义标题栏
- 文件列表面板可切换显隐（Ctrl+B）
- 图片悬浮控制面板可切换显隐
- 退出全屏动画平滑恢复窗口位置

### 🗂️ 菜单栏
顶部菜单栏提供全部功能入口：

- **文件**：打开目录（Ctrl+O）、退出（Ctrl+Q）
- **密钥**：导入 / 导出密钥包、查看密钥状态（密册模式专用）
- **视图**：切换普通 / 私密模式、切换文件列表面板显隐、切换图片悬浮控制器显隐
- **归集**：按评分 / 关键字 / 路径批量归集媒体文件
- **设置**：幻灯片播放间隔设置（秒，立即生效并持久化）
- **帮助**：解码器（查看 LAV Filters 安装状态、自动安装或手动下载引导）、关于（版本号、Python / Qt 版本、操作系统）

## 快捷键

| 快捷键 | 功能 | 适用范围 |
|--------|------|----------|
| `Space` | 播放 / 暂停 | 视频、图片 |
| `←` / `→` | 上一个 / 下一个 | 视频、图片 |
| `↑` / `↓` | 快进 / 快退 | 视频 |
| `A` / `D` | 快退 / 快进（同方向键） | 视频 |
| `W` / `E` | 上一个 / 下一个 | 视频 |
| `F` | 全屏 / 退出全屏 | 全局 |
| `Esc` | 退出全屏 | 全局 |
| `S` | 截图 | 视频 |
| `Z` | 设置裁剪起点 | 视频 |
| `X` | 设置裁剪终点 | 视频 |
| `C` | 执行视频裁剪 | 视频 |
| `1` ~ `5` | 评分 1~5 星 | 图片、视频 |
| `Delete` / `Ctrl+D` | 删除当前文件 | 图片、视频 |
| `Ctrl+B` | 切换文件列表面板 | 全局 |
| `Ctrl+O` | 打开目录作为树的根 | 全局 |
| `Ctrl+Q` | 退出 | 全局 |

## 技术栈

- **语言**：Python 3.14+
- **GUI 框架**：PyQt5 5.15.10
- **视频处理**：OpenCV 4.8+（numpy >= 2.0, < 3.0）
- **加密**：cryptography >= 42（AES-256-GCM）
- **数据库**：SQLite3（via apsw）
- **日志**：loguru 0.7.0
- **图像处理**：Pillow 10.4+
- **打包**：PyInstaller 6.15+
- **其他**：send2trash 1.8.3, platformdirs, pywin32 (Windows)

## 目录结构

```
multimedia_player/
├── Player.py                  # 主入口：日志 / 单实例锁 / 启动事件循环（只做启动控制）
├── VERSION                    # 版本号唯一真源
├── requirement.txt            # Windows 依赖
├── requirement_mac.txt        # macOS 依赖
├── src/
│   ├── __init__.py
│   ├── window/                # 主窗口（原 Player.py 里的窗口逻辑，按职责拆分）
│   │   ├── main_window.py            # MainWindow：状态 + 界面组装 + 信号接线
│   │   ├── theme.py                  # 全局 QSS、目录树箭头图标
│   │   ├── i18n.py                   # Qt 标准对话框中文翻译
│   │   ├── menu_bar.py               # 菜单栏构建
│   │   ├── file_tree.py              # 左侧文件树控件
│   │   ├── file_delegate.py          # 文件名截断 / 悬浮提示委托
│   │   └── *_actions.py              # media / view / rating / collect / private / key / tool
│   ├── data_manager/          # 配置 / 位置 / 评分 / SQLite 管理
│   ├── layout/                # UI 布局与组件（视频、图片、滑块、对话框等）
│   ├── collect/               # 归集功能（按评分/关键字/路径批量拷贝）
│   ├── private_mode/          # 密册模式（密钥包、加解密、批量任务）
│   └── utils/                 # 工具函数
│       ├── decoder_manager.py        # LAV Filters 检测 / 下载 / 安装
│       ├── decoder_install_thread.py # 解码器安装后台线程
│       ├── ffmpeg_manager.py         # ffmpeg.exe 检测 / 下载 / 解压
│       ├── ffmpeg_download_thread.py # ffmpeg 下载后台线程
│       ├── multipart_downloader.py   # 通用多线程并行下载器
│       ├── media_types.py            # 图片 / 视频扩展名清单（扫描、播放判定、归集共用）
│       └── utils.py                  # 路径 / 指纹等通用工具
├── scripts/
│   ├── build.bat              # Windows 一键构建 + 打包
│   ├── build_mac.sh           # macOS 构建脚本
│   └── push_release.bat       # 单独补发 GitHub Release
├── libs/ffmpeg/               # ffmpeg 可执行文件（截图 / 裁剪）
└── img/                       # 文档配图
```

## 快速开始

### 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd multimedia_player

# 安装依赖（Windows）
pip install -r requirement.txt

# 安装依赖（macOS）
pip install -r requirement_mac.txt
```

### 运行

```bash
python Player.py
```

## 密册模式使用说明

1. **导入密钥**（可选）：菜单 `密钥 → 导入密钥`，选择密册导出的 `.db` 密钥包
   - 如未导入密钥，首次加密时会自动生成新密钥，可通过 `密钥 → 导出密钥` 备份
2. **进入密册模式**：菜单 `视图 → 私密模式`
3. **打开私密库**：点击「打开私密库」选择加密媒体所在目录
4. **加密**：在左侧目录树右键 → `加密该路径下的图片和视频`
5. **解密**：右键 → `解密该路径下的文件`
6. **播放**：点击密文文件自动解密并播放

> ⚠️ 密钥包等同于明文密钥，配合私密目录可解密全部文件；请离线保存或放进加密网盘，不要外传。

## 构建打包

通过 `scripts\build.bat` 执行完整构建（onedir + onefile + zip + 可选 GitHub Release）：

```bash
# 完整构建（含 onedir + onefile + zip + Release）
scripts\build.bat

# 仅构建目录版
scripts\build.bat onedir

# 仅构建单文件版
scripts\build.bat onefile

# 仅打包 zip
scripts\build.bat zip

# 构建但不自动推送 Release
scripts\build.bat norelease

# 构建但不递增版本号
scripts\build.bat nobump

# 清理构建产物
scripts\build.bat clean
```

## 解码器说明

Windows 下播放部分视频格式依赖 LAV Filters 解码器。本程序会在启动时自动检测，若未安装则引导自动下载并静默安装；自动安装失败时会提示手动下载，地址：https://github.com/Nevcairiel/LAVFilters/releases

- **自动检测**：通过注册表卸载项、安装目录 `.ax` 文件、COM CLSID 三重检测
- **多源下载**：依次尝试国内 GitHub 镜像（ghproxy 系列）和官方直连，规避网络限制
- **多线程并行下载**：支持 HTTP Range 分块并行下载（默认 8 线程），服务器不支持时自动降级单线程
- **缓存复用**：安装包持久化缓存到 `data/decoder_cache/`，安装失败时保留缓存，下次启动直接复用安装，避免重复下载；安装成功后自动清理缓存
- **后台线程**：下载 + 安装在后台 QThread 中执行，不阻塞 UI

## ffmpeg 说明

视频截图 / 裁剪功能依赖 `ffmpeg.exe`。本程序会在开发环境运行时及构建脚本中自动检测，若 `libs/ffmpeg/ffmpeg.exe` 不存在则自动从网络下载并解压就位。

- **下载源**：BtbN/FFmpeg-Builds latest release，多源 fallback（国内镜像 → GitHub 直连）
- **多线程下载**：与解码器共用通用多线程下载器
- **仅开发环境检测**：打包后的 app 已通过 `--add-data` 内置 ffmpeg.exe，运行时不再检测下载

## 许可证

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 感谢

> This is an optional voluntary donation to support project development.
> Donation is NOT required to use this software and grants no commercial license.

如果这个工具帮到了您，欢迎随意赞赏，无论多少都是对我最大的鼓励！

![赞赏](img/pay.jpg)