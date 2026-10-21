# 踩坑记录（pitfalls）

> 记「**本机环境 / 工具链 / 命令语法**」层面的坑：踩一次就写，不管问题最终有没有修好。
> 每条必须有「正确做法」（可直接复制）与「反例」（别这么写）。模板见 `README.md` §5。

## PIT-001 PyInstaller 打包时 OpenCV/numpy 找不到 ⇒ 用 `--hidden-import`
- 触发条件: `pyinstaller --onefile` 打包含 `cv2` / `numpy` 的 Python 项目
- 错误现象: 打包成功但运行时报 `ModuleNotFoundError: No module named 'cv2'` 或 `.dll` 加载失败
- 正确做法: 添加 hidden-import：
  ```
  pyinstaller --onefile --hidden-import=cv2 --hidden-import=numpy Player.py
  ```
  或在 `.spec` 文件的 `hiddenimports=[]` 中添加
- 反例: 不加 hidden-import 直接打包，运行时才发现缺模块
- 首次记录: 2026-10-21

## PIT-002 批处理 `if/for ( )` 块内 `%ERRORLEVEL%` / `%VAR%` 取到旧值
- 触发条件: 在 `( )` 块内的命令读取同一块内上一条命令设置的变量或退出码
- 错误现象: 用 `%ERRORLEVEL%` 永远走到"旧值"对应的分支，假成功/假失败
- 正确做法: 用 `setlocal enabledelayedexpansion` + `!VAR!` / `!ERRORLEVEL!`
- 反例: `(call :some_label & if %ERRORLEVEL% neq 0 ...)` —— `%ERRORLEVEL%` 是进块前的值
- 首次记录: 2026-10-21

## PIT-003 `.bat` 编码约定：UTF-8 无 BOM + CRLF；`chcp 65001` 位置有讲究
- 触发条件: 新建/改写 `.bat` 文件（尤其含中文 echo 输出或 `title` 行）
- 错误现象: 带 BOM 时第一行 `@echo off` 变 garbage；
  `chcp 65001` 放在 `title` **之前**会导致 title 行被 cmd 错误解析（如 `'uild' is not recognized`）；
  完全不加 `chcp 65001` 则中文 echo 输出在 GBK 终端里乱码
- 正确做法:
  1. UTF-8 无 BOM、CRLF 行尾
  2. `chcp 65001 >nul 2>nul` 放在 `title` **之后**、第一个中文 echo **之前**
  3. 标题行用纯 ASCII 或保留中文均可（只要 `chcp` 在 title 之后就不会出问题）
- 反例: 另存为 UTF-8 with BOM；在 `@echo off` 下一行立刻 `chcp 65001`（title 还没执行就被切换）；
  极端地完全不用 `chcp 65001`（中文全乱码）
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-21

## PIT-004 Python 语法校验：`python -m py_compile` 和 `python -c "compile(...)"` 的区别
- 触发条件: 需要快速校验 `.py` 文件有没有语法错误
- 错误现象: `python -m py_compile` 只在显式语法错误时退出码非 0，某些 import 层面的问题不会报
- 正确做法: 语法检查用 `python -m py_compile <file>`（只检查语法不执行）；
  类型/导入检查用 `python -c "import py_compile; py_compile.compile('<file>', doraise=True)"`
- 反例: 以为 `py_compile` 通过就万事大吉（还要看运行时 import 是否成功）
- 首次记录: 2026-10-21