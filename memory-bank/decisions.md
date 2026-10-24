# 技术决策（decisions / ADR）

> 记录**取舍**：为什么这么定、放弃了什么、后续改动要注意什么。模板见 `README.md` §5。
> 状态只有三种：`已采纳` / `已废弃（被 ADR-xxx 取代）` / `待决`。

## ADR-001 构建脚本统一放 `scripts\`
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 原先 `build.bat`、`build_mac.sh`、`start.sh` 散落在仓库根，与源码文件和 `Player.py` 混在一起
- 决策: 全部迁移进 `scripts\`，`build.bat` 内用 `%~dp0..` 计算 `PROJECT_ROOT`
- 理由: 根目录只保留入口文件和工程配置；脚本集中便于维护
- 备选与为何不选: `tools\`（与外部工具混淆）；`build\`（会被构建清理删掉）
- 影响 / 约束: 新增脚本必须放 `scripts\`；所有路径引用以 `PROJECT_ROOT` 为基准

## ADR-002 双包构建：onedir（目录版）+ onefile（单文件版） + zip 归档
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 用户需要两种发布形态：方便调试的目录版和便于分发的单文件版
- 决策:
  1. `build.bat onedir` → `pyinstaller --onedir` → 输出到 `dist\`
  2. `build.bat onefile` → `pyinstaller --onefile` → 输出到 `dist\`
  3. `build.bat zip` → 把 `dist\onedir` 目录打包为 zip
  4. `push_release.bat` → 读取 `VERSION`，用 `gh` CLI 推送 Release
- 理由: onefile 启动慢但分发方便；onedir 启动快适合本地频繁运行；zip 用于额外压缩归档
- 备选与为何不选: 只用 onefile（启动慢，调试不便）；只用 onedir（不分发方便）
- 影响 / 约束: 两个包体积差异大，注意 `dist\` 目录结构

## ADR-003 版本号单源：`VERSION` 文件
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 需要版本号统一管理，方便构建脚本和 Release 推送引用
- 决策: 仓库根放 `VERSION` 文件，一行写语义化版本号（如 `1.0.0`）；
  `build.bat` 和 `push_release.bat` 都从这里读取
- 理由: 单文件单源，比嵌入代码或环境变量可靠；git 可追踪版本变更
- 备选与为何不选: 嵌入 `Player.py`（每次构建都要解析源码）；写 `setup.py`（这个项目不是 pip 包）
- 影响 / 约束: 发版前更新 `VERSION` 并提交

## ADR-004 用 `gh` CLI 做 GitHub Release 推送
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 需要自动推送构建产物到 GitHub Releases，且不想管理 API token
- 决策: 用已安装的 `gh` CLI，通过 `gh release create` / `gh release upload` 发布；
  推送失败不阻塞构建（视为独立步骤）
- 理由: `gh` CLI 免去 token 管理；失败不影响已生成的构建产物
- 备选与为何不选: 直接调 GitHub API（要管理 token）；用第三方 action（本机构建不需要 CI）
- 影响 / 约束: 构建机器需要提前 `gh auth login` 登录；不在 `main` 分支时不推送

## ADR-005 知识库制度：`memory-bank/` + `.clinerules` 强制「开工先读、收工必写」
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 参考 privi 项目的成熟知识库体系，避免同一批问题被反复排查
- 决策: 建立 `memory-bank/`（`README.md` 协议与索引 + `issues-solved.md` + `pitfalls.md` + `decisions.md` + `audit-tracker.md`），
  在 `.clinerules/` 里强制"任务开始先查库、结束必须回填"，条目统一模板、编号递增、永不删旧条目
- 理由: 结论与「复发判据」沉淀成可检索的短条目，比重新排查快一个数量级
- 备选与为何不选: 不建知识库（同一问题反复排查）；只靠 `.clinerules`（塞不下历史结论）
- 影响 / 约束: **任何任务结束都要更新 memory-bank**；不写 token/密钥

## ADR-006 版本号递增策略：每构建自动 +1 patch，满 100 进位
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 项目需要自动化版本管理，避免手动改版本号的遗漏和不一致；参考 privi 项目的 `bump_version.ps1` 方案
- 决策:
  1. 版本号遵循三段式语义化：`MAJOR.MINOR.PATCH`（如 `1.0.0`）
  2. 每次构建自动将 PATCH +1；PATCH ≥ 100 时清零并进位 MINOR +1；MINOR ≥ 100 时清零并进位 MAJOR +1
  3. 实现为一个独立的 PowerShell 脚本 `scripts/tools/bump_version.ps1`，用 `-File` 方式调用（避免 `-Command` 被安全策略拦截）
  4. `build.bat` 在构建开始前调用 bump，并做**回读校验**（版本号必须真的变了）
  5. 支持 `nobump` 参数跳过递增
- 理由:
  - 自动化避免手动忘记改版本号
  - 满 100 进位而非满 1000，保持版本号简洁（99 次小迭代足以覆盖大部分场景）
  - 独立脚本 `-File` 调用解决了 PowerShell `-Command` 被企业安全策略拦截的已知坑
  - 回读校验防止"脚本退出了但文件没变"的静默失败
- 备选与为何不选:
  - 手动改版本号（容易忘，构建产物版本号不一致）
  - 构建后 bump（万一构建失败，版本号已经 +1 了比实际发布少一版）
  - 语义化 MAJOR.MINOR.PATCH 手动决定（对个人项目粒度太细，自动化 PATCH 递增更实用）
- 影响 / 约束: 每次构建 VERSION 文件都会变，构建完成需提交 VERSION 的变更；
  构建脚本依赖 `scripts/tools/bump_version.ps1` 存在

## ADR-007 Python 3.14 依赖兼容性适配
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 本机 Python 已是 3.14.7，原 `requirement.txt` 中多个包无 3.14 wheel，构建在 `pip install` 阶段崩溃
- 决策:
  1. `numpy<2.0` → `numpy>=2.0,<3.0`（numpy 1.x 全系无 Python 3.14 wheel，连源码编译都极慢）
  2. `opencv-python==4.7.0.72` → `opencv-python>=4.8.0`（4.7 无 numpy 2.x ABI 兼容，运行时会崩）
  3. `pyinstaller==6.10.0` → `pyinstaller>=6.15.0`（6.10 不支持 Python 3.14，6.15 是门槛版本）
  4. Pillow 已在之前升级至 `>=10.4.0`
  5. `pyinstaller` 命令改用 `python -m PyInstaller`（用户目录安装时 `where pyinstaller` 找不到但 `pip` 能查到，裸命令照样挂）
- 理由:
  - numpy 1.x 在 Python 3.14 上无预编译 wheel，pip 会回退到源码 tar.gz 编译，耗时 5~10 分钟且可能编译失败
  - opencv-python 4.7 的 C 扩展链接 numpy 1.x ABI，与 numpy 2.x 二进制不兼容
  - PyInstaller 从 6.15 开始才正式支持 Python 3.14
- 备选与为何不选:
  - 降级 Python 到 3.12（放弃 3.14 新特性，且本机环境已固定）
  - 用 `--only-binary :all:` 强制只装 wheel（numpy 1.x 直接装不上，不如升级）
- 影响 / 约束: `opencv-python>=4.8.0` 需验证项目中所有 OpenCV API 调用兼容性（API 基本稳定，4.7→4.8 无 breaking change）

## ADR-008 构建日志双写：控制台 + `build\build_full.log`
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 之前 `build.bat` 只输出到控制台，构建失败时无法回溯完整日志排查问题
- 决策:
  1. 采用 privi 项目的 PowerShell 管道日志双写策略
  2. 首轮调用检测 `%~1` 不是 `--log` → PowerShell 管道重新调用 `%~f0 --log %*`
  3. PowerShell 用 `StreamWriter` 写 `build\build_full.log`（UTF-8 无 BOM，AutoFlush=true）
  4. 每个输出行同时 `Write-Host`（控制台）+ `$sw.WriteLine`（文件）
  5. `finally { $sw.Close(); exit $LASTEXITCODE }` 确保日志完整 + 退出码正确传递
- 理由:
  - 零侵入：不需要修改任何 echo/pip/pyinstaller 的输出语句
  - 实时可查：`AutoFlush=true` 保证每行即时落盘，可以边构建边 tail 日志
  - 退出码透传：PowerShell `exit $LASTEXITCODE` 保证构建成败判断不受日志管道影响
  - `2>&1` 合并 stderr → 日志包含所有错误信息
- 备选与为何不选:
  - 在每个 echo 后面追加 `>> build.log`（工作量大、容易遗漏、括号块内写文件困难）
  - `script`/`tee` 命令（Windows 无原生 tee）
  - 自定义 Python 脚本做 tee（引入额外依赖，构建前就要装好）
- 影响 / 约束: `build\build_full.log` 每次构建覆盖（不追加）；日志文件编码 UTF-8 无 BOM

## ADR-009 私密模式密钥与加解密：完全对齐 privi（读 v1+v2、写 v2），密钥包用 privi v2 SQLite
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 用户要求 ① 菜单新增「密钥管理」，能导入 privi 导出的密钥数据库、也能导出同样格式；
  ② 选择私密路径后能用导入的密钥解开路径下的加密文件并正常播放/展示；
  ③ 私密模式左侧树右键可批量加密/解密某路径下的图片与视频（内容 + 文件名，加密后删源文件）；
  ④ 方案必须与 `D:\WorkSpace\test\privi` 兼容。
- 决策:
  1. **算法与容器照抄 privi**（`media_encryption_service.dart` + `CryptoHandler.kt`）：
     AES-256-GCM；DEK 包裹 = `base64(nonce12|ciphertext32|tag16)`；
     文件容器**读 v1 与 v2，写出统一 v2**：
     `[b'PRV2'][baseNonce:8][plaintextSize:8][chunkSize:4] + n×(ciphertext + tag16)`，
     chunk nonce = `baseNonce(8) || int32_be(index)`，chunkSize = 1 MiB。
     （v2 是 privi 为了避开单流 GCM 的内存峰值而引入的；只写 v1 会让 privi 侧大文件解密变慢甚至 OOM）
  2. **密钥包 = privi v2 SQLite**：`meta(key,value)` / `key_material(id=1, salt, kek BLOB, source, created_at)` /
     `media_keys`（14 列，与 privi 一字不差），`PRAGMA user_version = 2`，
     文件名 `privi-key-YYYYMMDD-HHMMSS.db`，`meta.format = 'privi-key-backup'`。
  3. **本机索引放在独立库** `data/private_keys.db`，`media_keys` 额外有 `file_name / local_path / updated_at`
     三列（只在本地用）；导出时只写 privi 的 14 列，`private_path` 优先写 `local_path`。
  4. **跨设备匹配靠文件名**：privi 的 `private_path` 是 Android 路径，拷到 Windows 必然对不上；
     `find_media()` 依次按「绝对路径 → `private_path` → `basename(file_name)`」匹配，命中后回写 `local_path`。
  5. **崩溃安全顺序**：加密 = 先写 DEK 记录 → 写密文临时文件 → 校验长度 → `os.replace` → 删源文件；
     解密 = 解密到临时文件 → 校验非空 → 原子替换成原名 → 删密文 → 删记录。
     （与 privi 的 "先持久化 DEK 再加密" / "最后才清 DEK" 一致）
  6. **加密文件名**：32 位小写 hex、无扩展名（privi ADR-042）。所以播放前必须先解密成带扩展名的明文。
  7. **播放路径**：解密到 `data/private_cache/<md5(源绝对路径)[:12]>/<原文件名>`，
     保留原扩展名 ⇒ 现有 `VideoShowLayout` / `PicShowLayout`（按扩展名判类型）零改动复用；
     启动、退出、批量操作后清空缓存。
  8. **批量操作放 QThread**（`PrivateBatchThread`，线程内自建 `PrivateService` + 独立 sqlite 连接），
     UI 用 `QProgressDialog` 显示进度、支持取消。
  9. **密钥冲突**：本机已有不同 KEK 时默认拒绝导入，用户明确确认后才覆盖（沿用 privi `saltConflict` 语义）。
- 理由:
  - 只有复刻字节级格式，密钥包与密文才能双向交换（用户的核心诉求）；
  - 写出 v2 而不是 v1，是为了让 privi 打开我们加密的大视频时不会因为单流 GCM 吃内存而崩；
  - 独立密钥库不动既有 `player.db` 表结构，避免污染配置/播放位置表；
  - 先落库 DEK 再写密文，任何时刻崩溃都不会产生"有密文没密钥"的死文件；
  - 解密到缓存再复用现有布局，比改两个布局（且 `pic_show_layout.py` 本身是乱码文本）风险小得多。
- 备选与为何不选:
  - 直接复制 privi 的 drift 数据库当密钥包：会带走相册/播放历史等无关数据，且包格式被内部 schema 迁移绑死（privi ADR-047 也明确不这么做）；
  - KEK 只放内存 / 只在导出时生成：重启即丢，无法解释密文；
  - 把 DEK 写进密文文件头：彻底破坏与 privi 的互通；
  - 自造 zip/JSON 容器：privi 读不了；
  - 只支持 v2、不读 v1：老库里的 v1 密文会全部打不开（privi 明确保留 v1 读取）。
- 影响 / 约束:
  - 新增运行时依赖 `cryptography>=42`（PyInstaller 官方 hook，无需 hidden-import）；
  - 密钥包 = 明文 KEK，连同私密目录即可解开全部文件，UI 文案必须保留安全警告；
  - 加密后源文件删除、文件名变随机 hex，只能通过密钥库恢复原名；删除 `data/private_keys.db` 等于丢失解密能力；
  - `data/private_cache/` 里是明文，必须保证启动/退出时清空（`closeEvent` 已处理）；
  - 批量加密/解密只处理图片（`.jpg/.png/...`）与视频（`.mp4/.mkv`），其它类型与已加密文件跳过。
- 相关文件: `src/private_mode/privi_crypto.py`、`key_store.py`、`private_service.py`、
  `private_batch_thread.py`、`Player.py`、`requirement.txt`
- 相关条目: `ISSUE-005`、`PIT-005`、`ADR-007`（Python 3.14 依赖）
- 首次记录: 2026-10-21
- 复核（2026-10-21，真实 PNG + 真实 MP4 端到端）:
  密文直接打开 → `QImage` 为空、OpenCV `VideoCapture` 打不开（**不能直接播放**）；
  私密树点击 → 解密到 `data/private_cache/<hash>/<原名>.<扩展名>`：
  缓存文件与原始文件**字节完全一致**，图片已实际渲染出图，视频 OpenCV 可打开并读帧。
  `QMediaPlayer` 在本机自动化会话里连明文 mp4 都 `ResourceError`，见 `ISSUE-006`（与加密无关）。

## ADR-010 幻灯片设置收进「设置」菜单：间隔持久化到 config，播放区只留操作按钮
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 图片播放区顶部的「文件路径 + 输入框」「图片刷新时间间隔 + 输入框」占满一整行；
  实际上路径几乎总是从左侧树选（点击目录 / 右键「加载为幻灯片列表」），输入框极少用到；
  用户要求把这两项配置从播放区挪走，改为菜单里的弹框设置。
- 决策:
  1. 菜单栏新增「设置(&S)」→「幻灯片...」，点击弹出 `QDialog`
     （`QFormLayout` + `QSpinBox`(1~3600，后缀「 秒」) + `QDialogButtonBox(Ok|Cancel)`），
     确定后立即 `QTimer.setInterval` 并写 config；取消不改任何状态。
  2. 间隔配置键 `pic.show.slideshow.interval`（config 表，存整数秒，默认 5）；
     `PicInputLayout.get_interval_seconds()` 负责读取 + 夹取范围 + 非法值回落默认。
  3. 删除播放区的 `inputPathTitle` / `inputPath` / `inputIntervalPathTitle` / `inputInterval`，
     以及只服务输入框的 `text_edited` / `input_interval_text_edited` / `is_number`；
     `getPathBtn` 文案改为「选择目录」，点击总是弹目录框（`choose_pic_list()`）。
  4. 图片目录统一走 `PicInputLayout.set_content_path(path)`（左树点击 / 右键加载 / 私密模式），
     内部负责 `config.add_or_update('pic.show.list')` + 重新扫描。
  5. `PicShowLayout.start_process()` 在列表为空时先 `load_pic_list()`（无目录则弹目录框），
     并把 `counter` 越界修正为 0，避免「点幻灯片没反应」。
- 理由: 路径与间隔属于「配置」，不是每次播放都要看的操作项；收进菜单后播放区只剩 4 个动作按钮；
  间隔落到 config 后重启自动沿用，不需每次手输。
- 备选与为何不选:
  - 保留输入框只加菜单入口（重复入口，两处状态要同步，容易出现「改了没生效」）；
  - `QInputDialog.getInt` 代替自定义 `QDialog`（无法同时显示单位/范围提示，也不便于后续扩展设置项）；
  - 间隔存 QSettings（项目已有 config 表，统一进 `player.db` 更好备份）。
- 影响 / 约束:
  - 该间隔只影响 `PicInputLayout.timer`（幻灯片切图）；GIF 自身帧间隔与视频播放不受影响；
  - 目录不再显示在播放区（文件名/进度仍由标题栏显示），只能在左侧树看到当前目录；
  - 首次点「幻灯片」且没有记住目录时会弹出目录选择框，属预期行为。
- 相关文件: `Player.py`、`src/layout/pic_input_layout.py`、`src/layout/pic_show_layout.py`
- 首次记录: 2026-10-21
- 变更（2026-10-21，复核）: 按用户要求移除播放区的「选择目录」按钮（`getPathBtn`），
  图片目录只由左侧树选择；`choose_pic_list()` 保留为兜底（点「幻灯片」且无可用目录时弹目录框）。
  本节决策第 3 条中「`getPathBtn` 文案改为『选择目录』」已作废。
- 变更（2026-10-21，第二次复核）: 目录扫描改为后台线程（见 ADR-012）；
  `start_process()` 在列表为空时不再同步扫描，扫描完成后自动开始播放；
  `load_pic_list()` / `choose_pic_list()` 增加 `start_slideshow` 参数。

## ADR-011 图片控制栏改为「悬浮在图片区底部居中」的暗黑玻璃面板 + 「控制」菜单恢复显示
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: 图片控制按钮原来占用播放区顶部一整行（`PicInputLayout`），挤占图片显示高度；
  用户要求把控制按钮下沉到图片区底部居中、悬浮在图片之上，做成暗黑透明玻璃效果，
  并提供关闭按钮 + 菜单入口恢复，避免关掉后找不回来。
- 决策:
  1. `PicShowLayout.__init__` 不再 `addWidget(inputQWidget)`（顶部整行消失）；
     在 `qscrollarea` 建好后 `setParent(self.qscrollarea.viewport())`，
     面板成为图片区的子控件：随图片区整体显隐、天然盖在图片之上。
  2. 面板 = `QWidget#picControlPanel`：`WA_StyledBackground` + QSS
     竖向渐变半透明底（`rgba(58,58,80,150) → rgba(22,22,34,158)`）、1px 浅描边、14px 圆角，
     再加 `QGraphicsDropShadowEffect`（blur 26 / offset 0,4 / `rgba(0,0,0,150)`）模拟玻璃厚度。
     **Qt5 没有跨平台高斯模糊，不做真实毛玻璃**，只用半透明叠色 + 描边 + 投影近似。
  3. 保留原有 4 个按钮（选择目录 / 幻灯片 / 幻灯片并全屏 / 全屏），末尾追加圆形 `✕`
     （24×24，hover 变粉红）→ `hide_control_panel()`。
  4. 定位集中在 `_position_control_panel()`：`x=(viewport宽-面板宽)//2`、
     `y=viewport高-面板高-24`、`raise_()`；在 `eventFilter` 的 `QEvent.Resize`
     （主窗口与 viewport 都监听）和 `setVisible()` 里重新定位，
     窗口缩放 / 全屏切换后都保持底部居中。
  5. 显隐用 `controlPanelVisibilityChanged = pyqtSignal(bool)` 广播：
     `MainWindow._setup_menu_bar` 在「视图(&V)」菜单下加可勾选「显示控制器」，
     勾选调 `show_control_panel()`、取消调 `hide_control_panel()`；
     点 ✕ 时信号把菜单勾选同步为未勾选。
  6. 全屏不再隐藏控制栏（删掉原 `setVisible` 里的 `inputQWidget.setVisible(visible)`）；
     用户手动隐藏后，进出全屏也不会自动弹出（尊重用户选择）。
