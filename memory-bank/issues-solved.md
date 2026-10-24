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

## ISSUE-005 私密模式依赖 `cryptography`，但 `requirement.txt` 里没有 ⇒ 换机会 import 失败
- 状态: 已修复
- 症状 / 现场: 新增的 `src/private_mode/privi_crypto.py` 直接 `from cryptography.hazmat...`；
  本机 `.venv` 里恰好已装 `cryptography 50.0.2`（pip 显示 "Requirement already satisfied"），
  但 `requirement.txt` 里没有它 —— 换机器或重建虚拟环境后 `import Player` 会 `ModuleNotFoundError`
- 复发判据: `findstr /i cryptography requirement.txt` 无输出，或
  `.venv\Scripts\python.exe -c "import cryptography"` 失败
- 根因: 只在本机验证通过，遗漏了依赖声明（本机恰好预装）
- 证据: `tmp\pip_cryptography.log` 输出
  `Requirement already satisfied: cryptography>=42 in .\.venv\Lib\site-packages (50.0.2)`；
  修改前 `requirement.txt` 仅 10 行且不含 cryptography
- 修法: `requirement.txt` 末尾追加 `cryptography>=42`。
  PyInstaller 自带 `cryptography` 官方 hook，无需额外 `--hidden-import`
- 反例 / 易误判: "本机能跑就不用声明依赖"；把 `cryptography` 误当成 PyQt5 或 apsw 的附带依赖
- 相关文件: `requirement.txt`、`src/private_mode/privi_crypto.py`
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-21

## ISSUE-006 本机自动化会话里 QMediaPlayer 对任何本地视频都 `ResourceError` ⇒ 无法自动验证视频播放
- 状态: 未定位
- 症状 / 现场: `QMediaPlayer.setMedia(本地 mp4)` + `play()` 后，
  `mediaStatus` 从 LoadingMedia(2) 直接跳到 InvalidMedia(8)，`error()==1`(ResourceError)、
  `state==0`、`duration==0`、`errorString()` 为空
- 复发判据: 8 行最小复现（真实事件循环，不用 processEvents 也能复现）：
  ```python
  from PyQt5.QtCore import QUrl, QTimer
  from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
  from PyQt5.QtWidgets import QApplication
  app = QApplication([]); p = QMediaPlayer()
  p.setMedia(QMediaContent(QUrl.fromLocalFile(r'<任意本地 mp4>')))
  p.play(); QTimer.singleShot(4000, app.quit); app.exec_()
  print(p.mediaStatus(), p.error(), p.duration())   # 实测 8 1 0
  ```
- 证据:
  1. 三种容器全部失败：H.264 mp4 / mpeg4 mp4 / mjpeg avi（都 `status=8 error=1`）；
  2. **未加密的明文**与「私密模式解密缓存」表现完全一致 ⇒ 与加解密无关；
  3. `PyQt5/Qt5/plugins/mediaservice/{dsengine.dll,wmfengine.dll}` 存在，
     但 `QT_DEBUG_PLUGINS=1` 没有任何插件加载日志
- 修法: 未定位。不影响本次结论：解密缓存与原始文件字节完全一致，OpenCV 可正常打开并读帧，
  图片路径已实测渲染成功
- 下一步验证:
  ① 在交互式桌面会话（非本自动化会话）直接 `python Player.py` 播放明文 mp4；
  ② 安装 LAVFilters（`解码器/LAVFilters-0.73.1.exe`）后重试；
  ③ 检查 `QT_PLUGIN_PATH` / `QT_QPA_PLATFORM_PLUGIN_PATH` 与 mediaservice 插件依赖；
  ④ 换用 `QVideoWidget` + 显式 `app.exec_()` 的完整 Demo 代码验证
- 反例 / 易误判: 看到"解密后的视频播不了"就怀疑加解密 —— 必须先拿**明文对照组**跑一遍；
  本条目就是靠对照组排除的
- 相关文件: `Player.py`（视频播放链路未改动）、`src/private_mode/private_service.py`
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-21

## ISSUE-007 点击左侧树目录后“程序崩溃”：实际是 GUI 线程被 os.walk 卡死（Windows AppHang）
- 状态: 已修复
- 症状 / 现场: 点击左侧目录树里的目录后程序无响应，约 30~40 秒后被 Windows 关闭（用户感知为“崩溃”）；
  `data/log/file_*.log` 只有启动日志、没有异常栈，最后一条是启动期的“数据库路径”
