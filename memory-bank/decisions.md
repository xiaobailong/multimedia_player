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