# 多媒体播放器 项目规则

## 概述
基于 PyQt5 的桌面多媒体播放器，支持视频/音频播放、裁剪、截图等功能，可跨平台（Windows/macOS）运行。

## 技术栈
- **语言**: Python 3.14+
- **GUI 框架**: PyQt5 5.15.10
- **视频处理**: OpenCV 4.8+ (numpy>=2.0,<3.0)
- **打包**: PyInstaller 6.15+
- **数据库**: SQLite3 (via apsw)
- **日志**: loguru 0.7.0
- **图像处理**: Pillow 10.4+
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
  - `scripts\build.bat nobump` — 构建但不递增版本号
  - `scripts\build.bat clean` — 清理构建产物
- **单独补发 Release**: `scripts\push_release.bat`
- **清理构建产物**: `scripts\clean.bat`（或 `scripts\build.bat clean`）
- **版本号**: `VERSION` 文件是唯一真源，一行语义化版本号（如 `1.0.0`）

### Python 代码校验（替代构建）
- **语法检查**: `python -m py_compile <文件>` （只检查语法不执行）
- **不要自己跑构建**：构建由用户手工执行（见 `.clinerules/rules.md`）

### 交流约定（强制）
- 所有思考、分析、回答必须使用中文
- 代码注释可使用中文或英文

### 终端管理（强制）
- **不要假设终端类型！** 实际可能是 PowerShell 也可能是 cmd，每次执行命令前**必须先探测**。
  - 探测命令：`$PSVersionTable`
    - 输出含版本信息（`Name`/`PSVersion` 等）→ **PowerShell**
    - 报 `is not recognized` → **cmd**
  - **PowerShell 语法**：分隔用 `;`、重定向 `2>$null`、注释 `#`、变量 `$env:VAR`、末尾 `; exit`
  - **cmd 语法**：分隔用 `&`/`&&`、重定向 `2>nul`、注释 `rem`、变量 `%VAR%`、末尾 `& exit`
  - 禁止用 `cmd /c` 包裹命令
- **终端内容标识（必须）**：每个新终端首条命令必须是标识头：
  ```
  PowerShell: echo "=== task-N-用途 ==="
  cmd:        echo === task-N-用途 ===
  ```
  - `N` 为递增序号（从 1 开始，本次请求范围内唯一）
  - `用途` 为简短英文描述（如 build、git、test）
- **终端自关闭（强制）**：每条命令末尾加自关闭语句：
  ```
  PowerShell: ...; exit
  cmd:        ... & exit
  ```
- **禁止主动杀进程**：`taskkill /f /im cmd.exe` 会误伤用户自己的 cmd。

### Git 操作约定（强制）
- **禁用分页器**：所有 `git` 命令必须加 `--no-pager` 参数，避免输出被 less 分页器截断需要手动翻页。
  - 正确：`git --no-pager diff "文件路径"`、`git --no-pager log -n 10`、`git --no-pager status`
  - 不要省略 `--no-pager`，即使 `PAGER=cat` 环境变量已设置，git 自身的 pager 配置优先级更高会覆盖它。
- **推送只推当前分支**：禁止 `git push --all` / `--mirror`；禁止一条命令推多个分支。

### 临时文件管理（强制）
- 所有中间产物（命令输出、临时脚本、状态/轮询文件、探针日志、临时 JSON / CSV）全写 `tmp\`
- 每完成一个用户请求后，清理本次产生的临时文件：`Remove-Item -Recurse -Force tmp`
- `tmp\` 被 `.gitignore` 忽略（`/tmp/`），可放心当垃圾桶

### 知识库管理
- 知识库位于 `memory-bank/`，索引文件 `memory-bank/README.md`
- 开工读索引 → 只读命中条目；收工照 `memory-bank/WRITING.md` 回填
- 禁止 `read all` 知识库、禁止扫全仓库

### 构建日志
- **每次构建自动双写**：控制台实时输出 + 完整日志写入 `build\build_full.log`
- 实现原理：首轮调用检测无 `--log` 参数 → PowerShell 管道重新调用自身 `--log` → 所有 stdout/stderr 经 `ForEach-Object` 同时输出到控制台和 `StreamWriter`
- 日志文件 UTF-8 无 BOM，`AutoFlush=true` 保证实时可 tail
- `build\` 目录被 `.gitignore` 忽略

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