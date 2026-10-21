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