# 多媒体播放器 项目规则

## 概述
基于 PyQt5 的桌面多媒体播放器，支持视频/音频播放、裁剪、截图等功能，可跨平台（Windows/macOS）运行。

## 技术栈
- **语言**: Python 3
- **GUI 框架**: PyQt5 5.15.10
- **视频处理**: OpenCV 4.7.0.72 (numpy<2.0)
- **打包**: PyInstaller 6.10.0
- **数据库**: SQLite3 (via apsw)
- **日志**: loguru 0.7.0
- **图像处理**: Pillow 10.0.1
- **其他**: send2trash 1.8.3, pywin32 (Windows)

## 目录结构
```
multimedia_player/
├── Player.py                         # 主入口，应用程序启动
├── VERSION                           # 版本号唯一真源
├── requirement.txt                   # Windows 依赖
├── requirement_mac.txt               # macOS 依赖
├── src/
│   ├── __init__.py
│   ├── data_manager/
│   │   ├── __init__.py
│   │   ├── config_manager.py         # 配置管理
│   │   ├── position_manager.py       # 窗口位置管理
│   │   └── sqlite3_client.py         # SQLite 客户端
│   ├── layout/
│   │   ├── __init__.py
│   │   ├── custom_slider.py          # 自定义滑块组件
│   │   ├── custom_title_bar.py       # 自定义标题栏
│   │   ├── floating_control_panel.py  # 浮动控制面板
│   │   ├── pic_input_layout.py       # 图片输入布局
│   │   ├── pic_show_layout.py        # 图片展示布局
│   │   ├── range_slider.py           # 范围滑块
│   │   ├── video_cut_thread.py       # 视频裁剪线程
│   │   └── video_show_layout.py      # 视频展示布局
│   └── utils/
│       ├── __init__.py
│       └── utils.py                  # 工具函数
├── scripts/
│   ├── build.bat                     # Windows 一键构建 + 打包
│   ├── build_mac.sh                  # macOS 构建脚本
│   ├── push_release.bat              # 单独补发 GitHub Release
│   └── start.sh                      # 启动脚本
├── img/                              # 文档配图
├── 解码器/                            # LAVFilters 解码器安装包
├── .clinerules/                      # Cline 强制规则
├── memory-bank/                      # 知识库
└── .trae/                            # Trae IDE 项目规则
```

## 关键约定

### 构建命令
- **完整构建**: 通过 `scripts\build.bat` 执行（onedir + onefile + zip）
  - `scripts\build.bat` — 完整构建（onedir + onefile + zip + 可选 Release）
  - `scripts\build.bat onedir` — 仅构建目录版
  - `scripts\build.bat onefile` — 仅构建单文件版
  - `scripts\build.bat zip` — 仅打包 zip
  - `scripts\build.bat norelease` — 构建但不自动推送 Release
  - `scripts\build.bat clean` — 清理构建产物
- **单独补发 Release**: `scripts\push_release.bat`
- **版本号**: `VERSION` 文件是唯一真源，一行语义化版本号（如 `1.0.0`）

### Python 代码校验（替代构建）
- **语法检查**: `python -m py_compile <文件>` （只检查语法不执行）
- **不要自己跑构建**：构建由用户手工执行（见 `.clinerules/rules.md`）

### 交流约定（强制）
- 所有思考、分析、回答必须使用中文
- 代码注释可使用中文或英文

### 终端管理（强制）
- **终端内容标识（必须）**：每个新终端首条命令必须是标识头：
  ```cmd
  echo === task-N-用途 ===
  ```
  - `N` 为递增序号（从 1 开始，本次请求范围内唯一）
  - `用途` 为简短英文描述（如 build、git、test）
- **终端自关闭（强制）**：每条命令末尾加 `& exit`：
  ```cmd
  echo === task-1-git === && cd /d "d:\..." && git status & exit
  ```
- **禁止主动杀进程**：`taskkill /f /im cmd.exe` 会误伤用户自己的 cmd。

### 临时文件管理（强制）
- 所有中间产物（命令输出、临时脚本、状态/轮询文件、探针日志、临时 JSON / CSV）全写 `tmp\`
- 每完成一个用户请求后，清理本次产生的临时文件：`rmdir /s /q tmp`
- `tmp\` 被 `.gitignore` 忽略（`/tmp/`），可放心当垃圾桶

### 知识库管理
- 知识库位于 `memory-bank/`，索引文件 `memory-bank/README.md`
- 开工读索引 → 只读命中条目；收工照 `memory-bank/README.md` §5 模板回填
- 禁止扫全仓库

### 命令等待
- 在终端执行命令后必须等待命令执行完成，不要命令一发出就立刻查看输出并断定执行失败

## 常用操作
- **语法检查**: `python -m py_compile Player.py` 或 `python -m py_compile src/layout/video_show_layout.py`
- **完整构建发布**: `scripts\build.bat`（含 onedir + onefile + zip + GitHub Release）
- **仅构建不发布**: `scripts\build.bat norelease`
- **清理构建缓存**: `scripts\build.bat clean`

## 项目记忆
- Git 仓库位于 `D:\WorkSpace\test\multimedia_player`，所有代码变更通过 git 管理
- 版本号由 `VERSION` 文件管理
- GitHub Release 通过 `gh` CLI 推送