- 理由: 底部居中的悬浮控制条是播放器通行布局，不占图片显示面积；
  半透明 + 描边 + 圆角 + 投影在深色主题下既看得清又不抢画面；
  菜单入口是"关掉还能找回"的必要兜底。
- 备选与为何不选:
  - 继续放顶部（占高度，且离图片内容远）；
  - 用 `Qt.Tool` 顶层窗口（视频全屏的 `FloatingControlPanel` 那种做法）：
    图片区非全屏时会有窗口层级/焦点/跟随移动问题，作为 viewport 子控件更稳；
  - `QGraphicsBlurEffect` 做真毛玻璃：对实时刷新的图片区开销大，且 Qt5 会连控件树一起模糊。
- 影响 / 约束:
  - 控制栏只在图片区域内浮动，不会盖住左侧树/状态栏；父控件隐藏时自动跟着隐藏；
  - 面板宽度由按钮文案决定（当前约 360px），窗口过窄时 x 夹到 0，不会跑出边界；
  - `PicShowLayout.setVisible(True)` 不再把 `titleQLabel` 显示出来
    （该标签设计上一直隐藏、路径由窗口标题栏显示），顺带修掉"退出全屏后标题标签冒出来"的旧现象；
  - 键盘快捷键（Space/←/→/Delete/F 等）不受影响，仍然由 `MainWindow.keyPressEvent` 处理。
- 相关文件: `src/layout/pic_show_layout.py`、`Player.py`
- 首次记录: 2026-10-21
- 变更（2026-10-21，复核）: 面板按钮由 4 个减为 3 个（幻灯片 / 幻灯片并全屏 / 全屏）+ `✕`，
  不再包含「选择目录」；面板宽度随之约 360px → 278px，底部居中与显隐逻辑不变。
- 变更（2026-10-21，第三次复核）: `✕` 不再和操作按钮并排 —— 面板改成两行结构
  （第一行只有右上角 18×18 的圆形 ✕ 徽标，第二行才是三个操作按钮），
  面板尺寸变为约 244×52；显隐信号与菜单联动不变。
- 变更（2026-10-21，第四次复核）: 全屏时连同**菜单栏**一起隐藏
  （`full_screen_custom()` → `menu_bar.setVisible(False)`，`screen_normal()` 恢复），
  标题栏/状态栏原有做法不变，控制栏仍保留（见决策第 6 条）。
  注意：全屏中若用 ✕ 关掉控制栏，需先 Esc / F 退出全屏，再用「视图 → 显示控制器」恢复。
- 变更（2026-10-21，第五次复核）: 按用户意见把 `✕` 改回**与操作按钮同一行**（排在「全屏」右侧），
  恢复单行面板结构：`inputQWidget` 直接承载 `PicInputLayout`，尺寸约 278×36；
  两行/右上角徽标的方案作废。
- 变更（2026-10-22）: 「显示控制器」从「控制(&C)」菜单迁移到「视图(&V)」菜单，
  独立的「控制」菜单随之移除；入口位置变化，显隐逻辑与信号联动不变。

## ADR-012 图片目录扫描放后台线程（QThread + token + 延迟播放意图）
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: ISSUE-007 定位到"点目录就崩溃"的真因是 GUI 线程同步 `os.walk`；
  目录越大 / 文件系统越慢，卡得越久，用户看到的是"点了就没了"。
- 决策:
  1. 扫描逻辑独立到 `PicScanThread(QThread)`，信号 `scanned(token, path, files)`；
  2. 用 `os.scandir` 递归代替 `os.walk + getmtime`，按 `st_mtime` **升序**排序（保持原有"最旧优先"顺序）；
  3. `PicInputLayout` 维护 `_scan_token` / `_running_scans` / `_pending_slideshow`：
     新请求让 token+1 并中断旧线程；回调只接受 token 匹配的结果（连续点目录不会串号）；
  4. 「幻灯片」在列表为空时不再阻塞等待：置 `_pending_slideshow=True` 并请求扫描，
     扫描完成回调里自动 `start_process()`；用户取消目录选择则清空该意图；
  5. 私密模式手工填 `list_files` 前先 `cancel_scan()`；`MainWindow.closeEvent` 里
     `cancel_scan(wait_ms=1500)` 保证线程退出。
- 理由: GUI 线程绝不做递归文件 IO；token 机制让"连续点目录"天然取最后一次；
  延迟播放意图让用户只点一次按钮就能在扫描结束后自动开始。
- 备选与为何不选:
  - 同步扫描 + `QApplication.processEvents()` 刷新：大目录照样假死，且 processEvents 期间
    可能重入点击（同一目录被扫多次）；
  - 只把 `os.walk` 优化成 `os.scandir`、不线程化：仓库根 2.7s → 约 1s，仍会卡；网络盘/安全软件挂钩无解；
  - `QFileSystemWatcher` 增量索引：改动面大、跨平台行为不一致，当前需求不需要。
- 影响 / 约束:
  - 点目录后 `list_files` **不是立即就绪**（正常目录 10~50ms，大目录更久）；
    任何"点完目录立刻读 list_files"的代码都要考虑异步（目前只有 `start_process`，已用 pending 处理）；
  - 只接受最新一次请求的结果，被中断的线程不发包；
  - QThread 实例必须保活（`_running_scans` 集合 + `finished` 里 discard + `deleteLater`），
    否则会出现 "QThread: Destroyed while thread is still running"。
