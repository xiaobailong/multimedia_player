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