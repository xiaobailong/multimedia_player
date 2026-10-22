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

## PIT-005 apsw 与 `sqlite3` 模块 API 不同：没有 `executescript`，`cursor.description` 取完行就报错
- 触发条件: 用 apsw 执行多语句 DDL，或在 fetch 之后读 `cursor.description`
- 错误现象:
  1. `AttributeError: 'apsw.Connection' object has no attribute 'executescript'`
  2. `apsw.ExecutionCompleteError: SQL execution never started, or has completed`
     （`_exec_dicts` 里先 `fetchall()` 再读 `cursor.description` 时触发）
- 正确做法:
  1. 多语句脚本按 `;` 拆开逐条 `conn.execute(...)`（见 `src/private_mode/key_store.py` 的 `_run_script`）
  2. 先取列名再迭代结果：
     ```python
     cursor.execute(sql, params)
     names = [d[0] for d in (cursor.description or [])]
     for row in cursor:
         ...
     ```
- 反例: 直接把 `sqlite3` 的写法（`executescript` / `cursor.description` 随时可读）搬到 apsw
- 首次记录: 2026-10-21

## PIT-006 用编辑器「按行插入」追加代码时插到函数中间，会把函数体切成两半（py_compile 查不出）
- 触发条件: 用 `insert_line=N` 在文件末尾追加内容，但 N 算错（例如按旧行数而不是当前行数）
- 错误现象: `python -m py_compile` 通过、import 也正常；但某个函数只剩下前半段
  （本仓库 `unwrap_dek` 的解密分支被落到 `looks_encrypted` 末尾成了死代码，
  表现为"包裹后解不开、固定返回 None"）
- 正确做法:
  1. 追加代码前先确认**当前**行数（`(Get-Content 文件).Count`），`insert_line = 行数 + 1`
  2. 或者用 `old_text` 锚点做替换式追加（最稳）
  3. 插入后回读插入点前后的 10 行，确认函数边界完整
- 反例: 只跑 `py_compile` 就认为追加成功（缩进合法的死代码不会报错）
- 首次记录: 2026-10-21

## PIT-007 PowerShell 里直接跑 Python 并把 stderr 重定向，会被包成 `NativeCommandError`
- 触发条件: 在 PowerShell 里 `python xxx.py 2>&1 | ...` 或 `python xxx.py > out.txt 2>&1`
- 错误现象: 终端只显示
  `所在位置 行:1 ... NativeCommandError`，Python 的 traceback 丢失；
  `>` 重定向出来的文件还是 UTF-16LE，读出来是乱码/带 `\0`
- 正确做法: 用 cmd 包一层 + 显式 UTF-8：
  ```
  cmd /c "set PYTHONIOENCODING=utf-8&& .venv\Scripts\python.exe tmp\test.py > tmp\out.txt 2>&1"
  ```
  然后优先用 Read 工具读 `tmp\out.txt`
- 反例: 直接 `python x.py 2>&1 | Tee-Object`（stderr 一出现就被 PowerShell 当错误，输出被截断）
- 首次记录: 2026-10-21

## PIT-008 只装 `qt_zh_CN.qm` 还不够：QMessageBox 标准按钮仍是 `&Yes / &No / OK / Cancel`
- 触发条件: 已 `app.installTranslator(QTranslator().load('qt_zh_CN'))`，
  但对话框用的是 Qt **标准按钮**（`QMessageBox.Yes / No / Ok / Cancel`，含静态 `question()`）
- 错误现象: 按钮文本仍为英文；而 `QCoreApplication.translate('QDialogButtonBox', '&Yes')`
  已经能返回「是(&Y)」，`translate('QPlatformTheme', 'OK')` 却仍返回 `OK`
- 根因: Windows 平台主题取标准按钮文案走的是 `QPlatformTheme` 上下文，
  `qt_zh_CN.qm` 里没有这些条目（QDialogButtonBox 的条目只在非平台主题路径生效）
- 正确做法: 继承 `QTranslator` 覆盖 `translate()`，只对
  `QPlatformTheme` / `QDialogButtonBox` 两个 context 返回中文映射，其它 context 返回 **空串**
  （空串表示"不翻译"，Qt 会继续问下一个已安装的翻译）。实现见
  `Player.py::_StandardButtonTranslator` + `_install_chinese_translator()`
