- **每次会话开始必须先加载记忆库**（硬性约定，最高优先级）：新会话启动后，在执行任何任务之前，
  必须先读取并消化以下文件，建立对项目上下文、历史踩坑、已有决策的完整认知：
  1. `.clinerules/rules.md` —— 本文件，项目级行为约定
  2. `.clinerules/memory-bank.md` —— 知识库读写强制规则
  3. `.clinerules/tmp-files.md` —— 临时文件归属约定
  4. `memory-bank/README.md` —— 知识库索引与协议
  5. `memory-bank/issues-solved.md` / `pitfalls.md` / `decisions.md` —— 已解决问题、踩坑记录、技术决策
  加载完成后，在回复中简要报告：命中了哪些关键条目、当前项目状态概要。
  此约定优先级高于一切任务指令 —— 未加载记忆库前，不得执行任何代码修改或命令。
- 处于 Act/YOLO 模式时不要请求批准，直接执行；仅在操作不可逆（删除数据、强推、改生产配置）时才停下确认。
- 需要技术选型时自行采用推荐方案并在结尾说明理由，不要用提问工具等待确认；失败时按预设备选方案自动重试，最多 3 轮。
- **构建一律由用户手工执行，Cline 默认不跑构建**（硬性约定）：本仓库构建耗时较长，
  （全量 PyInstaller 打包 3~8 分钟），所以 Cline **不要**主动运行**任何**构建类命令 ——
  `build.bat`（全流程）、`build.bat onedir`、`build.bat onefile`、`build.bat zip` 等都算在内。
  **只有用户当场明确要求**（例如"跑一下构建"/"build 一下"）才可以执行；
  需要验证构建结果时，改为提醒用户手工点击构建，并在拿到日志后再分析。
- **改完的自测 = 静态验证（不是构建）**：默认只跑
  `python -m py_compile <改动文件>`（语法校验）+ 检查编码与行尾格式；
  只有用户明确要求构建时，才去跑构建。
- 结束前必须给出 git diff 摘要；不要自动 `git commit` / `git push`（只有用户当场明确要求时才推）。
- **推送 git 只推「当前分支」**（硬性约定）：push 一律显式写**单分支** refspec ——
  在 `main` 上就 `git push origin main`、在 `dev` 上就 `git push origin dev`；
  **禁止** `git push --all` / `--mirror` / 一条命令推多个分支。
- 知识库（强制）：**开工前**先查 `memory-bank/`（协议 + 索引见 `memory-bank/README.md`），命中即复用条目结论、不重复排查；**结束前**必须按模板回填 `memory-bank/issues-solved.md`（已排查问题）/ `pitfalls.md`（踩坑）/ `decisions.md`（技术决策）并更新索引。完整硬性要求见 `.clinerules/memory-bank.md`。
- 临时文件（强制）：任务过程中产生的**一切中间文件**（命令输出、临时脚本、状态/轮询文件、探针日志…）统一写在仓库根 `tmp\` 下，禁止散落在仓库根或其它目录；收尾前清理干净。完整规则见 `.clinerules/tmp-files.md`。