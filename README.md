# fcpxml-animation-pipeline

`fcpxml-animation-pipeline` 是一个面向 Final Cut Pro 后期流程的 Codex Skill 项目。它的目标是根据粗剪 FCPXML、旁白、字幕和动画要求，细化动画设计，调用动画渲染后端生成素材，并将动画安全地回填到新的 FCPXML 时间线。

项目目前已具备项目入口、确定性 Vn 脚手架、HyperFrames 单一布局源 adapter 和 FCPXML 交付后端：Skill 可以发现粗剪输入并建立隔离 Vn；A11 storyboard review 与 A12 正式合成共同引用同一 cue composition；正式透明 MOV 验证后可注册进 manifest，并生成包含完整原 Project 副本与独立 connected clips 的扁平 `.fcpxmld`。

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
python3 scripts/register_delivery_assets.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/build_delivery_package.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
```

前五条命令维持原有项目入口与 Vn 创建边界。后续命令从 manifest v2 生成 A11/A12 的 854×480 review projection、验证 projection-aware layout lock、生成逐 cue 的 1920×1080 delivery host，并在用户批准后原生渲染透明 ProRes 4444。`register_delivery_assets.py` 重新探测实际 MOV 并把稳定媒体属性注册进主 manifest；`build_delivery_package.py` 使用源 FCPXML、有理数时间、唯一 `deliveryProtocolVersion` 和已注册资产构建、DTD 校验并原子发布根层扁平包，相同 fingerprint 只在完整校验通过后复用。

每条动画的正式 DOM/CSS 只存在于 `compositions/cues/`，运动位于 `compositions/motion/`；`compositions/review/`、`compositions/delivery/`、`STORYBOARD.md` 和 `index.html` 均为生成视图。交付包不会直接修改 Final Cut Pro Library；首次导入后，可将 FCP 再导出的 XML 交给 `compare_fcpxml_roundtrip.py` 与原交付 XML 做语义回归。当前仍不会自动完成初始内容理解或语音转写。

项目目标与边界见 `docs/PROJECT.md`，架构基线见 `docs/ARCHITECTURE.md`，当前状态见 `docs/CURRENT.md`。