- 复发判据:
  ① 事件查看器里能看到 python.exe 的 **Application Hang (Id=1002)** + WER `EventType=AppHangB1`
     （不是 Application Error(1000)）；
  ② 带 faulthandler 的复现脚本点一次大目录，20 秒后打印的栈落在
     `src/layout/pic_input_layout.py` 的 `loadData` → `<frozen os> ... walk`（不是 Qt 内部）
- 根因: `PicInputLayout.loadData()` 在 GUI 线程里同步 `os.walk` 目标目录，并对每个文件调 `os.path.getmtime`；
  目录大（实测 `C:\Windows\WinSxS` 20s 扫不完）或文件系统被安全软件/DLP 挂钩时，
  事件循环被长时间占住 ⇒ Windows 判定“未响应”并强制关闭。
  （历史遗留的同步扫描，不是本次 UI 改造引入；只是点到的大目录把问题暴露出来）
- 证据:
  1. WER 报告：`EventType=AppHangB1`、`IsFatal=1`、`UI[3]=Python 未响应`、`UI[5]=关闭程序`；
     日志里没有任何 Python traceback（AppHang ≠ Application Error）；
  2. 复现脚本（`faulthandler.dump_traceback_later(20, exit=True)`）点击 `C:\Windows\WinSxS` 后输出：
     ```
     Timeout (0:00:20)!
     Thread 0x00004110 (most recent call first):
       File "<frozen os>", line 377 in walk
       .../src/layout/pic_input_layout.py, line 105 in loadData
       .../src/layout/pic_input_layout.py, line 53 in set_content_path
       .../Player.py, line 606 in on_tree_clicked
     ```
  3. 改造前点击仓库根（含 `.venv`）同步耗时 2.76s；改造后同一操作 0.042s 返回，扫描在后台继续；
     扫描 `WinSxS` 期间 50ms 心跳定时器 1 秒内触发 16 次 ⇒ 事件循环存活。
- 修法:
  1. 新增 `src/layout/pic_scan_thread.py::PicScanThread`（QThread，信号 `scanned(token, path, files)`），
     扫描全部移到后台线程；用 `os.scandir` 递归（Windows 下 stat 结果缓存，比 walk+getmtime 快），
     逐条目检查 `isInterruptionRequested()`；
  2. `PicInputLayout.loadData()` 改为启动线程（不再阻塞），token 递增丢弃过期结果，
     新请求会中断旧线程；`cancel_scan()` 用于私密模式手工填列表 / 关窗；
  3. 「幻灯片」在列表为空时用 `_pending_slideshow` 记下意图，扫描完成的回调里自动开始播放；
  4. `MainWindow.closeEvent` 里 `cancel_scan(wait_ms=1500)`，避免退出时 QThread 仍在跑。
- 反例 / 易误判:
  - 看到“程序没了 + 日志无异常”就当段错误/闪退 —— 先查事件查看器：AppHang(1002) 是 UI 阻塞，
    Application Error(1000) 才是崩溃；
  - 怀疑 `QGraphicsDropShadowEffect` / 悬浮面板 / `raise_()`（本轮 UI 改造的嫌疑对象），
    实际栈在 `os.walk`；
  - 怀疑 `QDirModel` 展开目录慢（实测 `expand()` 0.000s，慢的是我们自己的递归扫描）。
- 相关文件: `src/layout/pic_input_layout.py`、`src/layout/pic_scan_thread.py`、
  `src/layout/pic_show_layout.py`、`Player.py`
- 相关条目: `PIT-012`（AppHang vs Application Error 判定与 faulthandler 定位）、`ADR-012`
- 变更（2026-10-23）: 扫描实现集中到 `src/layout/media_scan_thread.py`（`MediaScanThread`），
  `pic_scan_thread.py::PicScanThread` 变成其薄子类；视频列表也改走同一套后台扫描（`ADR-021`）。
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-23

## ISSUE-008 目录树展开后"收起箭头"看不见：与深色底同色
- 状态: 已修复
- 症状 / 现场: 左侧目录树里未展开的目录有浅灰 `>` 箭头，点击展开后箭头变成几乎看不见的暗色
  （只有一层比背景略深/略浅的痕迹），用户误以为按钮消失了
