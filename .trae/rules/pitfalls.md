# 多媒体播放器 工作区避坑规则

> 执行命令或操作过程中遇到的坑，自动记录在此。每条包含：现象、原因、解决方案。

## 已记录坑点

### 1. RunCommand 无法复用已有终端 + 终端清理不可靠
- **现象**：
  1. 执行命令时指定 `target_terminal` 为上一次返回的终端 ID，系统仍然会新开一个终端。
  2. 每个 `RunCommand` 都会打开一个新终端，包括清理终端自身的命令，导致终端越清越多。
- **原因**：
  1. `target_terminal` 参数指定已有 ID 时未生效，每次调用都分配新终端——这是工具层面的限制，无法通过规则规避。
  2. 任何基于 `RunCommand` 的终端清理方案（杀进程、自杀式关闭）都不可靠，因为清理命令本身也会开新终端。
- **解决方案/规避**：
  - **接受现实**：无法在工具层面强制复用或清理终端。
  - **唯一可靠方案 —— 命令末尾 `& exit` 自关闭**：
    - 所有短命令（git、echo 等）末尾加 `& exit`，命令执行完终端自动关闭。
    - **关键**：如果命令中包含 `.bat` 或 `.cmd` 文件，必须用 `call` 调用（如 `call build.bat`），否则 cmd 会把控制权转移给该脚本不返回，后面的 `& exit` 不会执行。
    - 格式：`command args & exit`（cmd 语法，注意是 `&` 不是 `;`）。
  - **终端命名（必须）**：每个新终端首条命令必须是标识头：
    ```cmd
    echo === task-N-用途 ===
    ```
  - **禁止使用 `taskkill /f /im cmd.exe`**，会误伤用户自己的 cmd。
  - `StopCommand` 只能停止正在运行的命令，不会关闭终端会话。

### 2. cmd 终端中使用 PowerShell 语法会报错
- **现象**：在 cmd 终端中执行 `#` 开头的注释或 `2>$null` 等 PowerShell 语法，会报 `'#' is not recognized as an internal or external command`。
- **原因**：cmd 和 PowerShell 语法不同，`#` 不是 cmd 的注释符，`2>$null` 也不是 cmd 的重定向语法。
- **解决方案/规避**：
  - 当前环境默认是 cmd 终端，不要在命令中使用 `#` 注释或 PowerShell 专属语法。
  - cmd 的注释用 `rem`，重定向用 `2>nul`（无 `$`）。
  - 命令末尾用 `& exit` 关闭终端。

### 3. `.bat` 文件编码必须是 UTF-8 无 BOM + CRLF；`chcp 65001` 位置有讲究
- **现象**：
  1. `.bat` 文件带 BOM 时第一行 `@echo off` 变 garbage（cmd 报错/首行不生效）
  2. `chcp 65001` 放在 `title` **之前**会导致 title 中文行被 cmd 错误解析（如 `'uild' is not recognized`）
  3. 完全不用 `chcp 65001` 时，UTF-8 中文 echo 在 GBK 默认代码页的 cmd 窗口中显示为乱码
- **原因**：
  1. cmd.exe 对 BOM 敏感
  2. `chcp 65001` 切换代码页后，cmd 重新解析 `title` 行中的多字节 UTF-8 中文时发生字节混淆
  3. cmd 默认代码页是 GBK（936），直接输出 UTF-8 中文 = 乱码
- **解决方案/规避**：
  1. `.bat` 文件：UTF-8 无 BOM、CRLF 行尾
  2. `chcp 65001 >nul 2>nul` 必须放在 `title` **之后**、第一个中文 echo **之前**
  3. 标题行保留中文也没问题（只要 `chcp` 在其后）