- 相关文件: `src/layout/pic_scan_thread.py`、`src/layout/pic_input_layout.py`、
  `src/layout/pic_show_layout.py`、`Player.py`
- 相关条目: `ISSUE-007`、`PIT-012`
- 变更（2026-10-23）: 扫描实现上移成 `src/layout/media_scan_thread.py`（`MediaScanThread` +
  `collect_media_files`），`PicScanThread` 变成它的薄子类；视频列表也改走同一套（见 `ADR-021`）。
  递归 / token / 取消 / `mtime` 升序的约定都保持不变。
- 变更（2026-10-23，之后）：扫描实现再迁到 **不依赖 Qt** 的 `src/utils/media_scan.py`，
  并改为「按目录层级 BFS + `ThreadPoolExecutor`」的**多线程**扫描（见 `ADR-022`）；
  `MediaScanThread` / `PicScanThread` 只保留 Qt 信号封装，接口与 token 语义不变。
- 首次记录: 2026-10-21

## ADR-013 目录树展开/收起箭头：运行时生成 PNG + QSS `image:`（不用 QProxyStyle / 仓库内图片资产）
- 日期: 2026-10-21 | 状态: 已采纳
- 背景: ISSUE-008 —— 深色主题下目录树展开后的收起箭头与背景同色、看不见。
  样式表里只声明了 `::branch:has-children:closed`，open 状态没有图像。
- 决策:
  1. 用 `QPainter` 在运行时画两个 16×16 浅色 chevron（`#a6adc8`），
     首次启动写到 `data/theme/tree_branch_{closed,open}.png`，之后直接复用；
  2. QSS 里 closed / open 两种状态都显式 `image: url("...")`，两态视觉一致；
  3. 图标目录 `data/theme/` 加进 `.gitignore`（运行时产物，不入库）。
- 理由: 只改样式表即可生效，不影响 Qt 的绘制流程；图标随程序自动生成，
  不需要在仓库里放二进制资产，也不依赖安装路径（打包后照样写到可写的 data 目录）。
- 备选与为何不选:
  - `QProxyStyle` 重写 `PE_IndicatorBranch`：不产生文件，但 `setStyle` 会替换控件样式，
    与现有 QSS（背景/文字/item 颜色）交互不确定，风险高于收益；
  - 只删掉 `::branch` 规则：实测展开箭头仍与背景同色，无效；
  - 手工把 PNG 放仓库 `img/`：需要维护二进制资产，打包时还要额外处理资源路径。
- 影响 / 约束:
  - 首次启动会向 `data/theme/` 写两个小文件（各 <1KB），之后只读；
  - 图标颜色写死 `#a6adc8`，若以后换主题需要同步改 `_draw_tree_branch_icon()` 的默认色；
  - 高 DPI 下 16×16 图标可能略小，需要时把尺寸提到 20/24 或按 `devicePixelRatio` 重新生成。
- 相关文件: `Player.py`、`.gitignore`
- 相关条目: `ISSUE-008`
- 首次记录: 2026-10-21

## ADR-014 视频「播放进度条」与「剪切范围滑条」合并成一条时间轴（SeekCutSlider）
- 日期: 2026-10-22 | 状态: 已采纳
- 背景: 视频区有两行时间轴 —— 上面 `CustomSlider` 是播放进度，下面 `QRangeSlider` 选剪切范围；
  两者都表示"整段视频的 0~100%"，重复占垂直空间。用户同时要求时间标签去掉"已播放/总时长"文字。
- 决策:
  1. 新增 `src/layout/seek_cut_slider.py::SeekCutSlider(QWidget)` 自绘一条时间轴：
     - 白色圆点 = 播放头，点击/拖动任意位置 → `seekRequested(ms)`；
     - 蓝色双竖条 = 剪切起止，拖动 → `cutRangeChanged(start_ms, end_ms)`，区间用半透明蓝带高亮；
     - 命中优先级：剪切手柄（±8px）> 播放头；其余位置点击一律当"定位播放"；
  2. 时间标签：`bar_label`（左）/ `bar_label_all`（右）只显示 `HH:MM:SS`，去掉"已播放:"/"总时长:"前缀；
  3. 剪切行只保留「开始:」「结束:」按钮 + 两个时间输入框 + 「剪切」按钮，滑条由合并控件承担；
  4. `setDuration()` 在时长变化时把剪切范围重置为整段并 `emit cutRangeChanged`，
     自动把时间框填成 `00:00:00 ~ 总时长`（避免旧逻辑里"结束还是 00:00:00 导致剪切直接报错"）；
  5. `onTimerOut()` 只在 `not seek_slider.is_dragging()` 时回写位置，避免定时器与用户拖动打架；
     位置/时长文本统一走 `_format_time()`。
- 理由: 一条时间轴同时表达"现在播到哪"和"剪哪一段"，省一行垂直空间；自绘控件能明确控制手柄命中顺序与视觉一致性；
  `is_dragging()` 解决定时器与拖动的竞争。
- 备选与为何不选:
  - 两个 QSlider 叠在同一行：手柄互相抢鼠标事件，命中判定不可控；
  - 继续用 QRangeSlider 当主滑条、额外加播放头：它内部是 QSplitter + 三个 QGroupBox，
    没有第三个可拖标记，等于重写；
  - 保留文字前缀只改左右位置：不满足"去掉文字"的要求。
- 影响 / 约束:
  - 旧属性/方法 `bar_slider`、`cut_bar_slider`、`slider_start`、`slider_end`、`slider_progress_moved`、
    `bar_slider_maxvalue` 全部移除（仓库内无其它引用）；
  - 剪切时间输入框最大宽度 70→90，可完整显示 `00:00:00`；
  - 合并控件依赖 `player.duration()`；时长未知时忽略交互（与旧逻辑一致）；
  - 全屏悬浮面板仍搬三行控件（时间行 / 按钮行 / 剪切行），行数不变；
  - `custom_slider.py`、`range_slider.py` 保留在仓库但不再被视频布局使用（回退时可复用）。
- 相关文件: `src/layout/seek_cut_slider.py`、`src/layout/video_show_layout.py`、`src/layout/__init__.py`
- 首次记录: 2026-10-22
- 变更（2026-10-22，复核）: 控制区布局优化 ——
  左侧/右侧时间标签改**等宽字体 + 固定 66px**（数字跳动不抖）；
  按钮行按「播放控制 | 列表与循环 | 工具」三组、用两段弹性空白分隔，统一最小宽度（72/88/92）
  并补快捷键 tooltip，解决原来"每个按钮被拉伸成等宽大块"；
  播放按钮用 `#video_primary_btn` 高亮；「单曲循环」去掉 emoji（避免与其它按钮高度不一致），
  并新增全局 `QPushButton:checked` 样式给出按下反馈；
  剪切行改为**靠右紧凑排列**，时间框 90→120px 且写入后重置光标（见 PIT-013）。

## ADR-015 悬浮控制面板关闭按钮：18×18 自绘方形（常态淡底方框 + hover 粉底反色）
- 日期: 2026-10-22 | 状态: 已采纳
- 背景: `ISSUE-009` —— 关闭按钮被全局 QSS 的 `min-height`/`padding` 撑成 10×32 竖条；
  而且常态只画一个漂浮的 ✕，看不出"这是按钮"
- 决策:
  1. 保留 `_CloseButton(QPushButton)` 自绘方案（不用 QSS 文字 ✕），尺寸 18×18、圆角 4px；
  2. 常态：淡粉圆角方框（底 `rgba(243,139,168,26)` + 1px `rgba(243,139,168,110)` 描边）+ 粉红 ✕；
     hover：整块 `#f38ba8` 填充 + `#1e1e2e` ✕（沿用标题栏关闭按钮的反色交互）；
  3. 仍然"脱离布局"定位在容器右上角，但尺寸/位置统一从 `_CloseButton.SIZE` 推导，
     容器内容区右边距 12 → 26 给按钮留 26px 槽位
- 理由: 与面板内 30px 高图标按钮同一套圆角/配色语言；18px 比原来 10px 的点击面积约 3 倍，
  又不会比标题栏按钮更抢眼；常态方框让"可点"这件事一目了然
- 备选与为何不选:
  - 纯文字 `QPushButton("✕")` + QSS：依旧受全局 `min-height`/`padding` 影响，还得另写一套边距；
  - 做成 30×30 与行内按钮等高：右上角会挤压第一行右侧的时间标签；
  - 把 ✕ 放进布局单独一行：`ADR-011` 第三次复核时已按用户意见改回角落方案，不再反复
- 影响 / 约束: 容器右边距必须 ≥ `SIZE + 6`（当前 26），否则控制行内容会钻到按钮下面；
  以后改 `SIZE` 只需改类属性，`_position_close_btn()` 自动跟随（不再写死 10）
- 相关文件: `src/layout/floating_control_panel.py`
- 相关条目: `ISSUE-009`、`PIT-014`、`ADR-011`
- 首次记录: 2026-10-22
- 变更（2026-10-22，复用）: 用户要求图片播放控制面板也换成同款样式 ——
  类抽到独立模块 `src/layout/square_close_button.py::SquareCloseButton`，
  边长/提示文案改成构造参数（视频悬浮面板 18px、图片面板 24px，与行内按钮齐平）；
  `pic_show_layout.py` 原来的 `QPushButton("✕")` + `#picControlClose` 两条 QSS 删除；
  绘制内距与笔宽改为按实际边长等比计算（`0.3*边长`、`max(1.4, 边长/12)`），两处共用同一套绘制代码。

## ADR-016 所有弹框统一成「无边框 + 自绘标题栏」的深色对话框（与主窗口同风格）
- 日期: 2026-10-22 | 状态: 已采纳
- 背景: 主窗口是无边框 + 自定义标题栏；但 `QMessageBox` / `QFileDialog` / 手写的 `QDialog` /
  `QProgressDialog` 全都带着 Windows 原生标题栏 —— 深色界面里冒出一条浅色系统边框，
  风格割裂（用户明确要求"不要弹框反而用了默认标题栏风格"）。
- 决策:
  1. 新增 `src/layout/styled_dialogs.py`：
     - `StyledDialog(QDialog)`：`Qt.Dialog | Qt.FramelessWindowHint` + `WA_TranslucentBackground`；
       外壳 `#dialogRoot`（`#1e1e2e` / 1px `#45475a` / 圆角 10）+ 24px 投影；
       `DialogTitleBar` 高 34px（`#181825` + 1px `#313244` 下边线，与主窗口标题栏一致），
       标题 13px 加粗 `#cdd6f4`，右侧复用 `SquareCloseButton`（18px 粉框方形 ✕，见 ADR-015）；
       标题栏按住可拖动，首次显示居中于父窗口并 clamp 到屏幕可用区。
     - `MessageDialog`：info / warning / error / question，图标是自绘圆点 + 字符（不依赖系统图标），
       主按钮走 `#dialogPrimaryBtn`（`#89b4fa` 蓝底深色字）。
     - `AboutDialog`：`QLabel` RichText + 确定。
     - `StyledFileDialog`：`QFileDialog` 强制 `DontUseNativeDialog` 且 `setWindowFlags(Qt.Widget)`
       嵌入外壳；按钮/标签中文化（选择 / 取消 / 位置 / 文件夹 / 文件类型，目录模式的过滤器名"目录"），
       结果走 `selected_files`；`accepted` → 外壳 `accept()`，`rejected` → `reject()`。
     - `ProgressDialog`：标签 + `QProgressBar` + 取消；`canceled` 信号只发一次，
       `is_canceled()` 供同步循环用，`close()`（任务正常结束）不算取消。
  2. 便捷函数 `show_info / show_warning / show_error / ask_yes_no / show_about /
     pick_directory / pick_open_file`；`Player.py`、`src/layout/pic_input_layout.py` 里的
     `QMessageBox.*`、`QFileDialog.get*`、`QProgressDialog` 调用全部替换，
     「设置 → 幻灯片」改成 `StyledDialog` + `make_button_row()`。
- 理由: 一套外壳 + 一套配色，弹框与主窗口 / 悬浮控制面板视觉一致；调用方只需换函数名；
  嵌入非原生 `QFileDialog` 是同时满足"深色主题 + 无系统标题栏"的稳妥做法。
- 备选与为何不选:
  - 只给 `QMessageBox` 套 QSS：标题栏由 Windows 绘制，改不了，仍会出现浅色边框；
  - 自写文件浏览器：盘符 / 网络路径 / 排序 / 新建文件夹细节等于重造轮子；
  - `QFileDialog` 保持顶层 + `FramelessWindowHint`，再往它的 `QGridLayout` 插标题栏：
    内部行号会撞车，Qt 版本升级易碎。
- 影响 / 约束:
  - 弹框没有系统最小化/最大化；关闭只有自绘 ✕ 与 Esc（都是 `reject()`）；
  - 文件框默认 720×440，小屏上会贴近屏幕边缘（居中已 clamp）；
  - `QMessageBox` 不再使用，但 `_install_chinese_translator` 的兜底翻译保留（Qt 内部字符串仍需要，见 PIT-008）；
  - 新增弹框请继承 `StyledDialog` 或直接用便捷函数，不要再写 `QDialog` + 系统标题栏。