- 复发判据: 启动后展开任意目录，抓 `treeView` 截图；展开行的 branch 区域（条目左侧、缩进区内）
  取样只剩背景色 `#1e1e2e`，而同高度未展开行能取到 `#a6adc8` 附近的亮像素
- 根因: `Player.py` 全局样式表里只声明了
  `QTreeView::branch:has-children:closed { border-image: none; }`，
  **open（展开）状态没有任何 image/border-image**。样式表一旦接管 `::branch`，
  没有显式图像的状态就由样式引擎按接近底色的颜色自绘 ⇒ 深色主题下展开箭头与背景同色。
- 证据:
  1. 修复前抓图（`tmp/tree_crop.png`）：未展开行有浅灰 `>`；展开的 `src` 行箭头是暗色、几乎不可辨；
  2. 修复前后像素统计（同一段代码采样 branch 区亮像素，阈值 RGB 均 >110）：
     修复前 open 行 = 0（只有 `#1e1e2e`）；修复后 open 行 = 28、closed 行 = 28，两者一致；
  3. 试验对比：仅去掉 branch 规则仍不可见；给 open 加 `image:` 后立刻正常 ⇒ 与"缺少显式图像"直接相关。
- 修法:
  1. `Player.py` 新增 `_draw_tree_branch_icon()` / `_ensure_tree_branch_icons()`：
     用 `QPainter` 画两个 16×16 浅色 chevron（收起 `>`、展开 `v`，颜色 `#a6adc8`），
     首次启动写到 `data/theme/tree_branch_{closed,open}.png`（已存在则复用，不重复写盘）；
  2. 样式表里 closed / open 两种状态都显式指定
     `image: url("...")`（用 `__TREE_BRANCH_CLOSED__` / `__TREE_BRANCH_OPEN__` 占位符替换）；
  3. `.gitignore` 增加 `data/theme/`（运行时生成的图标不入库）。
- 反例 / 易误判:
  - 以为是"展开后按钮被隐藏/禁用"（实际是颜色问题，箭头仍存在、可点击）；
  - 只删掉 `::branch` 规则指望回退原生绘制（实测展开箭头依旧和背景同色）；
  - 用固定路径的图片资源手工放仓库（换机器/打包后路径失效，且多一份二进制资产）。
- 相关文件: `Player.py`、`.gitignore`
- 变更（2026-10-23）: 实现随重构迁到 `src/window/theme.py`
  （`_draw_tree_branch_icon()` / `ensure_tree_branch_icons()`），QSS 文本逐字符未变，见 `ADR-020`
- 相关条目: `ADR-013`（箭头图标方案的取舍）
- 首次记录: 2026-10-21 ／ 最近复核: 2026-10-21

## ISSUE-009 全屏悬浮控制面板的关闭按钮不是正方形：被全局 QSS 撑成 10×32 竖条
- 状态: 已修复
- 症状 / 现场: 视频全屏后，底部悬浮控制面板右上角的 ✕ 变成一条细长竖条（截图里像一根粉色短线），
  用户反馈"关闭按钮有点丑，不是正方形的"
- 复发判据: `findstr /n /c:"min-height: 0px" src\layout\square_close_button.py` 无输出（控件自身没清零 QSS 度量）
  ⇒ 高度会被抬到 32px；要定论就临时起一个面板实例打印 `btn.geometry().getRect()`，
  出现 `(x, y, w, 32)`（正方形被拉高）即复发，正常是 `(x, y, 18, 18)` / `(x, y, 24, 24)`
- 根因: 关闭按钮是 `QPushButton` 子类，命中 `Player.py` 全局 QSS
  `QPushButton { padding: 4px 12px; min-height: 22px; border: 1px solid #45475a; ... }`。
  `QStyleSheetStyle` 据此把控件的最小高度抬到 `22 + 2*4(padding) + 2*1(border) = 32px`；
  **最小尺寸的优先级高于 `setFixedSize()` 设的 maximum**，于是 10×10 的正方形被纵向拉成 10×32