### 4. 批处理 `if/for ( )` 块内 `%ERRORLEVEL%` 取到旧值
- **现象**：`( )` 块内用 `%ERRORLEVEL%` 判断上一条命令的退出码，永远走到旧值对应的分支（假成功/假失败）
- **原因**：`%VAR%` 是解析期展开（进块前就替换好了），`!VAR!` 才是运行时展开
- **解决方案/规避**：
  - 用 `setlocal enabledelayedexpansion` + `!ERRORLEVEL!` / `!VAR!`
  - 退出码判断优先用 `if errorlevel N` 结构

### 5. `rd /s/q` 语法在 Windows cmd 中不合法
- **现象**：`rd /s/q build` 报 `The syntax of the command is incorrect`
- **原因**：Windows cmd 要求 `rd` 的开关用空格分隔：`rd /s /q`
- **解决方案/规避**：一律写 `rd /s /q <目录>`

### 6. PyInstaller 打包后 OpenCV/numpy 找不到模块
- **现象**：PyInstaller 打包成功，但运行 `.exe` 时报 `ModuleNotFoundError: No module named 'cv2'` 或 `.dll` 加载失败
- **原因**：PyInstaller 的依赖分析无法自动检测到某些动态导入的模块（如 OpenCV 的 `.dll` 链）
- **解决方案/规避**：
  - 添加 `--hidden-import=cv2 --hidden-import=numpy` 参数
  - 或在 `.spec` 文件的 `hiddenimports=[]` 列表中添加
  - 必要时用 `--add-binary` 手动指定 `.dll` 路径

### 7. pip 输出重定向到 nul 导致误判卡死
- **现象**：`pip install -r requirement.txt > nul 2>&1` 运行时终端无任何输出，用户以为卡住了
- **原因**：所有输出（包括进度条和下载状态）被重定向吞掉
- **解决方案/规避**：
  - 不要让 pip 输出全部进 `nul`，保留正常输出
  - 如果必须静默，用 `> tmp\pip_log.txt 2>&1` 至少留日志文件可查

### 8. `for %%i in ("%~dp0..") do set "PROJECT_ROOT=%%~fi"` 不包含末尾 `\`
- **现象**：`if not exist "%PROJECT_ROOT%VERSION"` 实际查找路径为 `D:\...\multimedia_playerVERSION`（缺少 `\` 分隔符），始终判定文件不存在
- **原因**：`%%~fi` 展开为完整路径时不追加 `\`
- **解决方案/规避**：
  - 一律写成 `set "PROJECT_ROOT=%%~fi\"`（末尾加 `\`）
  - 或用 `if not exist "%PROJECT_ROOT%\VERSION"` 引用

### 9. `pip install -i %VAR% --trusted-host HOST` 变量为空时 `--trusted-host` 被误当 `-i` 参数
- **现象**：`pip install pyinstaller -i %PIP_MIRROR% --trusted-host pypi.tuna.tsinghua.edu.cn` 当 `%PIP_MIRROR%` 为空时，pip 把 `--trusted-host` 当 `-i` 的 URL 值，把 `pypi.tuna.tsinghua.edu.cn` 当包名，报 `The index url "--trusted-host" seems invalid` + `No matching distribution found for pypi.tuna.tsinghua.edu.cn`
- **原因**：cmd 变量为空时参数位置漂移，`-i` 吞掉下一个 token
- **解决方案/规避**：pip 镜像源直接硬编码在命令中，不用变量

### 10. PyInstaller `--specpath` 改变 `--add-data` 相对路径基准
- **现象**：`--specpath "build"` + `--add-data="libs\ffmpeg\ffmpeg.exe;ffmpeg"` → PyInstaller 在 `build\libs\ffmpeg\ffmpeg.exe` 找文件，报 `Unable to find`
- **原因**：`--specpath` 指定的目录会成为 `--add-data` 相对路径的解析基准（而非当前工作目录）
- **解决方案/规避**：`--add-data` 一律使用绝对路径：`--add-data="%PROJECT_ROOT%libs\ffmpeg\ffmpeg.exe;ffmpeg"`