- 相关文件: `src/layout/styled_dialogs.py`、`src/layout/square_close_button.py`、`Player.py`、
  `src/layout/pic_input_layout.py`、`src/layout/__init__.py`
- 相关条目: `PIT-008`、`PIT-015`、`ADR-015`
- 首次记录: 2026-10-22

## ADR-017 方向键语义调整：←/→ 上一个/下一个，↑/↓ 快进/快退（原有字母快捷键不动）
- 日期: 2026-10-22 | 状态: 已采纳
- 背景: 用户要求方向键按播放器习惯工作 —— 左 = 上一个、右 = 下一个（图片 + 视频），
  上 = 快进、下 = 快退（视频），同时"原有的快捷键不要动"。
  （原实现：← → 是视频快退/快进，图片的 ← → 才是上一个/下一个）
- 决策:
  1. `MainWindow.keyPressEvent` 重排方向键：
     - ← → `pic_show_layout.down()` + `video_show_layout.previous()`
     - → → `pic_show_layout.up()` + `video_show_layout.next()`
     - ↑ → `video_show_layout.up_time()`（仅视频）
     - ↓ → `video_show_layout.down_time()`（仅视频）
  2. 原有字母键全部保留：W/E（视频上/下一个）、A/D（快退/快进 + 图片上/下一个）、
     Space（播放暂停）、F/Esc（全屏）、Delete / Ctrl+D、S、Z/X/C、Ctrl+B 等一律不动；
     视频控制栏 tooltip 同步为 `上一个视频（W / ←）`、`下一个视频（E / →）`、`快进（↑）`、`快退（↓）`。
  3. 为了让方向键真正生效（原 ←/→ 在点过画面或按钮后就失灵，见 `PIT-016`）：
     - 媒体控件（`QVideoWidget`、两个 `QScrollArea`）与鼠标专用按钮
       （视频控制栏、图片控制面板、`SquareCloseButton`）统一 `Qt.NoFocus`；
     - 播放结束后 `main_window.setFocus()`（原来是 `video_widget.setFocus()` / `qscrollarea.setFocus()`）；
     - 在 viewport 上装 `eventFilter`，`MouseButtonPress` 时把焦点交还主窗口；
     - 全屏悬浮面板是独立顶层窗口，在它的 `keyPressEvent` 里把 Esc / 方向键转发给主窗口。
- 理由: 方向键是播放器最自然的"上一个 / 下一个 / 快进 / 快退"；保留字母键不破坏老用户肌肉记忆；
  焦点策略是 `keyPressEvent` 能收到按键的前提，否则快捷键会"有时灵有时不灵"。
- 备选与为何不选:
  - 用 `QShortcut(Qt.WindowShortcut)` 绑方向键：实测目录树获得焦点时也会触发，破坏树的方向键导航；
  - 应用级 eventFilter 全局拦方向键：会误伤表格 / 输入框 / 文件框，规则难维护；
  - 只在全屏模式生效：用户要求"适用于图片和视频播放"，普通模式也要能用。
- 影响 / 约束:
  - 点击媒体区 / 控制按钮后焦点回到主窗口；这些鼠标专用按钮不再参与 Tab 焦点链；
  - 剪切起止时间输入框（`QLineEdit`）仍可聚焦，聚焦时方向键移动文本光标、不触发播放操作；
  - 目录树保留原有方向键导航（树消费按键，不会触发播放快捷键）；
  - 以后新增的媒体控件 / 控制按钮要沿用 `Qt.NoFocus`，否则会重新出现"快捷键被吞"。
- 相关文件: `Player.py`、`src/layout/video_show_layout.py`、`src/layout/pic_show_layout.py`、
  `src/layout/pic_input_layout.py`、`src/layout/floating_control_panel.py`、
  `src/layout/square_close_button.py`
- 相关条目: `PIT-016`、`ADR-014`
- 首次记录: 2026-10-22

## ADR-018 图片 / 视频评分：内容指纹做主键 + 独立表 `media_rating` + 数字键 1~5 + 状态栏
- 日期: 2026-10-22 | 状态: 已采纳
- 背景: 需求是「图片和视频都能评分；文件移动到别的目录 / 换目录后评分仍能识别；单独建表管理；
  用 1~5 数字键触发；状态栏显示评分结果」。
- 决策:
  1. 新建独立表（`player.db`，不动既有表）：
     ```sql
     media_rating(fingerprint TEXT PRIMARY KEY, rating INTEGER, media_type TEXT,
                  last_path TEXT, file_size INTEGER, create_time TEXT, update_time TEXT)
     -- + CREATE INDEX idx_media_rating_last_path ON media_rating(last_path)
     ```
     由 `src/data_manager/rating_manager.py::RatingManager` 管理（与 `PositionManager` 同风格，
     复用 `Sqlite3Client` 单例；`set_rating / get_rating / delete_rating / rating_count`）。
  2. **主键是内容指纹，不是路径**：`src/utils/utils.py::file_fingerprint()` =
     `blake2b(文件大小 + 首 1MB + 尾 1MB)`（16 字节 → 32 位 hex）。
     视频再大也只读 2MB，切换文件不会卡；小于 2MB 的文件等价于全量哈希。
     文件移动 / 改名 / 换目录后内容不变 ⇒ 指纹不变 ⇒ 评分照样命中。
     `RatingManager` 内部按 `(size, mtime_ns)` 缓存指纹，同一文件不重复读盘。
  3. 交互：`1~5` 数字键（小键盘同样支持）→ `MainWindow._apply_rating()`；
     带 Ctrl/Alt/Shift 的组合键不触发；聚焦在剪切时间输入框等 `QLineEdit` 时由输入框自己消费，
     不会误评分。写入成功后同步刷新 `last_path`，便于排查文件现在在哪。
  4. 状态栏：右侧新增常驻标签 `ratingLabel`（`#ratingLabel`，蓝字 `#89b4fa`）
     显示 `评分：★★★★☆（4 星）`，未评分显示 `评分：—`；
     左侧 `statusLabel` 在评分后显示 `已为图片/视频评分：★★★★☆（4 星）— 文件名`。
     `change_show()` 与图片/视频的 `play()` 都会刷新右侧标签，
     所以移动后的文件一打开就能看到原评分。
- 理由: 路径会因为移动 / 改名失效，内容指纹是唯一既稳定又便宜的关联方式；
  首尾采样把读盘量钉死在 2MB；独立表 + 独立 Manager 与现有 `video_play_position` 结构一致，便于维护。
- 备选与为何不选:
  - 用文件路径做主键（实现最简单，但移动后就丢了，不满足需求）；
  - 全量哈希（几个 GB 的视频每次切换都要读完，明显卡顿）；
  - 用 `(大小, mtime)` 做主键（拷贝 / 改时间的工具会误判，且不同文件容易撞）；
  - 存到 `config` 键值表（评分是结构化数据，独立表便于将来按评分筛选 / 统计）。
- 影响 / 约束:
  - 文件内容被修改后指纹变化 ⇒ 视为新文件，旧评分不再命中（旧记录留在表里，可用 `delete_rating` 清理）；
  - 同一内容的多个副本共享评分（按内容判定，属预期行为）；
  - 私密模式按解密后的明文内容计算指纹 ⇒ 密文移动 / 改名后也能识别；
  - 以后要加「按评分筛选列表」，直接查 `media_rating.rating + last_path` 即可，不必改表结构。
- 相关文件: `src/data_manager/rating_manager.py`、`src/utils/utils.py`、`Player.py`、
  `src/layout/pic_show_layout.py`、`src/layout/video_show_layout.py`、
  `src/data_manager/__init__.py`、`src/__init__.py`
- 相关条目: `PIT-017`、`ADR-017`
- 首次记录: 2026-10-22

## ADR-019 「归集」菜单：按评分 / 关键字 / 路径筛选媒体并批量拷贝
- 日期: 2026-10-22 | 状态: 已采纳
- 背景: 需要把符合条件的图片 / 视频批量拷到一个目录：① 按评分（≥ N 星）；② 按文件名关键字；
  ③ 按目录递归扫描。三者都要能选文件类型（图片+视频 / 仅图片 / 仅视频）与归集数量（默认不限）；
  路径模式还要能选「顺序取前 N 个」或「随机抽取 N 个」；交互顺序是「参数弹框 → 确定 → 选保存目录」。
- 决策:
  1. 菜单「归集(&G)」放在「控制」与「设置」之间，三个动作共用一个 `CollectDialog`
     （`mode='rating' / 'keyword' / 'path'`），基于 `StyledDialog`（见 ADR-016），
     确定按钮文案「开始归集」，取消按钮「取消」。
  2. 参数：
     - rating：评分不低于 N 星（1~5，默认 3）+ 文件类型 + 数量（0 = 不限）；
     - keyword：搜索目录 + 文件名关键字（不区分大小写）+ 文件类型 + 数量；
     - path：搜索目录 + 文件类型 + 数量 + 选择方式（顺序 / 随机；数量为「不限」时该选项置灰）。
     三种模式都先 `pick_directory()` 选保存目录，取消则什么都不做。
  3. 逻辑分层：
     - `src/collect/collect_service.py`：扩展名判定（图片沿用 `is_pic` 列表，视频扩到 17 种）、
       `iter_media_files()`（`os.scandir` 递归、子目录排序保证顺序模式稳定、逐条检查取消）、
       `unique_destination()`（重名追加 " (n)"，绝不覆盖已有文件）；
     - `src/collect/collect_thread.py::CollectThread`：扫描 + `shutil.copy2` 全在后台线程，
       信号 `progress(done,total,text)` / `completed(stats)` / `failed(msg)`，`cancel()` 走 `requestInterruption()`；
     - `src/layout/collect_dialog.py`：参数弹框；
     - `Player.py`：`_open_collect_dialog()` → `_run_collect()`，进度用 `ProgressDialog`（可取消），
       完成后 `show_info` 汇总（拷贝/跳过/失败/取消 + 前几个错误）并写状态栏。
  4. `kind='all'` 的语义是「图片 + 视频」，**不是**「所有文件」：`matches_kind()` 先判媒体类型，
     避免把 `.txt` / `.srt` 一起拷进去。
  5. 评分模式的筛选在 GUI 线程做（查库 + `os.path.isfile` + 类型过滤 + 去重，量小）；
     扫描 / 拷贝这类重 IO 一律放 `CollectThread`（`ISSUE-007` 的教训）。
- 理由: 三种归集只是筛选条件不同，共用一个弹框与一套线程逻辑，代码量小、行为一致；
  后台线程避免大目录 / 大文件拷贝把窗口卡成「未响应」；重名追加序号保证不覆盖用户已有文件。
- 备选与为何不选:
  - 三个独立弹框 / 三套扫描代码：重复度高，后续容易走样；
  - 先选源目录再弹参数框：与需求的交互顺序相反；
  - 用 `shutil.move` 移动：需求明确是"拷贝到这个路径下"，源文件要保留；
  - 覆盖同名文件：会毁数据，改为追加 " (n)"。
- 影响 / 约束:
  - 归集只拷贝、不删除源文件；目标目录不存在会自动创建；
  - 同一批里同名文件依次变成 " (1)"、" (2)"；
  - 取消后已拷贝的文件保留（与私密加解密任务的处理一致）；
  - 扫描不跟随符号链接目录（`follow_symlinks=False`），避免循环；
  - 评分归集依赖 `media_rating.last_path`，文件移动过且之后没再打开过的记录会计入「跳过」。
- 相关文件: `src/collect/collect_service.py`、`src/collect/collect_thread.py`、
  `src/layout/collect_dialog.py`、`Player.py`、`src/data_manager/rating_manager.py`、`src/layout/__init__.py`
- 相关条目: `ADR-018`（评分表）、`ADR-012`（后台扫描）、`ADR-016`（弹框风格）
- 首次记录: 2026-10-22

## ADR-020 `Player.py` 瘦身：入口只做启动控制，窗口逻辑拆进 `src/window/`（mixin + 资源模块）
- 日期: 2026-10-23 | 状态: 已采纳
- 背景: `Player.py` 原来 2110 行，同一个文件里混了四层东西：启动控制（日志 / 单实例锁 / QApplication）、
  MainWindow `__init__` 里 380 行界面组装、7 个功能域（文件树操作 / 全屏快捷键 / 评分 / 归集 /
  私密模式 / 密钥 / 解码器与 ffmpeg）以及全局 QSS、i18n、文件树委托、菜单栏构建。
  想改任何一处都要在两千行文件里翻，且入口读不出「程序是怎么起来的」。