- 证据:
  1. 修复前临时预览脚本（`tmp/` 下，抓图随 tmp 清理）打印 `close btn: (1067, 3, 10, 32) fixed: 10 32`，
     截图里按钮区就是一根竖条；
  2. 修复后同一脚本打印 `close btn: (1056, 6, 18, 18) fixed: 18 18`，面板抓图里是规整的方形按钮；
  3. 单按钮放大图：常态淡粉方框 + ✕，hover 粉底 + 深色 ✕。
- 修法:
  1. 关闭按钮抽成 `src/layout/square_close_button.py::SquareCloseButton`（两个面板共用），
     `__init__` 里**先**给控件自身设样式表清零度量
     （`padding: 0px; margin: 0px; min-width: 0px; min-height: 0px; border: none; background: transparent;`），
     **再** `setFixedSize(size, size)`；控件自身样式表优先级高于祖先/应用级 QSS
  2. 视觉改成方形：常态画淡粉圆角方框（`rgba(243,139,168,26)` 底 + 1px `rgba(243,139,168,110)` 描边）
     + 粉红 ✕；hover 整块填 `#f38ba8`、✕ 反色 `#1e1e2e`；✕ 用圆头笔，边距 `0.3*边长`
  3. 定位统一走 `_position_close_btn()`：`x = 容器宽 - 按钮宽 - 6`、`y = 6`，并 `raise_()`；
     容器内容区右内边距 12 → 26，给按钮留槽位，控制行不会钻到按钮下面
  4. 图片面板（`PicShowLayout`）同款：`SquareCloseButton(size=24)` 放进操作按钮行末尾，
     删掉原 `#picControlClose` 两条 QSS（文字 ✕ 方案作废）
- 反例 / 易误判:
  - 以为 `setFixedSize()` 一定赢 ⇒ 实际 QSS 的 `min-height` 会把它顶掉（宽度不受影响，所以"只变高"）；
  - 只把尺寸从 10 调成 20：高度仍被抬到 32，还是竖条；
  - 在父容器上写 `#floatingContainer QPushButton {...}`：部分属性仍被全局 `QPushButton` 规则覆盖；
  - 打印 `btn.width()/height()` 而不是 `geometry()`，容易看不到被 style polish 之后的实际高度。
- 相关文件: `src/layout/square_close_button.py`、`src/layout/floating_control_panel.py`、
  `src/layout/pic_show_layout.py`、`Player.py`（全局 QSS）
- 变更（2026-10-23）: 全局 QSS 现位于 `src/window/theme.py::_MAIN_WINDOW_STYLE`（内容未变），
  见 `ADR-020`
- 相关条目: `PIT-014`、`ADR-015`
- 首次记录: 2026-10-22 ／ 最近复核: 2026-10-23

## ISSUE-010 幻灯片播放中切到视频模式后，幻灯片仍在后台翻页（标题栏 / 状态栏评分被图片覆盖）
- 状态: 已修复
- 症状 / 现场: 图片幻灯片（▶ 开始）播放中，点左侧树的视频切到视频模式：图片区已隐藏，
  但每隔几秒窗口标题变成某张图片名、状态栏右侧评分变成图片的评分；GIF 还会继续解码。
  用户描述为「幻灯片模式然后切换到视频模式后幻灯片还在播放」。
- 复发判据: `findstr /n /c:"pause_slideshow" src\window\view_actions.py` 无输出
  ⇒ 切视频时没停幻灯片；或 offscreen 脚本里 `start_process()` 后调用
  `win.change_show(MainWindow.show_type_video)`，断言 `inputAndExeLayout.timer.isActive()` 必须为 False
- 根因: 幻灯片是 `PicInputLayout.timer`（`QTimer`，`timeout → pic_show_layout.refreshPictures`），
  **与控件是否可见无关**；`MainWindow.change_show()` 只切 `pic_show_qwidget` / `video_show_qwidget`
  的可见性，从不停止该定时器。而 `refreshPictures() → play()` 每次都会
  `_update_title_bar()` + `main_window.refresh_rating_status()`，所以"看不见的图片"仍在改写 UI。
  该问题**重构前就存在**（`change_show` 是逐行原样搬运的，见 `ADR-020`）。
