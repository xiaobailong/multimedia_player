# 已排查问题（issues-solved）

> 追加式记录：**永远不要删旧条目**（状态可以改）。编号连续递增，模板见 `README.md` §5。
> 每条的「复发判据」必须是一条能 5 秒定论的命令 —— 下次遇到同现象先跑它，别重新排查。

## ISSUE-001 `build.bat` 三连坑：`chcp 65001` 编码问题 + `rd /s/q` 语法错误 + pip 输出被吞
- 状态: 已修复
- 症状 / 现场:
  1. `cmd.exe /c build.bat` 报 `'uild' is not recognized as an internal or external command`
  2. `rd /s/q build` 报 `The syntax of the command is incorrect`
  3. `pip install -r requirement.txt > nul 2>&1` 看起来卡住不动（实际在下载，但输出全被吞）
  4. （2026-10-21 补充）移除 `chcp 65001` 后，中文 echo 输出全部乱码
- 复发判据:
  问题 1：`chcp 65001` 出现在 `title` 行**之前**（`findstr /n "chcp 65001" scripts\build.bat` 看行号是否 < title 行号）
  问题 2：`findstr /n "rd /s/q" scripts\build.bat` 有输出
  问题 3：`findstr /n "> nul 2>&1" scripts\build.bat` 有匹配 pip 安装行的输出
  问题 4：中文 echo 乱码 + `chcp 65001` 完全不存在
- 根因:
  1. `chcp 65001` 放在 `title` **之前**时，代码页切换导致 cmd.exe 解析 `title 多媒体播放器 Build` 发生 UTF-8/GBK 字节混淆
  2. Windows cmd 要求 `rd` 开关用空格分隔：`rd /s /q`（正确），`rd /s/q` 会报语法错误
  3. 所有 pip 输出重定向到 `nul`，无法看到实时进度，用户以为卡死了
  4. 不设 `chcp 65001` 时，UTF-8 编码的中文在 GBK 默认代码页的 cmd 窗口中显示为乱码
- 证据: 终端回显 + 命令语法文档
- 修法:
  1. `chcp 65001 >nul 2>nul` **必须放在 `title` 之后、第一个中文 echo 之前** —— 这样 title 不受代码页切换影响，
     后续所有中文输出正常显示，且 `cmd.exe /c build.bat` 不会再报 `'uild'`
  2. 全部 `rd /s/q` 改为 `rd /s /q`
  3. 去掉 pip 的 `> nul 2>&1`，让 pip 正常显示输出
- 反例 / 易误判: 以为是 `title` 行本身有误（其实 title 行没问题）；
  以为是"删除 chcp 就万事大吉"（会引入中文乱码）
- 相关文件: `scripts\build.bat`
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-21

## ISSUE-002 pip 新版本不自动更新
- 状态: 已修复
- 症状 / 现场: pip 安装依赖时提示 `A new release of pip is available: 26.2.1 -> 26.2.2`，但不会自动升级，每次安装都会重复提示
- 复发判据: `pip --version` 返回旧版本号
- 根因: `build.bat` 的环境检查段没有调用 `python -m pip install --upgrade pip`
- 修法: 在 `:checkenv` 段添加 `python -m pip install --upgrade pip`
- 反例 / 易误判: 手动等用户说才加，不如直接做成自动步骤
- 相关文件: `scripts\build.bat`
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-21

## ISSUE-003 Pillow 10.0.1 在 Python 3.14 上 `pip install` 失败：`KeyError: '__version__'`
- 状态: 已修复
- 症状 / 现场: `pip install pillow==10.0.1` 报错 `Getting requirements to build wheel did not run successfully.`，
  栈底为 `File "<string>", line 27, in get_version` → `KeyError: '__version__'`
- 复发判据: `python --version` 返回 3.14.x 且 `pip install pillow==10.0.1` 报同样的 `KeyError`
- 根因: Pillow 10.0.1（2023 年发布）的 `setup.py` 用 `exec()` + `compile()` 解析 `src/PIL/_version.py`
  来提取 `__version__`，Python 3.14 的 AST/exec 行为变化导致 `exec(code, namespace)` 后
  `namespace` 中找不到 `__version__` 键
- 证据: 错误栈：`exec(code, locals())` → `get_version()` → `KeyError: '__version__'`；
  路径中含 `Python314`
- 修法: 将 `requirement.txt` 中 `pillow==10.0.1` 改为 `pillow>=10.4.0`，允许 pip 选择
  支持 Python 3.14 的较新版本
- 反例 / 易误判: 容易被误判为"pip 坏了"或"网络问题"，实际是依赖库本身与 Python 版本不兼容；
  从日志看 `numpy`、`opencv-python`、`PyQt5`、`loguru` 都成功下载了，唯独 Pillow 失败，
  说明不是网络问题
- 相关文件: `requirement.txt`
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-21

## ISSUE-004 pip 安装依赖超时：`Connection to pypi.org timed out`
- 状态: 已修复
- 症状 / 现场: `pip install -r requirement.txt` 报 `ConnectTimeoutError(..., 'Connection to pypi.org timed out. (connect timeout=15)')`
- 复发判据: `pip install numpy -i https://pypi.org/simple/` 超时
- 根因: 国内网络直连 PyPI 官方源不稳定，大包下载（如 PyQt5 约 50MB）极易超时
- 修法: 所有 pip 命令添加清华镜像：
  ```
  pip install ... -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
  ```
  `build.bat` 内置 `PIP_MIRROR=%PIP_MIRROR%` 变量（默认清华源），所有 pip 调用自动使用
- 反例 / 易误判: 容易被误判为"没装 Python"或"环境坏了"；实际换源后立刻正常
- 相关文件: `scripts/build.bat`
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-21