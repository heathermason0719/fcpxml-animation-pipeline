# fcpxml-animation-pipeline

`fcpxml-animation-pipeline` 是一个面向 Final Cut Pro 后期流程的 Codex Skill 项目。它的目标是根据粗剪 FCPXML、旁白、字幕和动画要求，细化动画设计，调用动画渲染后端生成素材，并将动画安全地回填到新的 FCPXML 时间线。

项目目前已具备第一阶段的项目入口能力：Skill 可以从实际工作区发现粗剪 FCPXML/FCPXMLD、低码参考视频、旁白材料和设计 notes，识别时间线空缺与文字证据，并判断是否具备开始后续分析的最低输入。

```bash
python3 scripts/init_user_workspace.py "/absolute/project/workspace"
python3 scripts/init_user_inbox.py "/absolute/project/workspace"
python3 scripts/intake_project.py --flat "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn"
```

第一条命令创建或识别 Skill 唯一默认写入区，默认显示名为 `AfterForge`；该名称可替换，不改变内部身份 `fcpxml-animation-pipeline`。第二条命令创建或识别由用户维护、Skill 只读的 `user-inbox/`。用户自行建立并选择 `YYYY-MM-DD_Vn/` 版本目录，第三条命令只读扫描该版本根目录并向 stdout 输出 JSON。本阶段不自动创建版本、不生成动画，也不修改或回填 FCPXML。

项目目标与边界见 `docs/PROJECT.md`，架构基线见 `docs/ARCHITECTURE.md`，当前状态见 `docs/CURRENT.md`。