- 证据: offscreen 用例（8 张图 / interval 300ms）：
  1. `start_process()` 后 `timer.isActive() == True`，700ms 内 `pic.path` 变化（翻页正常）；
  2. 对照实验：把 `pause_slideshow` 替换成空实现（还原旧行为）后 `change_show(video)`，
     1.2s 内 `pic.counter` 继续增长、`timer.isActive()` 仍为 True ⇒ 旧 bug 可复现；
  3. 修复后同一操作 `timer.isActive() == False`，1.2s 内 `pic.path` / `counter` 都不变。
- 修法:
  1. `PicShowLayout.pause_slideshow()`（新增）：停 `inputAndExeLayout.timer`、停 GIF 帧定时器
     （**不清空当前画面**），并复位 `_gif_slideshow_active` / `_gif_playing`，可重复调用；
  2. `MainWindow.change_show()` 切到 `show_type_video` 时调用 `self.pic_show_layout.pause_slideshow()`；
  3. 切回图片模式**不自动续播**（保留"用户按 ▶ 才开始"的语义）；空格 `pause()` 的开/关语义不变。
- 反例 / 易误判:
  - 以为控件隐藏后 `QTimer` 会自动停（不会，QTimer 与可见性无关）；
  - 在 `refreshPictures()` 里加 `if not self.isVisible(): return`：会连"用户手动翻页"一起挡掉，
    且 GIF 分支（`_advance_gif_frame`）绕过了这个判断；
  - 用 `_stop_gif()` 停 GIF：它会把 `pictureQLabel` 的 pixmap 清空，
    切回图片模式时会短暂空白（所以 `pause_slideshow` 只停定时器、不清画面）。
- 相关文件: `src/layout/pic_show_layout.py`、`src/layout/video_show_layout.py`、
  `src/layout/custom_title_bar.py`、`src/window/view_actions.py`、`src/layout/pic_input_layout.py`
- 相关条目: `ADR-010`（幻灯片间隔持久化）、`ADR-020`（窗口拆分）、`ISSUE-007`（后台扫描）
- 补充（2026-10-23，同一场景的后续反馈「标题栏没处理」）:
  - 症状: 只停幻灯片还不够 —— 切到视频模式后标题栏仍挂着图片名与幻灯片进度
    （用户截图 `flapper (1/72)`），看起来像"幻灯片还在放"。
  - 根因: 标题栏由各模式的 `_update_title_bar()` 被动写入，`change_show()` 切换模式时**不刷新**标题栏，
    于是停掉定时器后，上一次写入的图片信息就留在了视频模式里。
  - 修法:
    1. `PicShowLayout.refresh_title_bar()` / `VideoShowLayout.refresh_title_bar()`：
       有当前媒体 → 按它自己的文件名 + 列表进度刷新；没有 → `setInfo('', '')`
       （`CustomTitleBar.setInfo` 对空名字回落 `DEFAULT_TITLE = 多媒体播放器`）；
    2. `change_show()` 切到哪个模式就调用哪个 `refresh_title_bar()`。
  - 验证: offscreen 用例 10 项全过 —— 图片模式 `flapper_0 (1/6)`；幻灯片中切视频 → 标题回
    「多媒体播放器」且进度清空；有视频时切视频 → `movie (1/72)`；切回图片 → `flapper_0 (1/6)`；
    视频进度越界只显示文件名；路径为空 → 默认标题。
- 首次记录: 2026-10-23

## ISSUE-011 打开某些图片格式（.dib / .pcx / .pnm / .apng）程序直接闪退：`QImage` 插件嗅探在 C++ 层访问冲突
- 状态: 已规避
- 症状 / 现场: 图片列表里出现 `.dib/.pcx/.pnm/.apng` 等文件时，点开（或幻灯片播到）程序直接退出：
  退出码 `-1073741819`（0xC0000005 访问冲突），日志里**没有** traceback；
  而把同一个文件单独丢给脚本 `QImage(path)` 却完全正常 → 极易判成"偶发崩溃/驱动问题"
- 复发判据: 把一个正常 PNG 改名成 `.apng`（或任意 Qt 不认识的后缀），在真实 `MainWindow` 里
  `win.pic_show_layout.play(path)`；崩溃栈会落在 `src/layout/pic_show_layout.py::_play_static` 的
  `QImage(...)` 那一行。或 `findstr /n "PILLOW_ONLY_SUFFIXES" src\utils\media_types.py`（无输出=未规避）
