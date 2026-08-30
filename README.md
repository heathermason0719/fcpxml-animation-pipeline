# fcpxml-animation-pipeline

`fcpxml-animation-pipeline` 是一个面向 Final Cut Pro 后期流程的 Codex Skill 项目。它的目标是根据粗剪 FCPXML、旁白、字幕和动画要求，细化动画设计，调用动画渲染后端生成素材，并将动画安全地回填到新的 FCPXML 时间线。

项目目前已具备项目入口、确定性 Vn 脚手架和 HyperFrames 单一布局源 adapter：Skill 可以发现粗剪输入并建立隔离 Vn；A11 storyboard review 与 A12 正式合成共同引用同一 cue composition，运动独立保存，生成视图不再维护第二套布局。

```bash
python3 scripts/init_user_workspace.py "/absolute/project/workspace"
python3 scripts/init_user_inbox.py "/absolute/project/workspace"
python3 scripts/init_afterforge_project.py "/absolute/project/workspace"
python3 scripts/intake_project.py --flat "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn"
python3 scripts/scaffold_hyperframes.py "/absolute/project/workspace" "YYYY-MM-DD_Vn"
python3 scripts/sync_storyboard.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/layout_lock.py verify "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/assemble_hyperframes.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/sync_delivery.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/validate_hyperframes_adapter.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/render_animations.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
```

前五条命令维持原有项目入口与 Vn 创建边界。后续命令从 manifest v2 生成 A11/A12 的 854×480 review projection、验证 projection-aware layout lock、生成逐 cue 的 1920×1080 delivery host，并在用户批准后原生渲染透明 ProRes 4444。每条动画的正式 DOM/CSS 只存在于 `compositions/cues/`，运动位于 `compositions/motion/`；`compositions/review/`、`compositions/delivery/`、`STORYBOARD.md` 和 `index.html` 均为生成视图。当前仍不会自动完成初始内容理解或 FCPXML 回填。

项目目标与边界见 `docs/PROJECT.md`，架构基线见 `docs/ARCHITECTURE.md`，当前状态见 `docs/CURRENT.md`。