- 反例: 以为装了 qt_zh_CN.qm 就万事大吉；或给每个对话框手写 `addButton('是', ...)`
  （静态 `QMessageBox.question()` 改不了按钮，只能逐个替换，工作量大）
- 变更（2026-10-22）: 项目已不再使用 QMessageBox（弹框统一走 `src/layout/styled_dialogs.py`，见 `ADR-016`），
  但这段兜底翻译继续保留 —— 嵌入的 `QFileDialog` 内部字符串（新建文件夹 / 后退 / 详细列表等）
  仍由 Qt 自己的翻译 + 这个兜底负责。
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-22

## PIT-009 用 `run_commands` 内联执行复杂 PowerShell（`foreach` + `$` 变量）时变量名会被吞掉
- 触发条件: 直接让工具执行
  `powershell -NoProfile -Command "foreach($f in @('a','b')){ $b=[IO.File]::ReadAllBytes($f)[0..2]; ... }"`
- 错误现象: 命令里的 `$f` / `$b` 全部消失，PowerShell 报
  `Missing variable name after foreach` / `Unexpected token ')'`；
  而同样带 `$_` 的简单管道（`Get-ChildItem ... | %{ $_.Name }`）却正常，极易误判成语法写错
- 正确做法: 稍复杂的逻辑一律写成脚本文件放在 `tmp\` 再执行：
  ```
  cmd /c "set PYTHONIOENCODING=utf-8&& .venv\Scripts\python.exe tmp\probe.py > tmp\probe.txt 2>&1"
  ```
  单行查询改用 `cmd /c findstr /n /c:"..."`，或拆成多条最简单的 PowerShell 单行
- 反例: 反复调引号/转义想让 `foreach` 内联跑通（耗时且结果不稳定）
- 首次记录: 2026-10-21

## PIT-010 `read_files` 对同一文件再次按行段读取会返回 `[outdated - see the latest file content]`
- 触发条件: 先整篇读某文件（超过 2000 行 / 47k 字符被截断），再用 `start_line/end_line` 读同一文件的其它区间
- 错误现象: 返回内容只有一行 `[outdated - see the latest file content]`，拿不到行段（文件本身没有改动）
- 正确做法: 用 `tmp\dump_lines.py` 之类的小脚本把目标行段写到 `tmp\dump_xxx.txt`，再用 Read 读该 txt；
  或者一开始就按行段分块读、不要先整篇读
- 反例: 以为文件被改动或读工具坏了，转去 `SearchCodebase`（本仓库常超时，更慢）
- 首次记录: 2026-10-21

## PIT-011 offscreen 平台下 Qt 没有任何字体：抓图里按钮文字全是空白
- 触发条件: 用 `QT_QPA_PLATFORM=offscreen` 跑 PyQt5 并 `widget.grab().save(...)` 做视觉验证
- 错误现象: 圆角/半透明背景/布局都正常，但按钮文字（中文和 `✕`）完全不见；
  `QFontDatabase().families()` 返回 `[]`，按钮 `font().family()` 是 `Helvetica`、`pointSizeF()` 是 `-1.0`
- 根因: offscreen 平台插件不加载系统字体库，`QFontDatabase` 为空 ⇒ 画不出任何字形；
  布局尺寸仍按字体度量计算，所以按钮宽度是对的，极易误判成"QSS 把文字藏了/颜色不对"
- 正确做法: 需要看真实文字时用 Windows 平台抓图（本机自动化会话可用）：
  ```
  cmd /c "set PYTHONIOENCODING=utf-8&& set QT_QPA_PLATFORM=windows&& .venv\Scripts\python.exe tmp\preview.py"
  ```
  只验证几何/颜色/显隐逻辑时 offscreen 足够
- 反例: 看到文字空白就反复改 `color` / `padding` / 去掉 `QGraphicsDropShadowEffect`（都不是原因）
- 首次记录: 2026-10-21

## PIT-012 区分「UI 线程卡死(AppHang)」与「真崩溃(Application Error)」，用 faulthandler 定位卡点
- 触发条件: 用户报「点击某处程序崩溃/闪退」，但 `data/log/*.log` 里只有启动日志、没有 traceback
- 错误现象: 误判成段错误或 PyQt 异常，去翻 UI 代码 / 加 try-except，方向全错（本次真凶是历史遗留的 `os.walk`）
- 正确做法:
  1. 先查事件查看器（脚本写进 `tmp\*.ps1`，别在命令里内联 `$` 变量，见 PIT-009）：
     - **Application Hang (Id 1002)** / WER `EventType=AppHangB1` / `UI[3]=Python 未响应`
       ⇒ GUI 线程被阻塞，程序本身没崩；
     - **Application Error (Id 1000)** ⇒ 真崩溃（PyQt5 未捕获异常也会 abort，需要 stderr/控制台输出）。
  2. 定位卡在哪：复现脚本开头 `faulthandler.enable()`，在可疑操作前后加
     `faulthandler.dump_traceback_later(20, exit=True)`，超时会打印所有线程栈：
     ```
     cmd /c "set PYTHONIOENCODING=utf-8&& .venv\Scripts\python.exe tmp\repro.py > tmp\repro.log 2>&1"
     ```
  3. 栈里出现 `<frozen os> ... walk` / `scandir` / `getmtime` ⇒ 同步文件 IO 卡住 GUI 线程；
     出现 `Qt5Widgets` 内部 ⇒ 再查重入/死循环。
- 反例:
  - 把「无响应被系统关掉」当崩溃上报，浪费一轮排查；
  - 只盯着最近改过的 UI 代码找原因（本次的 `QGraphicsDropShadowEffect`/`raise_()` 全是冤枉的）。
- 首次记录: 2026-10-21

## PIT-013 QLineEdit 用 `setText()` 写定长文本会横向滚动，看起来像首/末字符被裁掉
- 触发条件: 固定宽度的 `QLineEdit`（如 `HH:MM:SS` 时间框）用 `setText()` 更新文本
- 错误现象: `text()` 取出来是完整的 `00:00:00`，但界面只显示 `0:00:00` 或 `00:02:0`，边缘像被切掉
- 根因: `QLineEdit.setText()` 会把光标放到末尾，为显示光标会横向滚动内容；
  控件宽度刚够时，开头或结尾的字符就落进不可见区域（与字体/QSS padding 无关，容易被误判）
- 正确做法:
  ```python
  edit.setText(text)
  edit.setCursorPosition(0)     # 光标回开头 → 滚动归零
  ```
  固定宽度还要留足内容宽度：本项目 `00:00:00`（13px 字体）用 120px；
  **初始 `setText()` 之后也要补一次 `setCursorPosition(0)`**（文本没变时 `_set_time_edit` 会提前 return）
- 反例: 只调宽度 / 加 `Qt.AlignCenter` / 改 QSS padding，光标仍在末尾，仍可能被滚动裁切
- 首次记录: 2026-10-22

## PIT-014 QSS 的 `min-height`/`padding` 会把 `setFixedSize()` 的正方形按钮拉成竖条
- 触发条件: `QPushButton` 子类用 `setFixedSize(w, h)` 固定成小正方形，而应用/父窗口 QSS 里有
  `QPushButton { min-height: 22px; padding: 4px 12px; border: 1px solid ... }`
- 错误现象: 控件实际几何变成 `(x, y, w, h+22+8+2)`（本项目 10×10 → 10×32），自绘的 ✕ 变成细长竖条；
  代码里 `setFixedSize` 明明写了正方形，界面却不是
- 正确做法: 给该控件单独清零度量，再固定尺寸（自身样式表优先级高于全局 QSS）：
  ```python
  self.setStyleSheet("QPushButton { padding: 0px; margin: 0px; min-width: 0px; min-height: 0px; border: none; background: transparent; }")
  self.setFixedSize(18, 18)
  ```
  验证要打印几何而不是尺寸提示：
  ```
  print(btn.geometry().getRect())   # 必须是 (x, y, 18, 18)
  ```
- 反例: 只改 `setFixedSize` 的数值（还是竖条）；`setMinimumSize(0, 0)`（style polish 会再次写回）；
  只调 `resize()`（下一次 polish 又变回来）
- 首次记录: 2026-10-22

## PIT-015 嵌入模式 QFileDialog 的 `selectFile()` 在目录模型加载前返回空 ⇒ 自动化测试假失败
- 触发条件: 把 `QFileDialog` 当子控件嵌进自定义外壳后，用脚本 `selectFile(path)` + `selectedFiles()`
  验证"能不能选中文件"
- 错误现象: `selectedFiles()` 返回 `[]`，`accept()` 也不生效（`result()` 仍是 0），
  看起来像"嵌入的 QFileDialog 不能选中文件"；但手工点界面完全正常
- 根因: QFileDialog 内部用 `QFileSystemModel`，目录内容是**异步加载**的；模型还没填好时
  `selectFile()` 解析不到条目，选择/accept 都会落空（与嵌入方式无关）
- 正确做法: 测"用户点打开"这条链路时直接操作文件名输入框 + 回车（等价真实点击）：
  ```python
  from PyQt5.QtWidgets import QLineEdit
  from PyQt5.QtTest import QTest

  edit = [e for e in fd.findChildren(QLineEdit) if e.objectName() == "fileNameEdit"][0]
  edit.setText(target)
  QTest.keyClick(edit, Qt.Key_Return)
  QTest.qWait(200)
  assert fd.selectedFiles()          # 这里一定是完整路径
  ```
  也可以先 `QTest.qWait(500)` 等模型加载，再用视图 model 的 index 选中
- 反例: 看到 `selectFile` 断言失败就去改产品代码（把 QFileDialog 换掉 / 加 hack），
  实际真实点击流程一直是好的
- 首次记录: 2026-10-22

## PIT-016 QScrollArea / QVideoWidget / QPushButton 抢走焦点 ⇒ MainWindow.keyPressEvent 收不到快捷键
- 触发条件: 在 `MainWindow.keyPressEvent` 里处理方向键等快捷键，界面上有媒体控件 / 滚动区 / 按钮
- 错误现象: 播放后点一下画面或控制按钮，快捷键就"失灵"；自动化里 `QTest.keyClick` 也复现：
  `focusWidget=QScrollArea / QVideoWidget / QPushButton` 时 MainWindow 一条按键都收不到
  （实测 `QScrollArea` 即使滚动条隐藏也会消费方向键；按钮则把方向键当焦点导航）
- 根因: 键盘事件只发给当前焦点控件；这些控件处理（或吞掉）方向键后事件不会冒泡到父窗口，
  `MainWindow.keyPressEvent` 根本没有被调用
- 正确做法（本项目 `ADR-017` 的落地方式）:
  1. 媒体显示控件与鼠标专用按钮 `setFocusPolicy(Qt.NoFocus)`；
  2. 播放结束后 `main_window.setFocus()`（不要用 `video_widget.setFocus()` / `qscrollarea.setFocus()`）；
  3. 在 viewport 上装事件过滤器，`QEvent.MouseButtonPress` 时把焦点交还主窗口；
  4. 全屏悬浮面板这类独立顶层窗口，在 `keyPressEvent` 里把 Esc / 方向键转发给主窗口。
- 反例: 只改键位映射不管焦点（快捷键看运气）；用 `QShortcut(Qt.WindowShortcut)` 兜底 ——
  实测目录树获得焦点时也会触发快捷键，破坏树的方向键导航
- 首次记录: 2026-10-22

## PIT-017 PyQt5 没有 `Qt.Key_Keypad1`；重写虚函数里抛异常会让进程静默 abort（无 traceback）
- 触发条件: 在 `keyPressEvent` 等被 Qt 回调的重写方法里出现 Python 异常
  （本次是访问不存在的枚举 `Qt.Key_Keypad1`）
- 错误现象: 程序/脚本直接退出，退出码 `-1073740791`（0xC0000409），日志里**没有** traceback，
  表现为"按了一下某个键就闪退"；而把同一句代码直接 `win.keyPressEvent(ev)` 手动调用，
  立刻能看到 `AttributeError: type object 'Qt' has no attribute 'Key_Keypad1'`
- 根因:
  1. Qt5 的小键盘数字不是 `Qt.Key_KeypadN`，而是 `Key_0..Key_9` + `Qt.KeypadModifier`（Qt3/4 的老写法已移除）；
  2. PyQt5 对虚函数 / 槽里未捕获的异常走 qFatal ⇒ abort，信息不会进 stdout/stderr 日志
- 正确做法:
  ```python
  if Qt.Key_0 <= event.key() <= Qt.Key_9:
      digit = event.key() - Qt.Key_0     # 小键盘数字同样命中（带 KeypadModifier）
  ```
  调试这种"静默崩溃"：把重写方法里的关键逻辑抽成普通函数手动调一次，
  或在方法体里 `try/except` 打日志 —— 真实异常立刻现形
- 反例: 用 `Qt.Key_Keypad1`（不存在）；把静默退出当段错误 / Qt 崩溃去查 C++ 层；
  只靠 `python -m py_compile` 校验（这种错误编译期查不出来）
- 首次记录: 2026-10-22