- 根因: `QImage(path)` 在扩展名没有对应 Qt 图片插件时会**逐个插件嗅探文件头**；
  主窗口起来后 `QIcon` 已经加载了 ico / icns / cur 等图片插件，
  拿"Qt 不认识的数据"喂给这些插件会在其 C++ 代码里越界访问 → 进程崩溃。
  崩溃点会随播放顺序漂移（本次依次在 `.apng` → `.pnm` → `.pcx` 上崩），说明是嗅探机制本身，
  不是某个固定文件坏了。
- 证据:
  1. `probe_seq.py`（真实窗口顺序播放 25 种格式）：
     `a.png` OK → `b.apng` 崩，faulthandler 栈 = `pic_show_layout.py line 209 in _play_static`；
  2. 隔离进程（无窗口）`QImage('b.apng')` 返回 40×30 正常 ⇒ 与插件加载状态强相关；
  3. 把 `.jpe/.jfif/.dib/.pnm/.pcx/.avif/.apng` 改为 Pillow 解码后，同一序列 25 种全部 OK、退出码 0；
  4. 崩溃先后出现在 `.apng`、`.pnm`、`.pcx` 三个不同扩展名上（每次都在改完上一个之后）。
- 修法:
  1. `src/utils/media_types.py` 新增 `PILLOW_ONLY_SUFFIXES`
     = `('.jpe', '.jfif', '.dib', '.pnm', '.pcx', '.avif', '.apng')`
     —— 判据是这些名字不在 `QImageReader.supportedImageFormats()` 里；
  2. `PicShowLayout._play_static()`：命中 `PILLOW_ONLY_SUFFIXES` 时**直接**走 Pillow，不碰 QImage；
     其余扩展名仍先试 QImage，失败再回退 Pillow；
  3. `PicShowLayout._load_image_with_pillow()`：Pillow 解码 → RGBA bytes → `QImage(...).copy()`
     （必须 `.copy()`：QImage 不接管传入的 bytes 缓冲）。
- 反例 / 易误判:
  - 干净脚本里 `QImage(path)` 不崩 ⇒ 误判"格式没问题"（真实窗口里才崩）；
  - 以为是 Pillow / 内存 / 显卡驱动问题，去查 `QPixmap.fromImage`、`pictureQLabel.setPixmap`；
  - 以为 `isNull()` 兜底就够了（崩溃发生在返回 null **之前**，Python 侧根本接不到异常）；
  - 只把问题扩展名从白名单删掉：不会崩了，但用户也看不到这些图（本修法是"改走 Pillow"而非"不支持"）。
- 相关文件: `src/utils/media_types.py`、`src/layout/pic_show_layout.py`
- 相关条目: `ADR-021`（媒体扩展名单点）、`PIT-017`（重写虚函数 / C++ 层静默崩溃的排查手法）、
  `PIT-012`（区分卡死与崩溃）
- 首次记录: 2026-10-23

## ISSUE-012 视频列表播放遇到无法播放的文件不会自动跳过，要手动点「下一个」
- 状态: 已修复
- 症状 / 现场: 列表模式（列表按钮 ▶| / 右键「加载为视频列表」）播到打不开或解不了的文件时，
  画面停住、时间显示 `00:00:00`，不会继续；必须手动点「下一个」或再点列表才继续。
- 复发判据: 造 3 个内容是文本的 `bad1.mp4 / bad2.mp4 / bad3.mp4`，`loadData()` + `run_list()` 后
  20s 内 `_list_reset_mode` 必须变成 `True`（说明自动跳完了）；
  或 `findstr /n /c:"_skip_unplayable" src\layout\video_show_layout.py` 无输出
- 根因: 列表的"下一集"只在 `onTimerOut()` 里 `position == duration` 时推进；
  无法播放的文件 `duration == 0`，而 `onTimerOut()` 第一行就是 `if duration == 0: return`
  ⇒ **永远走不到推进逻辑**。同时 `mediaStatusChanged(InvalidMedia)` 与 `player.error`
  只重置了"待跳转位置"，没有任何"跳下一个"的动作。
