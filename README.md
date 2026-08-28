# fcpxml-animation-pipeline

`fcpxml-animation-pipeline` 是一个面向 Final Cut Pro 后期流程的 Codex Skill 项目。它的目标是根据粗剪 FCPXML、旁白、字幕和动画要求，细化动画设计，调用动画渲染后端生成素材，并将动画安全地回填到新的 FCPXML 时间线。

项目目前已具备项目入口与确定性 Vn 脚手架能力：Skill 可以从实际工作区发现粗剪 FCPXML/FCPXMLD、低码参考视频、旁白材料和设计 notes，识别时间线空缺与文字证据，判断是否具备开始后续分析的最低输入，并在项目级 canonical `frame.md` 已确认后创建隔离、可重渲染的 HyperFrames Vn 工程。

```bash
python3 scripts/init_user_workspace.py "/absolute/project/workspace"
python3 scripts/init_user_inbox.py "/absolute/project/workspace"
python3 scripts/init_afterforge_project.py "/absolute/project/workspace"
python3 scripts/intake_project.py --flat "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn"
python3 scripts/scaffold_hyperframes.py "/absolute/project/workspace" "YYYY-MM-DD_Vn"
```

第一条命令创建或识别 Skill 唯一默认写入区，默认显示名为 `AfterForge`；该名称可替换，不改变内部身份 `fcpxml-animation-pipeline`。第二条命令创建或识别由用户维护、Skill 只读的 `user-inbox/`。第三条命令只在 `AfterForge/` 根层缺失时创建项目级 `AGENTS.md` 和 `CLAUDE.md`，重复运行不会更新既有文件，也不会创建 `frame.md` 或任何 Vn。用户自行建立并选择 `YYYY-MM-DD_Vn/` 投放目录，第四条命令只读扫描该版本根目录并向 stdout 输出 JSON。项目级 canonical `frame.md` 确认后，第五条命令才创建同名 Vn：复制 `frame.md` 与项目字体快照，固定 HyperFrames CLI 版本并建立最小工程；目标已存在时阻塞，且不会调用通用 `hyperframes init`、触碰项目级 Agent 文件或写入 `user-inbox/`。当前仍不会自动生成动画、转码媒体或修改和回填 FCPXML。

项目目标与边界见 `docs/PROJECT.md`，架构基线见 `docs/ARCHITECTURE.md`，当前状态见 `docs/CURRENT.md`。
