# memory-bank — 跨会话知识库（Cline 开工必读 / 收工必写）

> 目的：**同一个坑不查第二遍。** 已经定位清楚的问题、踩过的坑、做过的技术决策全部沉淀在这里；
> 配合 `.clinerules` 强制 Cline 每次任务开始读取、任务结束回填，跨会话复用，不再重复扫描老问题。
>
> 建立：2026-10-21　维护：Cline 每次任务自动更新　编码约定：UTF-8（无 BOM）+ CRLF

## 1. 固定文件（不要再加层级/新分类，加条目即可）

| 文件 | 内容 | 什么时候写 |
| --- | --- | --- |
| `README.md` | 本协议 + 「症状 → 条目」快速索引 | 每次新增条目时同步更新索引（§4） |
| `issues-solved.md` | **已排查问题**：症状 → 根因 → 证据 → 修法 → 复发判据（`ISSUE-nnn`） | 一个「卡住/失败/异常现象」被定位清楚之后 |
| `pitfalls.md` | **踩坑记录**：本机环境 / 工具链 / 命令语法陷阱（`PIT-nnn`） | 踩到一次就记，不管问题最终有没有修好 |
| `decisions.md` | **技术决策**（ADR 风格：背景/决策/理由/备选/影响，`ADR-nnn`） | 做了取舍、定了方案，或明确「决定不做」时 |
| `audit-tracker.md` | **审计追踪**：记录每轮对核心文件的安全审查结论 | 每次审查完文件后更新 |

## 2. 开工协议（每个任务都要做，不许跳）

1. **先读本文件**（索引见 §4），再按任务关键词**去库里查**：命中就**直接复用结论**，不要重新排查。
2. 检索词优先级：报错原文 / 退出码 → 文件名·命令（`build.bat`、`push_release.bat`…）→
   症状词（卡死、编译失败、乱码、包缺失）→ 模块名（构建、播放器、GUI、编解码）。
   检索方式：**优先用 Read 工具把 4 个文件整篇读**（体量小、最可靠）；
   `SearchCodebase` 在本仓库可能超时，只当辅助。
3. 任务涉及的文件/现象若已有条目：**先按条目的结论执行**；只有当"当前现场证据"与条目矛盾时，
   才重新排查，并在同一轮内**更新该条目**（写清新证据）。
4. **老问题复发**：先跑条目里的「复发判据」（一条命令定论），确认后**更新原条目**（最近复核 + 新证据），
   **不要新建重复条目**。

## 3. 收工协议（每个任务结束前）

- 本次**定位清楚的问题** → 追加到 `issues-solved.md`；老问题复发 → 更新原条目。
- 本次**踩的坑**（命令语法、编码、工具怪癖、误判、被工具打断） → 追加到 `pitfalls.md`。
- 本次**做的取舍**（选型、方案对比、明确不做的范围） → 追加到 `decisions.md`。
- **没定位清楚的不许写成结论**：可以建条目但 `状态: 未定位`，并写清已知证据与下一步验证方法。
- 更新 §4 索引表（新条目必须能被关键词检索到）。
- 不写 token / 密钥 / 私密凭据。
- 条目里优先写「复发判据」和「反例/易误判」——这两栏才是省时间的地方。

## 4. 症状 → 条目 快速索引

