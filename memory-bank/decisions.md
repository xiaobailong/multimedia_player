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