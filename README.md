# fcpxml-animation-pipeline

`fcpxml-animation-pipeline` 是一个面向 Final Cut Pro 后期流程的 Codex Skill 项目。它的目标是根据粗剪 FCPXML、旁白、字幕和动画要求，细化动画设计，调用动画渲染后端生成素材，并将动画安全地回填到新的 FCPXML 时间线。

项目目前已具备项目入口、可选动画脚本审核、确定性 Vn 脚手架、HyperFrames 单一布局源 adapter、统一 Stage Contract、单 Vn Review 与 FCPXML 交付后端。Storyboard、480p Demo、独立原生渲染授权和 D1–D6 交付证据由 resolver 串联，不以文件存在或手工维护的 `currentStage` 代替当前完成语义。

首次使用先在仓库的隔离 Python 环境安装依赖；后续命令在激活该环境后运行。`jsonschema` 是 Review 写入的必需校验依赖，不能缺失时跳过校验。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
source .venv/bin/activate
```

```bash
python3 scripts/init_user_workspace.py "/absolute/project/workspace"
python3 scripts/init_user_inbox.py "/absolute/project/workspace"
python3 scripts/init_afterforge_project.py "/absolute/project/workspace"
python3 scripts/intake_project.py --flat "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn"
python3 scripts/scaffold_hyperframes.py "/absolute/project/workspace" "YYYY-MM-DD_Vn"
python3 scripts/migrate_hyperframes_runtime.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn" "X.Y.Z"
python3 scripts/sync_storyboard.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/layout_lock.py verify "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/assemble_hyperframes.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/sync_delivery.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/validate_hyperframes_adapter.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/workflow_status.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/serve_workflow_review.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/render_animations.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/register_delivery_assets.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/build_delivery_package.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
```

上述 `YYYY-MM-DD_Vn` 是命令示例；版本标记同时接受大写 `V` 和小写 `v`。脚手架原样保留用户选定的拼写，并在发现仅大小写不同的既有版本时阻塞，避免跨文件系统产生版本身份碰撞。新 Vn 在创建时解析官方当前 HyperFrames 版本并立刻固定为精确 pin，也可由调用方显式指定精确版本；创建前兼容性检查失败时不发布 Vn。已有 Vn 始终使用自己的 pin，不因官方发布新版自动变化；升级必须通过显式迁移命令完成，并记录实际检查和审核 evidence 的保留、重绑或失效。

前五条命令维持原有项目入口与 Vn 创建边界。A-stage 与 D-stage 的唯一机器定义见 `references/workflow-stage-contract.json`，完整可读表由它确定性生成到 `references/workflow-stage-contract.md`。仓库级 Review shell 绑定单个 Vn：Storyboard 在对应旁白和主审帧/必要辅助帧之后，直接投影 cue 级 `finalAnimationDescription`，再于当前静帧上下文记录 A11 comment 与逐 cue 批准。初始设计或后续 Review / 聊天反馈若仍支持会实质改变最终呈现的多种合理解释，Agent 会在修改受影响 cue 前提出一个聚焦问题；明确结果内的实现细节不重复询问，澄清不新增批准门，也不把过程写进最终动画说明。提交 comment 会撤销相应批准并保留被评论的锁定静帧作为待修改版本，只有受审文件实际变化才使 layout lock 失效。缺少最终动画说明、锁定审核帧失效或仍有开放 comment 时不能批准。Demo 自动绑定播放器时间；该时刻只有一个 active cue 时自动关联，存在多个重叠 cue 时列出全部候选且不预选，必须由用户明确选择后才能提交。一条 comment 可由用户标记为影响 static、motion 或二者；A14 独立授权仍是单独操作。所有状态写回 manifest，renderer、注册器和包构建器按 resolver 的证据链 fail closed。

Demo 支持直接拖动播放条。右上角“刷新”重新读取审核状态并显示成功时间或失败原因；视频未变化时保留播放位置，已登记的 Demo 哈希变化时才切换到新视频，不会把刷新当作批准或推进流程。

并发冲突或网络失败后，当前页面会话保留未提交的静帧与 Demo 草稿；刷新若发现审核对象已变化，需要用户确认重新绑定，不能把旧意见静默挂到新画面。此处不保证关闭页面或浏览器整页重载后的草稿恢复。旧逐镜批准失效后，只要当前静帧、说明和 comment 满足门槛即可重新批准；未受影响镜头的批准继续保留。

当前执行输入使用 `inputFingerprintVersion=2`，覆盖动画时间位置、时长、叠层顺序和精确帧率等语义。它不是 HyperFrames 版本号。旧指纹按原语义保留历史事实；新的 A13/A14 写入以及 D2–D4 生产写入须重新建立当前输入证据，A11 仍由逐 cue layout lock 与批准 predicate 约束。已完成的旧 Vn 不会被自动重开。同指纹交付包通过完整验证且已登记时，只读复用，不覆盖既有 FCP 验收或 round-trip 状态。

每条动画的正式 DOM/CSS 只存在于 `compositions/cues/`，运动位于 `compositions/motion/`；`compositions/review/`、`compositions/delivery/`、`STORYBOARD.md` 和 `index.html` 均为生成视图。交付包不会直接修改 Final Cut Pro Library；首次导入后，可将 FCP 再导出的 XML 交给 `compare_fcpxml_roundtrip.py` 与原交付 XML 做语义回归。当前仍不会自动完成初始内容理解或语音转写。

需要规范填写动画要求时，可按需使用仓库内的 `assets/animation-script-template.docx`；它不会自动复制进项目，也不是 intake 必填材料。用户填好后自行放入当前 `user-inbox/YYYY-MM-DD_Vn/`，自由格式脚本仍然受支持。

项目级 `frame.md` 和视频级运动气质为各 cue 提供默认风格；动画脚本若对单条镜头明确指定视觉或运动风格，该逐镜要求在其明确范围内优先，未指定部分仍继承项目默认。逐镜要求不会覆盖 FCPXML 时间权威、AfterForge 范围、读写边界、交付协议或渲染后端能力限制。

新制作默认采用流畅、可读、缓入缓停可感知且便于后续剪辑的运动；时长与余量按镜头设计，不固定秒数或退场比例，有叙事用途的持续运动不受“不漂浮”一刀切限制。详细执行规则见 `SKILL.md`；项目默认更新不改写既有 Vn 快照与批准，也不代表已实现素材子区间摆放。

当某条动画需要把两段或以上原片重新排列、回放、裁切、遮罩或组成多画面时，A7 默认要求用户提供独立且带充足余量的片段，不从粗剪中猜测精确取段与顺序。文件名使用 `01-`、`02-` 等顺序前缀，或保留 `animation-source`、“动画素材”关键词，即可与粗剪参考视频确定性分流。此类输入默认接受 1920×1080 H.264、匹配项目的恒定帧率与 Rec.709 SDR；ProRes 和 4K 只在大幅放大裁切、抠像或重度影像处理时按需索取。该规则是 cue 级素材门槛，不会把独立原片升级为全局 intake 必填项。

素材身份和选择以用户最新明确说明，以及实际投放文件的名称、编号顺序和可检查画面为权威。脚本中列出的“用户提供素材类型”只是规划参考；实际文件与用户说明相互一致时，即使与脚本举例不同，也作为 `agent-normalized` 直接继续。该权威关系只适用于素材身份与选段，不改变脚本对逐镜风格、运动和表达目的的明确要求。

项目目标与边界见 `docs/PROJECT.md`，架构基线见 `docs/ARCHITECTURE.md`，当前状态见 `docs/CURRENT.md`。