- 决策:
  1. `Player.py` 只保留启动控制流 —— `init_logging()` / `acquire_single_instance_lock()` /
     `QApplication` → `MainWindow` → `app.exec()`，60 余行，`main()` 一眼看到底；
  2. 主窗口移入 `src/window/`：`main_window.py` 的 `MainWindow` **只做状态持有 + 界面组装 + 信号接线**
     （`_init_services` / `_init_window` / `_build_ui` / `_build_media_views` / `_build_file_trees` /
     `_build_work_area` / `_build_title_bar` / `_build_status_bar` / `_build_central_widget` /
     `_restore_last_session` / `_schedule_startup_checks`）；
  3. 功能按职责拆成 mixin：`media_actions` / `view_actions` / `rating_actions` / `collect_actions` /
     `private_actions` / `key_actions` / `tool_actions`；
     纯资源与业务无关的部分独立成模块：`theme`（QSS + 目录树箭头图标）、`i18n`（Qt 中文翻译）、
     `file_tree` / `file_delegate`（左侧树控件与委托）、`menu_bar`（菜单栏构建）；
  4. `MainWindow` 继承顺序 = `(各 mixin..., QMainWindow)`：mixin **必须排在 QMainWindow 之前**，
     否则 `keyPressEvent` / `closeEvent` / `eventFilter` / `changeEvent` 会被基类实现遮蔽；
  5. 类常量（`expand_path_config_key` / `show_type_video` / `normal` / `full` …）留在 `MainWindow`，
     mixin 内原来的 `MainWindow.xxx` 全部改读 `self.xxx`（取值相同）。
- 理由:
  - mixin **保持 `self` 作用域不变** ⇒ 方法体可以逐行原样搬运，重构风险最低（对比组合式 controller
    要把每个 `self.statusLabel` 改成 `self.window.statusLabel`，改动面覆盖全部方法）；
  - 入口只剩启动控制，主窗口只剩「装界面 + 连线」，读代码时能直接跳到对应功能模块；
  - QSS / 菜单 / 文件树这类纯资源代码独立后，改样式或菜单不会碰到业务方法。
- 备选与为何不选:
  - 组合式 controller（`MainWindow` 持有 `MediaController(self)` 等对象）：分层更彻底，但要重写全部
    `self.xxx` 访问、`self` 传参，改一个漏一个的风险远大于收益；
  - 只把 MainWindow 整体挪到 `src/window/main_window.py`、不再拆 mixin：文件仍有 ~1300 行，
    达不到「主入口只做逻辑控制」的目标；
  - 按功能拆成独立 QWidget 子窗口：会改变现有布局层级与信号结构，属于功能性改动，不在重构范围。
- 影响 / 约束:
  - 新增窗口功能：属于哪个域就加到对应 `*_actions.py`，不要往 `main_window.py` 里堆；
  - 新增全局样式：写到 `theme.py`；`view_actions` 里 `screen_normal` / `full_screen_custom`
    通过 `CENTRAL_WIDGET_STYLE` / `CENTRAL_WIDGET_FULLSCREEN_STYLE` 常量切换，别再内联 QSS；
  - 新增 mixin 时**必须**排在 `QMainWindow` 之前，且方法名不要与现有 mixin 重名（会被 MRO 遮蔽）；
  - `_show_about_dialog` 读 VERSION 改用 `get_resource_base_path()`（原实现用 `__file__` 所在目录，
    代码搬到 `src/window/` 后路径会变；开发环境两者都指向仓库根，打包后同样读不到 VERSION）；
  - PyInstaller 无需改脚本：`src/window` 全是静态 import，能从 `Player.py` 分析到。
- 验证方式（可复用）:
  1. `python -m py_compile` 全部改动文件；
  2. **AST 逐方法对比**：把原 `MainWindow` 的方法体与新模块方法体（`self.x` / `MainWindow.x` 归一同一个
     节点）做 `ast.dump` 比较 ⇒ 除 `__init__` / `screen_normal` / `full_screen_custom` /
     `_show_about_dialog` 四处有意改动外全部一致；
  3. QSS 文本逐字符对比（4 段样式表 `identical: True`）；
  4. `symtable` 检查每个模块「被引用但未导入」的全局名 = 0；
  5. `QT_QPA_PLATFORM=offscreen` 下真实构造 `MainWindow` 冒烟：34 个关键属性齐全、6 个菜单与动作文本、
     树列宽/隐藏列、`change_show` / `toggle_tree` / 私密模式切换全部正常。
- 相关文件: `Player.py`、`src/window/*.py`、`README.md`（目录结构）
- 相关条目: `ADR-005`（知识库制度）、`ISSUE-008`（目录树箭头图标，随 `theme.py` 迁移）
- 首次记录: 2026-10-23

## ADR-021 「加载为图片 / 视频列表」统一递归扫描（`MediaScanThread` + 扩展名单点）
- 日期: 2026-10-23 | 状态: 已采纳
- 背景: 用户要求"加载为图片或视频列表时需要支持递归搜索"。排查现状：
  1. **图片列表本来就是递归的** —— `PicScanThread` 用 `os.scandir` + 待处理目录栈递归，
     按 `st_mtime` 升序返回（`ADR-012` 时就已是这个形态）；
  2. **视频列表不是递归的** —— `VideoShowLayout.loadData()` 用
     `glob(os.path.join(path, "*.mp4"))`：只扫一层、只认 `.mp4`；而 `is_video()` 认 `.mp4/.mkv`
     ⇒ 子目录里的视频、`.mkv` 文件都进不了列表（点单个文件却能播 `.mkv`，口径不一致）；
  3. `loadData()` 在 GUI 线程同步 `glob` + 逐个 `getmtime`，大目录会卡（`ISSUE-007` / `ADR-012` 的老问题）。
- 决策:
  1. 抽出 `src/layout/media_scan_thread.py`：`IMAGE_SUFFIXES` / `VIDEO_SUFFIXES` +
     `collect_media_files(root, suffixes, is_cancelled)`（递归 `scandir`、逐条目检查取消、
     `mtime` 升序、取消返回 `None`）+ `MediaScanThread(token, path, suffixes)`（信号 `scanned(token, path, files)`）；
  2. `PicScanThread` 变成 `MediaScanThread` 的薄子类（固定 `IMAGE_SUFFIXES`），
     `PicInputLayout` 的接口与行为**完全不变**；
  3. `VideoShowLayout.loadData()` 改为后台扫描：`_scan_token` / `_scan_threads` / `_on_list_scanned`
     （只接受最新 token），新增 `cancel_scan(wait_ms)`，`MainWindow.closeEvent` 与图片扫描一起调用；
  4. 视频扩展名口径统一：`is_video()` 与列表扫描共用 `VIDEO_SUFFIXES`
     （初版 `.mp4/.mkv`；2026-10-23 已按要求扩展到 24 种常见格式，见下方"补充"）；
  5. 扫描期间点「列表」按钮 → 提示"正在扫描视频列表（含子目录），请稍候…"，不再误报"列表未加载"。
- 理由:
  - 一套递归实现同时服务图片 / 视频两种列表：行为一致（递归 + mtime 升序 + 可取消），不会两套逻辑走样；
  - 扩展名口径单点：以后要支持更多视频格式只改 `VIDEO_SUFFIXES` 一处，`is_video()` 自动跟随；
  - 沿用 `ADR-012` 的后台线程 + token 约定，大目录不再卡 GUI。
- 备选与为何不选:
  - 用 `glob('**/*.mp4', recursive=True)` 就地递归：写法短，但仍在 GUI 线程、无取消、扩展名照样写死；
  - 把 `PicScanThread` 复制一份改成视频版：~40 行几乎相同的递归代码，后续改一处漏一处；
  - 视频扩展名直接扩展到归集用的 17 种：播放器 `is_video()` 只声明支持 mp4/mkv，
    列表里塞进点开就报"文件格式错误"的文件反而更糟；要扩就改 `VIDEO_SUFFIXES` 一处。
- 影响 / 约束:
  - **列表加载变为异步**：`loadData()` 返回时 `play_list` 仍为空，稍后由 `_on_list_scanned` 填充；
    目前唯一调用方 `load_for_video_lise()` 只切显示、不读列表，故不受影响；
    将来若"loadData 之后立刻读 play_list"，必须等 `scanned` 信号或改用回调；
  - 顺序仍是 `mtime` 升序（最旧优先，与原实现一致），递归后子目录文件混入同一序列；
  - 删除最后一个视频后"找下一个"的兜底逻辑**未改**（仍是同目录 `*.mp4`、GUI 线程同步）：
    改成递归会重新引入卡死风险，等确有需求再做后台版；
  - 不跟随符号链接目录（`follow_symlinks=False`），避免目录循环；
  - 扫描线程必须保活（`_scan_threads` 集合 + `finished` 里 discard + `deleteLater`），
    窗口关闭前 `cancel_scan(wait_ms=1500)`。
- 验证:
  1. 纯函数：三层目录的图片 / 视频（含 `.MKV` 大写扩展名）全部递归命中、`.txt` 被排除、
     `mtime` 升序、取消返回 `None`；
  2. 线程：`MediaScanThread` 信号回传 token 与列表，与纯函数结果一致；
  3. 真实窗口：`video.loadData(root)` 立即返回（`play_list` 为空 ⇒ 证明没在 GUI 线程同步扫），
     完成后列表递归填充、线程集合清空；连续切换目录只保留最后一次结果；
  4. 图片链路回归：`PicInputLayout.set_content_path()` → 列表递归包含子目录、不自动播幻灯片、线程清理正常；
  5. 关闭窗口时仍有扫描在跑 → `cancel_scan` 不崩。
- 相关文件: `src/layout/media_scan_thread.py`、`src/layout/pic_scan_thread.py`、
  `src/layout/video_show_layout.py`、`src/layout/pic_show_layout.py`（`is_pic()` 也用 `IMAGE_SUFFIXES`）、
  `src/window/view_actions.py`（`closeEvent`）、`src/layout/pic_input_layout.py`
- 相关条目: `ADR-012`（后台扫描约定）、`ISSUE-007`（GUI 线程同步 os.walk 致假死）
- 首次记录: 2026-10-23
- 补充（2026-10-23，用户要求"扫描增加更多常见视频格式支持"）:
  - 变更:
    1. 扩展名清单上移到**不依赖 PyQt** 的 `src/utils/media_types.py`（`IMAGE_SUFFIXES` / `VIDEO_SUFFIXES`），
       扫描、`is_video()`、`is_pic()`、归集（`collect_service`）全部引用同一份对象
       （测试断言 `collect_service.VIDEO_SUFFIXES is media_types.VIDEO_SUFFIXES`）；
       `media_scan_thread` 保留再导出，旧 import 不用改；
    2. `VIDEO_SUFFIXES` 从 2 种扩到 **24 种**常见容器：
       `.mp4 .m4v .mkv .mov .avi .wmv .flv .webm`（常见）、
       `.mpg .mpeg .mpe .m2v .vob .ts .mts .m2ts`（MPEG 系）、
       `.3gp .3g2 .rmvb .rm .ogv .asf .f4v .divx`（手机 / 其它）；
       是原归集 17 种的超集，所以"归集能拷的"现在"列表也能列出来"；
    3. `collect_media_files(..., recursive=True)` 新增 `recursive=False`：
       删除最后一个视频后"找下一个"的兜底改为 `collect_media_files(path, VIDEO_SUFFIXES, recursive=False)`
       （单层同步扫，既不再写死 `*.mp4`，也不会递归卡 GUI），`glob` 导入随之删除。
  - 影响 / 约束:
    - 列表 / 点击播放的判定都放开了，但**能否真正解码取决于系统解码器 / LAV Filters**：
      `.rmvb/.rm/.vob` 这类在没装对应解码器时会走既有的"无法播放"提示，属预期；
    - 以后再加格式只改 `src/utils/media_types.py` 一处，扫描 / 播放判定 / 归集自动跟随；
    - `.ts` 与 TypeScript 同名后缀：在媒体播放器场景里按 MPEG-TS 处理（原归集清单已有）。
  - 验证: offscreen 用例 13/13 通过 —— 24 种清单、扫描递归命中 22+3 个样本（含大写 `.MKV` / `.mts`）、
    非视频文件不混入、`mtime` 升序、`recursive=False` 只扫当前层、归集口径同步、
    真实窗口 `loadData()` 把 25 个样本全部载入、`is_video()` 认新格式。
