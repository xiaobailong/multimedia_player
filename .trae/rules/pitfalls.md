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
  - **唯一可靠方案 —— 命令末尾自关闭**：
    - 所有短命令（git、echo 等）末尾加自关闭语句，命令执行完终端自动关闭。
    - **PowerShell**：`command args; exit`
    - **cmd**：`command args & exit`
    - **关键**：如果命令中包含 `.bat` 或 `.cmd` 文件，在 cmd 里必须用 `call` 调用（如 `call build.bat`），否则控制权转移后 `& exit` 不会执行；PowerShell 里直接调用即可。
  - **终端命名（必须）**：每个新终端首条命令必须是标识头：
    - PowerShell: `echo "=== task-N-用途 ==="`
    - cmd: `echo === task-N-用途 ===`
  - **禁止使用 `taskkill /f /im cmd.exe`**，会误伤用户自己的 cmd。
  - `StopCommand` 只能停止正在运行的命令，不会关闭终端会话。

### 2. 不要假设终端类型，先探测再决定语法（重要）
- **现象**：凭经验用 cmd 语法写 `&&`、`2>nul`、`%VAR%`，或用 PowerShell 语法写 `;`、`2>$null`、`$env:VAR`，结果在另一种终端里报错。
- **原因**：RunCommand 实际启动的终端不固定，有时是 PowerShell，有时是 cmd，不能写死。
- **解决方案/规避**：
  - 每次执行命令前**先探测终端类型**。
  - 探测命令：`$PSVersionTable`
    - 输出含 `Name`/`PSVersion` 等版本信息 → **PowerShell**
    - 报 `'$PSVersionTable' is not recognized` → **cmd**
  - 探测后用对应语法：
    - **PowerShell**：分隔 `;`、重定向 `2>$null`、注释 `#`、变量 `$env:VAR`、末尾 `; exit`
    - **cmd**：分隔 `&`/`&&`、重定向 `2>nul`、注释 `rem`、变量 `%VAR%`、末尾 `& exit`
  - 禁止用 `cmd /c` 包裹命令。

### 2.5. git 命令输出被分页器截断，需手动翻页
- **现象**：执行 `git diff`、`git log` 等命令时，输出进入 less 分页器，内容被截断，需要手动翻页或按 q 退出，无法一次性完整显示。
- **原因**：仓库的 git 配置（`core.pager`）启用了分页器，即使运行环境设置了 `PAGER=cat`，git 自身的 pager 配置优先级更高，会覆盖环境变量。
- **解决方案/规避**：
  - 所有 `git` 命令一律加 `--no-pager` 参数：`git --no-pager diff "路径"`、`git --no-pager log -n 10`、`git --no-pager status`
  - 不要省略，环境变量 `PAGER=cat` 对 git 无效。

### 3. `.bat` 文件编码必须是 UTF-8 无 BOM + CRLF；`chcp 65001` 位置有讲究
- **现象**：
  1. `.bat` 文件带 BOM 时第一行 `@echo off` 变 garbage（cmd 报错/首行不生效）
  2. `chcp 65001` 放在任何中文行**之前**→ 后续所有中文行被 cmd 错误解析（如 `'uild' is not recognized`、`'参数时，通过' is not recognized`）
  3. 完全不用 `chcp 65001` 时，UTF-8 中文 echo 在 GBK 默认代码页的 cmd 窗口中显示为乱码
- **原因**：
  1. cmd.exe 对 BOM 敏感
  2. `chcp 65001` 切换代码页后，cmd 重新解析后续行中的多字节 UTF-8 中文时发生字节错位，REM 关键字丢失、title 参数被截断
  3. cmd 默认代码页是 GBK（936），直接输出 UTF-8 中文 = 乱码
- **解决方案/规避**：
  1. `.bat` 文件：UTF-8 无 BOM、CRLF 行尾
  2. `chcp 65001 >nul 2>nul` 必须出现在**所有中文行之后**：PASS 1 中放在 `if` 块内（仅影响子进程编码），PASS 2 中放在 `title` **之后**、第一个中文 echo **之前**
  3. 标题行保留中文也没问题（只要 `chcp` 在其后）
  4. **切勿**把 `chcp 65001` 放在脚本开头（第 2 行），会导致整个脚本的中文 REM/title 全部错位

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

### 11. PowerShell 多行 commit message 解析不可靠
- **现象**：
  1. 在 PowerShell 里用 `git commit -m "第一行`n第二行"` 提交时，消息要么被压成一行，要么报错 `pathspec '...' did not match any file(s) known to git`（消息内容被 git 当成了文件路径参数）。
  2. 消息里含中文、括号、引号时更容易出问题。
- **原因**：
  1. PowerShell 用反引号 `` ` `` 做转义符，换行是 `` `n``（不是 `\n`），但在工具调用的字符串参数传递过程中，反引号换行容易被吞掉或变成字面量。
  2. git 的 `-m` 参数本质只收一个 token，多行内容在命令行参数边界处容易被拆分。
  3. 当 commit message 中包含特殊字符（如 `(`、`)`、`'`、中文）时，PowerShell 的参数解析与 git 的参数解析不一致，会把消息后半段当成路径参数。
- **解决方案/规避**：
  - **首选方案：写临时文件 + `git commit -F`**（最稳，完全绕开命令行参数解析）：
    ```powershell
    New-Item -ItemType Directory -Force tmp | Out-Null
    @'
    feat: 提交标题（第一行）

    详细说明第二行
    第三行可以列点
    - 点 1
    - 点 2
    '@ | Out-File -FilePath tmp/commit_msg.txt -Encoding utf8
    git --no-pager commit -F tmp/commit_msg.txt
    ```
    - 用 PowerShell 的 here-string `@'...'@`（**单引号**形式，不展开变量、不转义）把消息原样写入 `tmp/commit_msg.txt`
    - `git commit -F <文件>` 从文件读取提交消息，换行、中文、特殊字符都原样保留
    - 临时文件放 `tmp/` 下（已被 `.gitignore` 忽略），提交后清理
  - **次选方案：多次 `-m`**（仅适合消息不含特殊字符、且能接受段落间有空行的场景）：
    ```powershell
    git commit -m "feat: 标题" -m "说明第一段" -m "说明第二段"
    ```
    - git 允许用多个 `-m`，每个 `-m` 自动成为一个段落（段落间会插入空行）
    - 中文、括号多时仍可能出问题，不推荐
  - **禁止**：在 `-m` 参数里用 `\n` 或 `` `n`` 写多行消息，PowerShell + git 双层解析后大概率损坏