| 现场现象 / 报错 | 去看 |
| --- | --- |
| `build.bat` 报 `'uild' is not recognized` / 中文标题乱码 | `ISSUE-001`（编码与 `chcp 65001`） |
| `rd /s/q` 语法错误 / `The syntax of the command is incorrect` | `ISSUE-001`（`rd` 开关必须空格分隔） |
| `pip install` 好像卡住不动 | `ISSUE-001`（重定向到 `nul` 吞掉了进度输出） |
| `pip` 有新版本提示但不自动更新 | `ISSUE-001`（`pip install --upgrade pip`） |
| `pillow==10.0.1` 安装报 `KeyError: '__version__'` / `Getting requirements to build wheel` 失败 | `ISSUE-003`（Python 3.14 不兼容） |
| PyInstaller 打包报语法错 / 找不到模块 | `PIT-001`（隐藏导入） |
| 批处理 `if/for` 块内变量取旧值 | `PIT-002`（延迟展开） |
| `.bat` 中文乱码 / 首行不生效 | `PIT-003`（编码约定） |
| `python -m py_compile` 无输出但实际有语法错 | `PIT-004`（Python 校验命令） |
| 版本号递增策略 / `bump_version.ps1` | `ADR-006`（每构建 +1 patch，满 100 进位） |
| Python 3.14 依赖升级（numpy/opencv/pyinstaller） | `ADR-007`（numpy>=2.0, opencv>=4.8, pyinstaller>=6.15） |
| 构建日志双写（控制台 + build_full.log） | `ADR-008`（PowerShell 管道 tee，零侵入） |
| 私密模式 / 密钥包 / 与 privi 互通 | `ADR-009`（privi 兼容的密钥与加解密方案） |
| `requirement.txt` 缺 `cryptography` 导致私密模式 import 失败 | `ISSUE-005` |
| apsw 报 `no attribute 'executescript'` / `ExecutionCompleteError` | `PIT-005` |
| 用编辑器「按行插入」追加代码，函数被切成两半且编译通过 | `PIT-006` |
| PowerShell 跑 Python 报 `NativeCommandError` / 输出乱码 | `PIT-007` |
| QMessageBox 按钮还是 `&Yes / &No / OK / Cancel` | `PIT-008`（qt_zh_CN.qm 不够，要兜底 QTranslator） |
| `QMediaPlayer` 报 `ResourceError`、任何本地视频都放不了 | `ISSUE-006`（未定位，明文同样失败 ⇒ 与加密无关） |
| 幻灯片间隔要持久化 / 播放区路径与刷新间隔输入框已移除 | `ADR-010`（设置菜单 → 幻灯片弹框） |
| `run_commands` 内联 PowerShell 的 `$` 变量消失、`foreach` 报语法错 | `PIT-009`（改用 `tmp\` 下的脚本文件） |
| `read_files` 对同一文件的行段读取返回 `[outdated - see the latest file content]` | `PIT-010`（先导出到 `tmp\` 再读） |
| 图片控制栏要悬浮在底部居中 / 玻璃效果 / 关闭与恢复显示 | `ADR-011`（视图菜单 → 显示控制器） |
| offscreen 抓图里按钮文字全空白 | `PIT-011`（offscreen 无字体，改用 windows 平台抓图） |
| 点击左侧树目录后程序无响应/被关闭（像是崩溃） | `ISSUE-007`（GUI 线程同步 `os.walk`）、`ADR-012`（后台扫描线程） |
| 报“崩溃”但日志无 traceback，怎么判断是卡死还是崩溃 | `PIT-012`（事件查看器 AppHang≠Application Error + faulthandler） |
| 目录树展开后收起箭头看不见（与深色背景同色） | `ISSUE-008`（QSS `::branch` 缺 open 图像）、`ADR-013` |
| 视频进度条与剪切滑条要合并 / 时间标签去掉“已播放、总时长”文字 | `ADR-014`（`SeekCutSlider`） |
| 视频控制区按钮被拉得很宽 / 时间输入框显示不全 | `ADR-014` 变更（分组布局）、`PIT-013`（QLineEdit 光标滚动） |
| 全屏悬浮面板 / 图片控制面板的关闭按钮不是正方形 / 变成一根细长竖条 / 两处样式不统一 | `ISSUE-009`（QSS `min-height` 覆盖 `setFixedSize`）、`PIT-014`、`ADR-015` |
| 弹框还是 Windows 默认（浅色）标题栏 / 弹框风格与主窗口不一致 | `ADR-016`（统一 `styled_dialogs`：无边框 + 自绘标题栏） |
| 嵌入 QFileDialog 用 `selectFile()` 测不出选中结果 / accept 无效 | `PIT-015`（QFileSystemModel 异步加载） |
| 方向键快捷键不生效 / 点过画面或控制按钮后快捷键失灵 | `PIT-016`（控件抢焦点）、`ADR-017`（方向键新语义） |
| 图片 / 视频评分（1~5 键）/ 移动或改名后评分丢失 / 状态栏评分显示 | `ADR-018`（内容指纹 + 独立表 `media_rating`） |
| 按某个键后程序静默退出（退出码 -1073740791、日志无 traceback） | `PIT-017`（PyQt5 虚函数异常 abort；`Qt.Key_Keypad1` 不存在） |
| 归集菜单（按评分 / 关键字 / 路径批量拷贝）/ 拷贝重名 / 归集时界面卡死 | `ADR-019`（`CollectDialog` + `CollectThread`） |
| `Player.py` 太长 / 想拆 MainWindow / 新增窗口功能该放哪 | `ADR-020`（入口只做启动控制，窗口拆进 `src/window/`：mixin + theme/i18n/file_tree/menu_bar） |
| 新加的 mixin 里 `keyPressEvent` / `closeEvent` 不生效 | `ADR-020`（mixin 必须排在 `QMainWindow` 之前，否则被基类遮蔽） |
| 幻灯片切视频后仍在后台翻页 / 标题栏残留图片名与幻灯片进度 | `ISSUE-010`（`pause_slideshow` + `refresh_title_bar`） |
| `python -m py_compile src\window\*.py` 报 `[Errno 22] Invalid argument` | `PIT-004`（py_compile 不展开通配符） |
| `cmd /c` 里嵌 `python -c "..."` 报 `"…"后面缺少表达式` / `意外的标记` | `PIT-009`（改写成 `tmp\` 下的脚本文件） |

## 5. 条目模板

### issues-solved 模板
```
## ISSUE-NNN 简短标题（能概括现象的）
- 状态: 已修复 / 已规避 / 未修复 / 未定位
- 症状 / 现场: …
- 复发判据: （一条 5 秒定论的命令）
- 根因: …
- 证据: …
- 修法: …
- 反例 / 易误判: …
- 相关文件: `path/file`
- 首次记录: YYYY-MM-DD ／ 最近复核: YYYY-MM-DD
```

### pitfalls 模板
```
## PIT-NNN 简短标题
- 触发条件: …
- 错误现象: …
- 正确做法: （可直接复制执行的正确命令/代码）
- 反例: …
- 首次记录: YYYY-MM-DD ／ 最近复核: YYYY-MM-DD
```

### decisions 模板
```
## ADR-NNN 标题
- 日期: YYYY-MM-DD | 状态: 已采纳 / 已废弃（被 ADR-xxx 取代） / 待决
- 背景: …
- 决策: …
- 理由: …
- 备选与为何不选: …
- 影响 / 约束: …
```

---

最后更新: 2026-10-23（ADR-020：`Player.py` 拆为「入口只做启动控制 + `src/window/` 主窗口 mixin 化」；ISSUE-010：切视频后幻灯片仍在后台翻页 + 标题栏未跟着切模式；PIT-004 / PIT-009 补复核）