- 补充（2026-10-23，图片格式同步扩展）:
  - 变更:
    1. `IMAGE_SUFFIXES` 12 → **25** 种：JPEG 家族（`.jpg .jpeg .jpe .jfif`）、
       `.png .apng`、`.bmp .dib`、`.gif .webp`、`.tif .tiff`、`.ico`、`.tga`、
       Netpbm（`.pbm .pgm .ppm .pnm`）、X11（`.xpm .xbm`）、`.wbmp`、
       矢量（`.svg .svgz`）、`.pcx .avif`；
    2. `PicShowLayout._play_static()` 增加 Pillow 兜底解码（QImage 读不了的格式），
       并新增 `PILLOW_ONLY_SUFFIXES`：Qt 插件名里没有的扩展名**直接**走 Pillow，
       绕开 `QImage()` 的插件嗅探导致的 C++ 访问冲突（详见 `ISSUE-011`）；
    3. 归集 `ALL_SUFFIXES = IMAGE + VIDEO` 自动跟随，`matches_kind()` 对新图片格式判为 `image`。
  - 影响 / 约束:
    - `.svg/.svgz` 依赖 **QtSvg 插件**（开发环境实测可读）；若打包后打不开，
      在构建脚本补 `--hidden-import=PyQt5.QtSvg`（mac 脚本已有，Windows 脚本未加）；
    - 动画 GIF 仍走原 GIF 分支；`.apng` 经 Pillow 解码只显示首帧（不做逐帧动画）；
    - **HEIC / HEIF / PSD / HDR 未纳入**：Qt5 无插件，Pillow 侧需要额外依赖或未实测，
      放入白名单只会让用户看到"无法加载图片"；
    - 以后再加图片格式：改 `IMAGE_SUFFIXES` 一处；若 Qt 插件不支持，同时加进 `PILLOW_ONLY_SUFFIXES`。
  - 验证: offscreen 用例 8/8 通过 —— 25 种格式样本（含大写扩展名 / 子目录）递归扫描 25/25、
    非图片文件不混入、`mtime` 升序、在真实窗口里逐个 `play()` 全部解码成功（含 Pillow 兜底的
    `.dib/.pcx/.pnm/.avif/.apng`）、`is_pic()` 大小写不敏感、`PILLOW_ONLY_SUFFIXES ⊆ IMAGE_SUFFIXES`、
    归集口径同步、整段序列退出码 0（无访问冲突）。
- 补充（2026-10-24，`ISSUE-013`）: `.ts / .mts / .m2ts` 与 TypeScript 源文件后缀冲突，
  扫描时额外做一次 MPEG-TS 同步字节校验（`media_scan._looks_like_mpeg_ts`），
  不匹配的文件不会被当成视频列出；`is_video()` 仍只按后缀判断（用户可手动点开试）。
- 最近复核: 2026-10-24

## ADR-022 扫描与归集多线程化（分层 BFS 扫描 + 并行拷贝）
- 日期: 2026-10-23 | 状态: 已采纳
- 背景: 用户反馈"文件较多时单个线程较慢"，要求扫描与归集都支持多线程。
  现状：
  1. 扫描（图片 / 视频列表、归集筛选）都是**单个线程**串行 `os.scandir`；
     在 900+ 目录、上千文件的树上实测 0.36s，目录再大就会明显变慢（网络盘更甚）；
  2. 归集拷贝是 `for src in files: shutil.copy2(...)`，纯串行，几百个文件就要 1 秒以上，
     大文件（视频）场景更明显；
  3. 归集"扫描 + 拷贝"都在同一个后台 `QThread` 里，无法并行。
- 决策:
  1. **扫描实现迁到 `src/utils/media_scan.py`（不依赖 Qt）**：`collect_media_files(root, suffixes,
     is_cancelled, recursive, max_workers, on_progress)`；
     并发模型是「按目录层级 BFS」——每层的目录并行 `scandir`（`ThreadPoolExecutor`），
     扫完一层再下发下一层；结果最后统一按 `st_mtime` 升序（与并发度无关，顺序稳定）；
     取消返回 `None`；`on_progress(found_count)` 每层回调一次；
     默认 `DEFAULT_SCAN_WORKERS = 8`（可传 `max_workers` 覆盖，上限 64）；
     `recursive=False`（删除后"找下一个视频"这种单目录小扫描）仍然单线程、不开池；
  2. `MediaScanThread`（`src/layout/media_scan_thread.py`）退化成 Qt 封装：
     只持有 token / path / suffixes / `max_workers` 并 `emit scanned(...)`；
     `PicScanThread` 继续作为它的薄子类，`PicInputLayout` 一行不用改；
  3. **归集扫描**改用同一个 `collect_media_files`（`collect_service.suffixes_for_kind(kind)`
     把 kind 映射成扩展名），并在扫描完成后做关键字过滤、按路径排序、再按 limit / random 截断；
  4. **归集拷贝并行**：`ThreadPoolExecutor(max_workers=copy_workers)`，每个文件一个任务，
     默认 `DEFAULT_COPY_WORKERS = 4`（可传 `params['copy_workers']`，上限 32）；
     重名保护 = 「`unique_destination(..., reserved)` 在锁内取号 + 把结果登记进 `reserved` 集合」，
     避免两个线程同时选中"还没落盘的同名目标"而互相覆盖；
     进度信号按"完成数"在锁内自增、限频 0.1s 发出（线程里 `emit` 由 Qt 自动排队）；
     取消时排队中的任务在入口直接 return，已完成的文件保留；
  5. 扫描线程数也可由 `params['scan_workers']` 覆盖（默认 8），方便测试与调优。
- 理由:
  - 扫描与拷贝都是 **IO 密集**（`scandir` / `stat` / `read+write`），`ThreadPoolExecutor` 足够，
    不需要进程池；GIL 在系统调用期间释放，实测有 1.7~2.3 倍加速；
  - 分层 BFS 天然无死锁：一层内的任务互不依赖，下一层只在本层全部返回后才下发；
  - 扫描函数放在 Qt-free 模块里，归集（纯逻辑层）不用为了扫目录去 import PyQt5；
  - 顺序仍由最后统一排序保证，多线程不会打乱"最旧优先 / 路径序"的既有语义。
- 备选与为何不选:
  - **进程池**（`ProcessPoolExecutor`）：路径列表要跨进程序列化，收益抵不过开销，且 Windows 下 fork 语义麻烦；
  - **`asyncio` + `aiofiles`**：Qt 事件循环里再跑一个 asyncio loop 会引入两套事件模型，调试成本高；
  - **一次把整棵树的目录先收集完再并行**：仍要先串行遍历一遍，等于没省；
  - **固定"每层一个任务"用 `QThreadPool`**：Qt 线程池接口不如 `ThreadPoolExecutor` 直接（取消 / 结果收集都得自己写）。
- 影响 / 约束:
  - **并行度取决于同一层目录数**：`a/b/c/d` 这种深链（每层只有一个子目录）没有加速；
    宽树（大量兄弟目录）收益最大；
  - 8 / 4 是经验值：机械盘 / 网络盘上盲目加线程会让寻道互相打断，需要通过
    `max_workers` / `params['scan_workers'|'copy_workers']` 按场景调；
  - **扫描阶段不再逐目录回报**：`iter_media_files(on_dir=...)` 只在开始时回调一次 root，
    进度文字改为"正在扫描：已找到 N 个文件"（每层一次，调用方限频 0.2s）；
  - **"顺序 + 数量限制"的语义微调**：原来是"扫到 N 个就提前停"，现在是"全量扫描 → 排序 → 取前 N"。
    结果更稳定（路径序前 N），代价是大目录即使只要 10 个也会扫完（换来的是并行扫描更快）；
  - 归集重名规则不变（追加 " (n)"），并行下由 `reserved` 集合保证 150 个同名文件拷成 150 个不覆盖的文件；
  - 归集 `stats['copied']` / `failed` 在锁内自增，`completed` 只在所有任务结束后发一次。
- 验证（本机 offscreen，全部通过）:
  1. 扫描：`max_workers=1` 与 `max_workers=8` 结果**完全一致（含顺序）**；
     90 个视频 / 60 张图 / 6×5 层目录树全部命中；`on_progress` 按层递增；取消返回 `None`；
  2. 列表：`MediaScanThread(max_workers=4)` 信号回传正确；`recursive=False` 只看当前层；
  3. 归集：150 个文件（含 5 组同名）4 线程拷贝 → `copied=150 / failed=0`，
     目标目录 150 个文件、145 个带 " (n)" 后缀（**没有互相覆盖**），进度单调递增；
  4. 归集分支：`sequence + limit=7` → 7 个；关键字 `clip` → 30 个；评分模式传入 12 个 → 12 个；
     中途取消 → `cancelled=True`、已拷贝 5 个保留、任务正常结束；
  5. 基准（只记录，不作断言）：扫描 920 目录 / 1800 文件 0.361s → 0.157s（**2.31x**）；
     拷贝 300 × 100KB 1.236s → 0.736s（**1.68x**）。
- 相关文件: `src/utils/media_scan.py`（新增）、`src/layout/media_scan_thread.py`、
  `src/collect/collect_service.py`、`src/collect/collect_thread.py`
- 相关条目: `ADR-012`（后台扫描约定）、`ADR-021`（递归扫描 / 扩展名单点）、`ISSUE-007`（GUI 线程同步 IO 致假死）
- 首次记录: 2026-10-23
- 变更（2026-10-24）: **扫描调度部分被 `ADR-023` 取代** —— 从「分层 BFS + 每层提交一批」
  改成「任务队列 + 常驻线程池」（去重 / 空等待 / 结束判定 / junction 防环）。
  归集的并行拷贝（`DEFAULT_COPY_WORKERS = 4`、`reserved` 重名保护、进度限频、取消保留已拷文件）
  不受影响，仍然按本条的决策执行。

## ADR-023 扫描调度重做：任务队列 + 常驻线程池（去重 / 空等待 / 结束判定 / 防环）
- 日期: 2026-10-24 | 状态: 已采纳
- 背景: `ADR-022` 用的是「分层 BFS + 每层 `ThreadPoolExecutor` 提交一批」，有两个问题：
  1. **层屏障**：本层所有目录扫完才下发下一层，一个慢目录（网络盘 / 大目录）会拖住整层；
  2. 每层都要新建一批 future，深树下调度开销累积。
  用户提出更直接的模型：**一个任务队列 + 一个线程池**，每个任务 = 一个绝对路径目录，
  线程领任务 → 只扫该目录里的文件 → 把子目录放回队列；没任务就等待；队列去重。
