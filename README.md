# 多媒体播放器

基于 PyQt5 的桌面多媒体播放器，支持视频/音频播放、图片浏览、视频裁剪截图、媒体评分、文件归集，以及与「密册」兼容的私密媒体加密功能。可跨平台（Windows / macOS）运行。

![版本](https://img.shields.io/badge/version-1.0.6-blue)
![Python](https://img.shields.io/badge/python-3.14%2B-green)
![PyQt5](https://img.shields.io/badge/PyQt5-5.15.10-green)

## 功能特性

### 🎬 视频播放
- 支持常见视频格式（mp4 / mkv / mov / avi / flv / webm 等）
- 播放 / 暂停、上一个 / 下一个、快进 / 快退
- 全屏播放 + 悬浮控制面板（Esc 退出）
- 视频截图（保存为 jpg，可自定义输出目录）
- 视频裁剪（指定起止时间，无损裁剪）
- 播放进度记忆（关闭时自动保存，下次打开续播）

### 🖼️ 图片浏览
- 支持常见图片格式（bmp / png / jpg / webp / gif 等）
- 幻灯片自动播放（可自定义间隔）
- 上一张 / 下一张、暂停
- 悬浮玻璃风格控制面板

### 📁 文件管理
- 左侧目录树浏览，文件名截断 + 悬浮显示全名和大小
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
├── Player.py                  # 主入口，应用程序启动
├── VERSION                    # 版本号唯一真源
├── requirement.txt            # Windows 依赖
├── requirement_mac.txt        # macOS 依赖
├── src/
│   ├── __init__.py
│   ├── data_manager/          # 配置 / 位置 / 评分 / SQLite 管理
│   ├── layout/                # UI 布局与组件（视频、图片、滑块、对话框等）
│   ├── collect/               # 归集功能（按评分/关键字/路径批量拷贝）
│   ├── private_mode/          # 密册模式（密钥包、加解密、批量任务）
│   └── utils/                 # 工具函数
├── scripts/
│   ├── build.bat              # Windows 一键构建 + 打包
│   ├── build_mac.sh           # macOS 构建脚本
│   └── push_release.bat       # 单独补发 GitHub Release
├── libs/ffmpeg/               # ffmpeg 可执行文件（截图 / 裁剪）
├── 解码器/                     # LAVFilters 解码器安装包
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

Windows 下播放部分视频格式可能需要安装 LAVFilters 解码器，安装包位于 `解码器/` 目录。

## 许可证

本项目仅供学习交流使用。