- 证据: 端到端用例（真实 QMediaPlayer、三个假视频）：
  修复前停在 bad1 不动；修复后日志依次
  `视频播放失败（error=1）` → `跳过无法播放的视频（媒体无效）` ×3，
  结束状态 `index=2 / total=3 / reset=True`，全程无点击；单文件约 50~60ms。
- 修法:
  1. `__init__` 里连接 `self.player.error`（`QMediaPlayer.error` 是 pyqtSignal）；
  2. `_on_player_error()` 与 `_on_media_status_changed(InvalidMedia)` 统一走 `_skip_unplayable()`；
  3. `_skip_unplayable()` **只在列表模式生效**：`QTimer.singleShot(0)` 里先 `play_list_index += 1`
     再 `play()`；已经是最后一个则按"列表播放完毕"收尾（`_list_reset_mode=True`、
     tooltip 改「重播列表」、停止定时器）；
  4. `_skipping_unplayable` 防重入：同一次失败会先后收到 `error` 和 `InvalidMedia`，不加锁会一次跳两个。
- 反例 / 易误判:
  - 以为 `EndOfMedia` 会兜底 —— 坏文件 duration 是 0，`onTimerOut` 第一行就 return；
  - 在 `mediaStatusChanged` / `error` 回调里直接 `setMedia()`：播放器状态切换中重入，会丢信号或卡住；
  - 跳过后不检查是否到末尾 → 越界；或反复重试同一个坏文件 → 死循环；
  - 单片模式也自动跳：会把用户明确点开的文件跳过，体验更差（本修法只在列表模式跳）。
- 相关文件: `src/layout/video_show_layout.py`
- 相关条目: `ISSUE-013`（列表里混进大量不可播的 `.ts`，放大了这个现象）、`ISSUE-006`（本机 QMediaPlayer 报 ResourceError）
- 首次记录: 2026-10-24

## ISSUE-013 `.ts` / `.mts` / `.m2ts` 与 TypeScript 后缀冲突：扫用户目录列出 8000+ 个"视频"
- 状态: 已修复
- 症状 / 现场: 右键把 `C:\Users\<用户>` 加载为视频列表后显示「视频扫描完成 … 共 8108 个」，
  绝大多数是 `.vscode\extensions\...\*.ts`（TypeScript 源码），点哪个都播不了。
- 复发判据: 建一个内容为 `import x from "y"` 的 `a.ts`，`collect_media_files(dir, VIDEO_SUFFIXES)`
  的返回值里出现它；或 `findstr /n /c:"_looks_like_mpeg_ts" src\utils\media_scan.py` 无输出
- 根因: 扩展名清单里 `.ts / .mts / .m2ts` 既是 MPEG-TS / AVCHD 容器，又和 TypeScript 源文件同名
  （TS 5 新增 `.mts`），纯按后缀匹配无法区分。
- 证据: 用户日志「视频扫描完成: C:/Users/766698 共 8108 个」+ 目录树里 `.vscode/extensions/...`；
  按内容抽查，这些 `.ts` 都是文本（首字节不是 0x47）。
- 复核（2026-10-24）: 用用户给的真实文件
  `C:\Users\766698\.vscode\extensions\slujbadrujby.column-mode-toggle-0.0.2\src\extension.ts` 实测：
  616 字节，前 8 字节 `69 6d 70 6f 72 74 20 2a`（`import *`），
  `_looks_like_mpeg_ts() == False`，`collect_media_files(该目录, VIDEO_SUFFIXES) == []`，
  整个扩展根目录扫描结果也是 0 个 ⇒ 修复后不会再被当成视频。
- 修法: `src/utils/media_scan.py::_looks_like_mpeg_ts()` —— 命中 `.ts/.mts/.m2ts` 时读前 377 字节，
  校验 MPEG-TS 同步字节（标准 TS：偏移 0 与 188 都是 `0x47`；M2TS：偏移 4 与 196 是 `0x47`），
  不匹配就不算媒体文件。校验只在**扫描阶段**做，`is_video()` 仍按后缀判断（用户仍可手动点开试）。