- 缺陷核对（实现前逐条过了一遍，全部补上）:

  | # | 原始设计的坑 | 后果 | 补全方式 |
  | --- | --- | --- | --- |
  | 1 | 「没任务就退出」 | **漏扫**：A 线程还在扫根目录时，B 线程看到空队列退出 → 根目录的子目录再没人扫 | 队列维护 `pending`（队列中 + 在途目录数）；只有 `pending == 0` 才广播结束，否则 `Condition.wait()` 等待 |
  | 2 | 去重键用原始路径 | 大小写 / 相对路径 / 尾部 `\` 不一致被当成不同目录；**junction 环**（`base\loop -> base`）路径每层都不同，去重完全失效 → 无限递归 | 键 = `normcase(abspath(path))`；junction / 目录软链**用 `realpath` 做键**（跟随但不重复、天然防环） |
  | 3 | 持锁扫目录 | 慢 IO 期间所有线程都拿不到任务，等于退化成单线程 | 锁只在「取任务 / 入队 / 记账」时持有，`os.scandir` 全程在锁外 |
  | 4 | 异常路径不记账 | 某线程抛异常没 `done()` → `pending` 永不归零 → 全体永久等待（假死） | `try/except/finally`：异常只记日志，`finally` 保证 `done()` |
  | 5 | 回调异常 | `on_progress` / 取消判定抛异常会杀死 worker，同样导致 `pending` 不归零 | 回调包 `try/except`（取消判定异常当"未取消"，进度回调异常只告警），且回调在锁外调用 |
  | 6 | 取消时 `pending` 不归零 | 主线程 `join` 卡住，关闭窗口 / 换目录都没反应 | `close()` 置 `_closed` 并 `notify_all()`，所有等待者立刻返回 `None`；主线程轮询取消后 `close()` |
  | 7 | 只按 `mtime` 排序 | 并发下相同 `mtime` 的文件相对顺序随线程完成顺序变化 → 列表顺序抖动 | 排序键 `(mtime, normcase(path))`，顺序稳定 |
  | 8 | 无界队列 | 目录极多时内存随目录数增长（路径字符串） | 记录为约束：媒体库规模下可接受；要上限就得牺牲并行度（未做） |
  | 9 | 单目录场景也开池 | `recursive=False`（删除后"找下一个视频"）开销反而变大 | 单层扫描仍走同步单线程，不开池 |
  | 10 | 目录扫描期间被删除 / 无权限 | 整个扫描失败 | 单目录 `OSError` 跳过，不影响其它分支 |
  | 11 | 同一文件多条路径（硬链接 / 两个 junction 指向同一目录） | 文件重复出现 | 目录级去重即可保证不重复扫描；同一文件的不同路径仍按"不同文件"列出（符合列表语义） |
  | 12 | 参数非法 / 线程数过大 | 崩或把磁盘打爆 | `max(1, min(int(值), 64))`，非法值回落默认 8 |

  另：Windows 实测 `DirEntry.is_dir(follow_symlinks=False)` 对 **junction 返回 True、`is_symlink()` 返回 False**，
  只有 `is_junction()` 认得出（Python 3.12+）—— 这是坑 #2 的实证依据，必须显式处理，
  否则用户目录里只要有一个自引用 junction 就永远扫不完。
- 决策:
  1. `src/utils/media_scan.py::_ScanQueue`：`deque` + `_keys`（去重）+ `_pending`（在途计数）+
     `Condition`；`put()` 去重入队、`get()` 空则等待/结束则返回 `None`、`done()` 记账并广播、`close()` 取消；
  2. `collect_media_files()` 起 `max_workers` 个常驻 worker（默认 8），主线程只负责轮询取消 + `join`；
     worker 本地累积结果，退出时合并，避免每个文件抢锁；
  3. junction / 目录软链：跟随扫描（不漏），用 `realpath` 做去重键（不重复、不死循环）；
  4. 结果排序 `(mtime, normcase(path))`；`on_progress` 每 0.1s 最多一次、锁外调用；
  5. `recursive=False` 保持同步单线程。
- 理由: 任务队列是流水线，慢目录只占一个线程、不会阻塞其它分支；
  队列的"空 vs 结束"语义用计数 + 条件变量表达最直接；去重放在队列层，调用方无需关心。
- 备选与为何不选:
  - 继续用分层 BFS（`ADR-022`）：层屏障问题无解，除非再加"层内超时"，复杂度更高；
  - `queue.Queue` + `join()` + 哨兵：`join()` 只能主线程等，worker 之间没法用它判断"该不该退出"，
    还是要自己维护计数，不如直接 `Condition`；
  - 给 junction 直接跳过（不跟随）：实现最简单，但用户用 junction 挂载媒体目录时会**漏扫**；
  - 用 `os.walk`（自带防环？没有）：`os.walk` 默认不跟随软链，但 junction 在 Windows 上会被当目录进去，同样有环风险。
- 影响 / 约束:
  - 队列无界：目录数极大时内存随路径数增长（未设上限，避免牺牲速度）；
  - 取消的响应粒度 = 一次 `scandir`（无法中断正在返回目录项的系统调用），与旧实现一致；
  - junction / 软链会被跟随（旧实现会跳过），**行为变化**：链接目标里的媒体现在也会出现在列表里；
    同一真实目录被多个链接指向时只扫一次（路径取第一次发现的那个）；
  - `pending` 计数依赖"入队即 +1、处理完 -1"，任何新增的入队入口都必须走 `put()`（不要直接 `append`）。
- 验证（本机 offscreen，24/24 + 集成 6/6 全部通过）:
  1. **不遗漏**：270 个视频的宽+深目录树，与独立参照 `os.walk` 结果**集合完全一致**；
     `max_workers` = 1 / 4 / 16 三次结果**含顺序完全一致**，无重复路径；
  2. **队列语义**：重复入队被拒（`pending` 只记一次）；队列空 + 有在途目录时消费者**阻塞等待**
     （不返回 `None`）；新任务入队后等待者立刻领到；`pending` 归零才返回 `None`；`close()` 能唤醒等待者；
  3. **防环**：`mklink /J loop <base>`（自引用）下扫描 0.01s 结束、文件数与参照集一致（无重复、无递归）；
     指向外部目录的 junction 被跟随且只扫一次（不漏扫）；
  4. **健壮性**：取消返回 `None`；`on_progress` 故意抛异常仍能扫完；`recursive=False` 只看当前层；
     不存在目录返回 `[]`；`max_workers='x'` 自动回落；多次扫描结果一致；
  5. **集成**：归集（8 线程扫描 + 4 线程拷贝）60 个同名文件全拷成功不覆盖；`MediaScanThread` 与
     窗口视频列表均正常；
  6. 基准（315 目录 / 900 视频）：1 线程 0.054s → 8 线程 0.029s（**1.83x**）。
- 相关文件: `src/utils/media_scan.py`（重写 `_ScanQueue` / `collect_media_files`）
- 相关条目: `ADR-022`（多线程化，调度部分被本条取代）、`ADR-012`、`ISSUE-007`
- 首次记录: 2026-10-24

## ADR-024 点目录加载图片列表改为「300ms 防抖」+ 拒绝访问告警限流
- 日期: 2026-10-24 | 状态: 已废弃（被 ADR-025 取代）
- 背景: 用户反馈"没点右键，为什么触发了图片扫描"。排查确认链路是
  `treeView.clicked → MediaActionsMixin.on_tree_clicked`：
  **只要左键点中目录（包括点展开箭头）就会 `set_content_path(dir)` 立刻递归扫该目录的图片**。
  这是既有交互（"点目录 = 看这个目录的图片"），但在树里翻目录 / 展开系统目录时会产生大量无用扫描：
  实测先点 `C:/Users` 再点 `C:/MININT`，两个扫描线程先后启动、第一个被第二个中断
  （日志 `媒体扫描已取消: C:/Users`），还刷出 30+ 条"拒绝访问"警告。
- 决策:
  1. 目录点击改为 **300ms 防抖**（`PIC_SCAN_DEBOUNCE_MS`）：期间又点了别的目录就重置计时器，
     只有"最后停下来"的那个目录会被真正扫描；
  2. 点了具体文件 / 切到视频模式 / 进入私密模式时，取消排队中的目录扫描
     （避免用户已经去看视频了，后台还在扫目录、抢 IO）；
  3. `media_scan` 的"拒绝访问"告警限流：每次扫描前 10 条 WARNING + 1 条汇总，
     其余降为 DEBUG（`_log_access_warning`；`collect_media_files` 开始时重置计数）。
- 理由: 交互语义不变（点目录仍然加载该目录图片），但避免"翻树时每个目录都扫一遍"；
  同时把系统目录的权限噪声从日志里压下去。
- 备选与为何不选:
  - 改成"只有右键菜单才扫图片"：交互变化大，用户已习惯点目录看图；
  - 先判断目录里有没有图片再决定扫不扫：判断本身就要扫（循环依赖）；
  - 区分"点展开箭头"与"点条目"：Qt 的 `clicked` 两者都会触发，靠坐标判断分支区域太脆弱。
- 影响 / 约束:
  - 点目录后图片列表最多延迟 300ms 才刷新（大目录本来也要等扫描）；
  - `content_path` / `list_files` 不再是"点完立刻可用"；**新代码不要"点目录后同步读列表"**，
    要等 `PicInputLayout._on_scan_finished` / 扫描回调；
  - 防抖定时器挂在主窗口（`_pic_scan_timer`），随父对象销毁。
- 验证: offscreen 用例 10/10 —— 点目录不立即扫描；连续点 3 个目录只扫最后一个且列表内容是最后一个目录的；
  点文件 / 切视频模式都会取消排队任务；告警 10 条 WARNING + 1 条汇总 + 其余 DEBUG。
- 相关文件: `src/window/media_actions.py`、`src/window/view_actions.py`、
  `src/window/private_actions.py`、`src/utils/media_scan.py`
- 相关条目: `ISSUE-007`（扫描必须放后台）、`ADR-023`（扫描调度）
- 废弃说明（2026-10-24）: 用户明确要求"点目录不要自动扫描，只有右键菜单 / 功能菜单才触发"，
  防抖实现已删除，改由 `ADR-025` 接管；本条的**告警限流**部分继续保留生效。

## ADR-025 取消「点目录自动扫描」：列表只由右键菜单 / 文件菜单显式加载
- 日期: 2026-10-24 | 状态: 已采纳
- 背景: `ADR-024` 只是给"点目录就扫图片"加了防抖，但用户的实际诉求是**根本不要自动扫**：
  在树里点/展开目录（包括点展开箭头）都会触发对该目录的图片递归扫描，扫 `C:/Users` 这种目录要
  一分钟以上，还会把模式从视频切到图片，属于"我没让你扫你却扫了"。
- 决策:
  1. `MediaActionsMixin.on_tree_clicked()` 的**目录分支直接 return**：单击目录只做选中 / 展开，
     **不扫描、不切换显示模式**（也不再停止正在播放的幻灯片）；
  2. 列表加载只保留显式入口：
     - 右键菜单：`加载为幻灯片列表` / `加载为视频列表`（原有）；
     - **文件菜单新增**：`加载为幻灯片列表...(&P)` / `加载为视频列表...(&M)`
       （`load_pic_list_dialog()` / `load_video_list_dialog()`，先弹目录选择框，再走与右键相同的加载逻辑）；
  3. 删除 `ADR-024` 的防抖实现（`_schedule_pic_scan` / `_apply_pending_pic_scan` / `_cancel_pic_scan`
     及 `PIC_SCAN_DEBOUNCE_MS`），`view_actions` / `private_actions` 里的相应调用一并去掉。
- 理由: 扫描是重 IO（大目录几十秒到几分钟），必须由用户显式发起；菜单入口比"点目录"更可控、更可发现。
- 备选与为何不选:
  - 保留防抖（`ADR-024`）：仍然会"点一下就扫"，只是少扫几个，不符合"不要自动扫"；
  - 点目录弹确认框"要加载图片列表吗？"：每次都弹很烦；
  - 只在目录里存在图片时才扫：还是要先扫才知道（循环依赖）。
- 影响 / 约束:
  - **行为变化**：点击目录不再自动显示该目录的图片；要看图片请用右键菜单或「文件」菜单；
  - 点目录也不再从视频模式切到图片模式（更符合直觉）；
  - 右键菜单 / 文件菜单两条路径都走同一个 `set_content_path()` / `loadData()`，行为一致。
- 验证: offscreen 用例 9/9 —— 点目录不扫描、不切模式；点单个视频仍能播放；
  文件菜单两个入口分别触发图片扫描 / 视频列表加载；junction+ACL 场景见 `ISSUE-014`。
- 相关文件: `src/window/media_actions.py`、`src/window/menu_bar.py`、
  `src/window/view_actions.py`、`src/window/private_actions.py`
- 相关条目: `ADR-024`（已废弃）、`ISSUE-014`（同一次反馈里的漏扫 bug）、`ISSUE-007`
- 首次记录: 2026-10-24

## ADR-026 「私密模式」是否值得作为独立模式：建议删掉模式开关、合并为单一工作区（仅评估，待决）
- 日期: 2026-10-24 | 状态: 已采纳（阶段 1 已落地；阶段 2 明确不做）
- 背景: 用户提出「私密模式是否有必要存在；能否与普通模式合并，一个界面包含两者全部功能，并去掉视图菜单里的模式选择」。
- 评估（以当前代码为证）:
  1. **模式不是安全边界**：`_toggle_private_mode()` 只改内存标志 + 显隐控件，**没有任何口令 / 鉴权**
     （`private_actions.py:16-60`）；`private_mode` 不持久化（`main_window.py:99`，重启恒 `False`）。
     也就是说任何人点一下「视图 → 私密模式」就能看到私密库，模式挡不住本机用户；
     真正的保护来自 AES-256-GCM + 随机文件名 + 密钥库（`ADR-009`）。
  2. **私密树是普通树的功能子集**：私密树右键只有「加密 / 解密 / 刷新」三项（`private_actions.py:247-251`）；
     普通树有复制 / 移动 / 删除 / 刷新 / 加载为幻灯片列表 / 加载为视频列表 / 设置为截图路径 /
     设置为剪切路径 / 设置默认展开（`media_actions.py:44-69`）。而私密模式下点目录会**同步解密整目录图片**
     （`private_actions.py:172-227`），与 `ADR-025`「点目录不做事」直接冲突。
  3. **代价是双份 UI 状态**：两套 `QDirModel` + 两棵 `FileTreeView`（`main_window.py:149-166`）、
     三栏 splitter、私密占位层与「打开私密库」按钮（`main_window.py:176-198`）、
     切模式时保存 / 恢复可见性与比例（`private_actions.py:62-87`），`private_mode` 分支还散在
     `view_actions.py:35 / 230`；`private_tree_model.refresh()` 要在 `key_actions.py:60`、
     `private_actions.py:349` 各刷一次。引用计数（`private_mode|private_tree|private_overlay|private_library`）：
     `main_window.py` 19 / `private_actions.py` 38 / `menu_bar.py` 9 / `view_actions.py` 4 / `key_actions.py` 1。
  4. **密文在普通树里本来就看得见**：`QDirModel` 不过滤文件，32 位 hex 无扩展名密文在普通模式下同样显示；
     只是 `on_tree_clicked()` 按扩展名判类型（`pic_show_layout.py:432` / `video_show_layout.py:880`），
     密文落到「文件格式错误!!!」（`media_actions.py:201-204`）。
     所以合并缺的不是安全，而是**点击时的解密分流**。
- 决策建议（待用户确认后实施）:
  - **阶段 1（推荐先做，风险低）：删掉模式开关，只留一套树 / 工作区。**
    1. `menu_bar.py`：删 `mode_group` / `normal_mode_action` / `private_mode_action`；视图菜单只留
       「文件列表面板」「显示控制器」；文件菜单加「打开私密库...」（用 `private.library.path` 记路径、
       把树根切过去，替代原来的占位按钮）。
    2. `main_window.py`：删 `private_mode` 标志、`private_tree_model/view`、`private_overlay_widget`；
       splitter 回到两栏。
    3. `media_actions.on_tree_clicked()`：入口先 `private_service.resolve_playable(self.path)`（密文→解密缓存、
       明文原样），再按返回的 `play_path` 判视频 / 图片，标题栏用原始文件名。`describe()` 只查一次 sqlite
       + 读 4 字节文件头，单击开销可忽略。
    4. `media_actions.right_click_menu()`：补「加密该路径下的图片和视频」「解密该路径下的文件」，
       复用现成的 `_encrypt_private_path` / `_decrypt_private_path`。
    5. `private_actions.py`：删 `_toggle_private_mode` / `_save_normal_state` / `_restore_normal_state` /
       `_show_private_overlay` / `_load_private_library` / `_on_private_tree_clicked` / `_private_right_click_menu`；
       保留批量加解密、`_load_private_slideshow`（改挂到显式菜单项）与全部进度 / 失败回调。
    6. `view_actions.py`：去掉两处 `private_mode` 分支（`screen_normal` / `toggle_tree`）。
    7. `key_actions.py` 与批量完成回调：`private_tree_model.refresh()` → `model.refresh()`。
  - **阶段 2（可选、暂不建议）**：让「加载为幻灯片 / 视频列表」的扫描包含密文并按需解密。
    要动 `PicInputLayout._on_scan_finished` 与 `VideoShowLayout.loadData`（后者 50KB 遗留代码），
    风险远高于收益；阶段 1 用显式的「加载私密幻灯片（含密文）」保住现有能力即可。
- 理由: 模式开关不提供任何访问控制，却带来双份 UI 状态、功能割裂（私密树少 8 个普通树入口：复制 / 移动 /
  删除 / 加载为幻灯片列表 / 加载为视频列表 / 截图路径 / 剪切路径 / 默认展开）和与 `ADR-025`
  冲突的隐式扫描；合并后「一份界面 = 全部功能」，加密 / 解密退化为普通的**文件操作**，语义更准。
- 备选与为何不选:
  - 保留模式并加口令解锁 / 自动锁定：能做，但要新增解锁 UI、超时锁定、忘记口令兜底，
    且仍挡不住资源管理器 / 其它进程直接看密文；安全收益接近 0。
  - 保留模式、只把两棵树补成等价：等于每类操作写两遍，维护成本翻倍，模式本身仍无意义。
  - 阶段 1 就做密文列表扫描：视频列表切歌时要逐个解密大文件，还要改 50KB 遗留布局，收益不抵风险。
- 影响 / 约束（实施时要注意）:
  - **密文可见性**：合并后普通树里能直接看到 hex 名密文（现在普通模式也能看到，不是新增暴露）；
    「打开私密库」书签保留一键进入。
  - **误删风险（新增）**：普通树右键「删除 / 移动」可作用到密文；建议对密文目标的「删除」加二次确认
    （删掉密文＝丢数据，密钥库救不回）。
  - **私密幻灯片**：点目录不再自动解密（符合 `ADR-025`），必须走显式菜单项；
    `_load_private_slideshow` 逻辑原样保留，只换触发入口。
  - **列表 / 归集不含密文**：`media_scan` / `collect` 按扩展名筛，密文天然被排除（本次不处理；
    归集若需要，直接拷密文即可，另开条目）。
  - **评分不受影响**：`RatingManager` 用内容指纹（`rating_manager.py:61`），密文解密后指纹与明文一致。
- 验证方法（阶段 1 实施后，offscreen 构造 `MainWindow`）:
  1. 菜单里没有「普通模式 / 私密模式」，视图菜单只剩两项；
  2. 普通图片 / 视频点击仍能播放；密文点击 → 解密到缓存并播放，标题栏显示原文件名；
     缺密钥 → 弹提示不崩溃；
  3. 右键「加密该路径下的图片和视频」→ 密文生成、源文件删除；「解密该路径下的文件」→ 原名恢复；
  4. 私密幻灯片动作能把整目录图片按序展示；
  5. 全屏进出、`Ctrl+B` 切树、关闭清理缓存均正常。
- 相关文件: `src/window/private_actions.py`、`src/window/main_window.py`、`src/window/menu_bar.py`、
  `src/window/media_actions.py`、`src/window/view_actions.py`、`src/window/key_actions.py`、
  `src/private_mode/private_service.py`
- 相关条目: `ADR-009`（密钥 / 加解密方案，不变）、`ADR-020`（mixin 拆分）、`ADR-025`（点目录不扫描）
- 首次记录: 2026-10-24
- 落地结果（2026-10-24，阶段 1 已完成）:
  - `menu_bar.py`：删 `mode_group` 与两个模式 QAction；视图菜单只剩「文件列表面板」「显示控制器」；
    文件菜单新增「打开私密库...」「加载为私密幻灯片列表...」（密文没有扩展名，普通扫描认不出）；
  - `main_window.py`：删 `private_mode` 标志、`private_tree_model/view`、`private_overlay_widget`
    与「打开私密库」按钮；splitter 回到两栏 `[10000*left, 10000*right]`；
  - `media_actions.py`：`right_click_menu()` 重写为 4 组（加载列表 / 文件操作 / 路径设置 / 私密操作子菜单），
    菜单位置改用 `treeView.viewport().mapToGlobal(pos)`（错误写法见 `PIT-020`）；
    `on_tree_clicked()` 统一走 `private_service.resolve_playable()`；`delete()` 对密文加二次确认；
  - `private_actions.py`：删模式切换 / 状态保存恢复 / 私密树点击 / 私密右键菜单 / 覆盖层；
    保留 `_open_private_library`（改为切树根）、`_load_private_slideshow`、加解密与批量进度回调；
    新增 `_is_encrypted_file` / `_encrypt_current_target` / `_decrypt_current_target` /
    `load_private_pic_list_dialog` / `load_private_slideshow_for_target`（378 → 265 行）；
  - `view_actions.py`：去掉 `private_mode` 两个分支（全屏隐藏树 / `Ctrl+B` 提前 return）；
  - `key_actions.py`：`private_tree_model.refresh()` → `model.refresh()`；
  - `file_tree.py`、`README.md` 文档同步；
  - 全仓库 `private_mode|private_tree|private_overlay|normal_mode_action|_toggle_private_mode`
    引用归零（只剩包名 `src.private_mode`，与界面模式无关）。
- 验证（offscreen 窗口级冒烟 **36 项全 PASS**，脚本 `tmp\smoke_merge.py`，验证后已清理）:
  1. 8 个已删属性 `hasattr == False`；splitter 两栏；
  2. 视图菜单无模式项、文件菜单两个新入口在位；
  3. 右键菜单 4 组齐全 + 私密子菜单 3 项；文件目标禁用目录类动作、目录目标启用；
     空白处右键（无目标）只剩「刷新」可用；
  4. 明文图片点击正常播放；密文点击 → 解密到 `cache/<md5>/<原名>` 并播放，标题栏显示原名；
  5. 右键「加密 / 解密」正确转发右键目标；私密幻灯片列出 2 张缓存明文并显示；
  6. `Ctrl+B`、全屏进出、关闭清理缓存均正常。
  - 另外逐函数比对：`_encrypt_private_path` / `_decrypt_private_path` / `_on_private_batch_progress`
    与重构前**逐行相同**；`_run_private_batch` / `_on_private_batch_completed` / `_on_private_batch_failed`
    只有「私密模式 → 私密操作」文案和删掉 `private_tree_model.refresh()` 两处差异。
- 阶段 2（密文参与「加载为幻灯片 / 视频列表」扫描、树里显示原文件名）**部分落地**：
  「私密视频列表」以**显式入口 + 按需解密**的方式补上（`ADR-027`），没有改扫描器；
  「树里显示解密后原名」仍未做（当前用 `[私密库]` 目录标记代替）。

## ADR-027 私密视频列表（播到哪一集解哪一集）+ 私密库目录标记 + 私密侧扩展名口径统一
- 日期: 2026-10-24 | 状态: 已采纳
- 背景: `ADR-026` 合并模式后，私密操作只剩「加载私密幻灯片」。用户提出两点：
  ① 想按列表播放私密视频，得有对应入口；② 需要「把某个目录标记为私密库」，
     以标识该目录下都是加密文件（否则密文没有扩展名，普通入口扫出来是 0 个，看着像坏了）。
- 决策:
  1. **私密视频列表**：`PrivateService.list_videos(dir_path)`（含密文、按 mtime 升序）；
     `VideoShowLayout` 增加 `set_path_resolver()`，在 `play()` 里把密文换成缓存明文 ⇒
     列表里直接放**密文原路径**，播到哪一集才解密哪一集，不预先解整目录大文件；
     解析失败返回空串，列表模式自动走已有的 `_skip_unplayable()` 跳过。
  2. **私密库标记**：配置项 `private.library.dirs`（JSON 数组，绝对路径），右键在
     「标记为私密库（本目录全是密文）/ 取消私密库标记」之间切换；标记对**子目录**同样生效；
     树里该目录行追加 `[私密库]` 并高亮（`FileDisplayDelegate.paint`），tooltip 补一句说明；
     标记目录上的「加载为幻灯片 / 视频列表」自动改走解密分支（右键菜单与文件菜单两个入口都做了）。
  3. **扩展名口径统一**：私密侧 `IMAGE_EXTENSIONS / VIDEO_EXTENSIONS` 改为复用
     `src/utils/media_types.py`（25 图 / 24 视频），加密范围、`describe()`、`list_images()`、
     `list_videos()` 全部同一份清单（原来私密侧只有 12 图 + mp4/mkv，.avi/.mov/.svg 既加不了密也列不出来）。
- 理由: 视频动辄几百 MB~数 GB，加载列表时全量解密既慢又占盘；按需解密把成本摊到真正看的那一集。
  标记则解决「密文没扩展名 ⇒ 普通扫描 0 结果」的误导，并给树一个可见标识。
- 备选与为何不选:
  - 视频列表也在加载时全解密（与幻灯片一致）：实现最简单，但 10 集 5GB 的目录要先解 5GB 才开播；
  - 列表里放解密后的缓存路径：切集时会指向过期缓存（批量操作 / 重启后失效）；
  - 标记写进文件系统（`desktop.ini` / 隐藏标记文件）：会被同步盘带走，对「本机私密」语义过重；
  - 只做视觉标记、不改加载行为：用户还得手动选「私密视频列表」，容易以为普通入口坏了；
  - 在 `looks_like_plain_media()` 里补齐所有容器签名：每加一种格式都要维护，
    不如「有媒体扩展名 ⇒ 必是明文」这条硬规则（落地时暴露的误判见 `ISSUE-015`）。
- 影响 / 约束:
  - `VideoShowLayout.play()` 多 4 行解析逻辑；解析器用 **lambda 动态取服务实例**（见 `PIT-021`），
    直接绑定实例方法在替换 `private_service` 后会失效；
  - 密文视频的播放位置记忆落在缓存路径上（缓存退出即清），与合并前行为一致；
  - `ISSUE-015`：`encrypt_one()` / `scan_encryptable()` 的密文判定改为
    「`is_v2_file()` 或（无扩展名 + `looks_encrypted()`）」，否则 .mpg/.vob/.ts/.rmvb 会被误判为已加密；
  - `.ts/.mts/.m2ts` 复用 `media_scan.is_mpeg_ts_file()`（新增公开包装），与扫描端同一套校验（`ISSUE-013`）；
  - `private.library.dirs` 是新增配置项（首次运行不存在）；JSON 直接拼进 `config` 表，
    含单引号的路径仍受 `ConfigManager` 字符串拼 SQL 的限制（本机路径极少出现，未改 `ConfigManager`）。
- 验证（offscreen 窗口级冒烟 **44 项 PASS / 0 FAIL**，脚本 `tmp\smoke_private.py`，验证后已清理）:
  1. 标记写入配置 / 重读 / 祖先判定 / 取消标记都正确，未标记目录不受影响；
  2. 已标记目录的右键项显示「取消私密库标记」；标记目录上的「加载为视频列表」自动走私密分支；
  3. `list_videos()` 只列视频、返回密文原路径；`.ts` 文本被排除、真 MPEG-TS 保留；
  4. 密文视频第 1 集与 `next()` 的下一集都解到 `cache/<md5>/<原名>`；
  5. `FileDisplayDelegate.paint` 绘制 `[私密库]` 行不崩；`Ctrl+B`、全屏进出正常；
  6. 测试写入的 `private.library.dirs` 已在收尾删掉（`player.db` 无残留）。
- 相关文件: `src/private_mode/private_service.py`、`src/layout/video_show_layout.py`、
  `src/window/private_actions.py`、`src/window/media_actions.py`、`src/window/file_delegate.py`、
  `src/window/menu_bar.py`、`src/window/main_window.py`、`src/utils/media_scan.py`
- 相关条目: `ADR-026`（模式合并）、`ADR-021`（扩展名单点）、`ISSUE-013`（TS 校验）、
  `ISSUE-015`（密文误判）、`PIT-021`
- 首次记录: 2026-10-24