- 反例 / 易误判:
  - **资源管理器里 `.ts` 显示成播放图标**是 Windows 文件关联（系统把 `.ts` 关联给了某个播放器），
    与本程序的判定无关 —— 别拿图标当"程序识别错了"的证据；
  - 直接在**旧构建 / 旧进程**里复测：修复只在源码里，需要重启（源码运行）或重新构建才生效；
  - 直接把 `.ts` 从清单里删掉：真正的 MPEG-TS 录像（电视录制 / 蓝光）再也列不出来；
  - 只看首字节 `0x47`：TypeScript 文本里也可能出现该字节，必须看 188 / 196 的第二个同步字节；
  - 用"文件大小"过滤：TypeScript 也可能很大，判不准。
- 相关文件: `src/utils/media_scan.py`
- 相关条目: `ADR-021`（视频扩展名扩到 24 种时引入）、`ISSUE-012`（同一次反馈里暴露）
- 首次记录: 2026-10-24

## ISSUE-014 扫 `C:/Users` 一个视频都扫不到（AppData 下明明有 mp4）：junction 用 realpath 去重，把真实目录"顶掉"了
- 状态: 已修复
- 症状 / 现场: 右键把 `C:/Users` 加载为视频列表 → 日志 `视频扫描完成: C:/Users 共 0 个`；
  可是 `C:\Users\766698\AppData\Local\KuashengV2\pro\ks_766698\video\*.mp4` 明明存在（资源管理器能播）。
  直接扫那一层 0.9s 就能找到 4 个视频。
- 复发判据: `collect_media_files(r'C:/Users', VIDEO_SUFFIXES)` 的结果里**没有任何 `\AppData\` 路径**
  （或对"junction 路径不可读"的模拟环境返回 0）；用后台脚本跑一次，正常应 ≥ 4 个、且命中目标文件。
- 根因: `ADR-023` 为了"跟随 junction 但不重复/不死循环"，用 `realpath` 当去重键，但**入队的是链接路径**。
  Windows 用户目录里有一批老式 junction：`Local Settings` → `AppData\Local`、`Application Data` → `AppData\Roaming`、
  `Cookies` / `Recent` / `SendTo` / `Templates` / `「开始」菜单` … 这些链接**本身 ACL 拒绝访问**。
  于是：扫 `C:\Users\<u>` 时先把这些链接的真实路径（如 `appdata\local`）记进了去重键，
  随后真正扫到 `AppData\Local` 时被判为"重复"直接跳过；而去扫那些链接路径又会 `拒绝访问` ⇒
  **整个 AppData 一棵都没扫**。同时 `All Users`（→ `C:\ProgramData`）让扫描在 ProgramData/WER 里空转。
- 证据:
  1. 后台实跑 `collect_media_files(r'C:/Users', VIDEO_SUFFIXES, max_workers=8)` → `count = 0`，耗时 **97.2s**；
  2. 直接扫 `...\AppData\Local\KuashengV2` → 0.93s 找到 4 个（含目标 `b0c87a316d30d70e7630b0cf90006dc1.mp4`）；
  3. 单测复现：造 `tree/AppData/Local/media/a.mp4` + junction `tree/Local Settings → tree/AppData/Local`，
     让 `scandir(junction)` 抛 `PermissionError`：修复前结果 `[]`，修复后返回真实目录里的 `a.mp4`。
- 修法: `media_scan._scan_one_dir()` 对 junction / 目录软链**改用 `os.path.realpath()` 作为入队路径**
  （去重键也用这个真实路径），不再去扫那个可能不可读的链接路径。这样：
  - 不可读的 `Local Settings` 会变成"扫 `AppData\Local`"，文件照样能扫到；
  - 真实目录后到也不会重复（键相同）；
  - 指向树外的 junction 仍然会被跟随（不漏扫）。
- 反例 / 易误判:
  - 以为"拒绝访问的目录跳过就行" —— 跳过的其实是链接，真实目录因为去重键被占而永远不会再扫；
  - 以为 realpath 去重只是"防环" —— 它还会和**真实目录自己**抢去重键；
  - 用 `os.walk` 复测：`os.walk` 不跟随 junction，结果当然也不含 AppData（会误判成"本来就没有视频"）；
  - 只看"扫了 97s 没报错"就当扫完了 —— 要检查结果里有没有 `\AppData\` 路径。
- 相关文件: `src/utils/media_scan.py`
- 相关条目: `ADR-023`（任务队列调度，去重键设计）、`ADR-021`、`ISSUE-013`
- 首次记录: 2026-10-24

