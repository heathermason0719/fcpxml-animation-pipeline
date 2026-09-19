# AfterForge · FCPXML Animation Pipeline

用同一份制作源理解脚本、试做动画、接收反馈并生成可导入 Final Cut Pro 的透明动画包。以“电影系列 → 单集 → 制作版本 → 修改与交付”组织工作，支持文案起步和粗剪起步。

新版使用 manifest 3.0 / work model 2.1.0。新创作对象先确认真实 Storyboard，只有明确限定的 Motion 探索可以先行；已进入创作循环的对象可直接修改和局部试做。完整 Demo、完整 Review 批准与正式交付授权分别记录。改说明不重渲，改摆放复用动画媒体。旧 schema 2.0 工程原位只读展示，继续制作明确创建新副本，不继承旧授权。

## 使用

需要本地 Python、FFmpeg/ffprobe、Node/npm，以及明确版本的 HyperFrames。Python 依赖在 `requirements.txt`。依赖安装和 Skill 安装需单独授权；命令不会探测 latest 或自动迁移旧工程。

```bash
.venv/bin/python scripts/afterforge.py open "/workspace/AfterForge"
.venv/bin/python scripts/afterforge.py open "/workspace/AfterForge" --request-file /tmp/open.json
.venv/bin/python scripts/afterforge.py status "<version-root>"
.venv/bin/python scripts/afterforge.py update "<version-root>" --request-file /tmp/update.json
.venv/bin/python scripts/afterforge.py preview "<version-root>" --request-file /tmp/preview.json
.venv/bin/python scripts/serve_workflow_review.py "/workspace/AfterForge" --port 8765
.venv/bin/python scripts/afterforge.py deliver "<version-root>" --request-file /tmp/deliver.json
.venv/bin/python scripts/afterforge.py resume "<version-root>" --request-file /tmp/resume.json
```

CLI 与 Review 共用业务层；结构化写入使用 `requestId` 和 `expectedRevision`。相同请求重试去重，冲突保留原草稿和位置。CLI 返回生成的稳定 ID、版本根目录、状态与产物路径。

无粗剪起步的 open 请求：

```json
{"requestId":"episode-01","expectedRevision":0,"title":"电影系列","episodeTitle":"01 开场","brief":{"summary":"本集希望观众理解什么","segments":[]}}
```

绑定粗剪时增加用户明确选择的 `inputDirectory`；多个合理输入候选由 canonical `inputSelection: {fcpxml, reference_video}` 明确指定，兼容别名 `selections`。两个字段同时出现时，按该输入目录归一化后的完整选择必须相同，否则请求被拒绝；不按排名或字段优先级替用户选择。目前只支持单 Project sequence 输入。同一集新版本使用 `episodeId`；`copyFrom` 必须附用户明确跨版本委托的 `commission: {channel, text, reference}`，并明确 `copyMode: "restart"`，或为每个动画目标 Cue 提供 `objectContinuity`（`{kind:"new"}` 或 `{kind:"continue",sourceObjectId:"..."}`）。continue 仅承接首次资格的来源，不承接 Review、批准或 Demo 授权。`user-inbox/` 从不写入。源 FCPXML、参考视频与旁白材料在制作版内保存所需副本。

从旧工程创建副本时，仅继承视觉与运动默认；新副本会替换已知旧审核模板，并明确旧阶段文字不再是执行指令。原规范不改，旧规范路径和冻结哈希不进入新副本。新建版遇到已有系列默认时，明确传 `useSeriesDefaults: true|false`；采用时同时记录 `commission`。既有项目的 AGENTS/CLAUDE 和根层规范须在明确授权的衔接清理中同步，普通 open 不自动覆盖或迁移这些文件。

初次制作通过 `update` 的 `operation: "runtime", version: "X.Y.Z"` 初始化本地已缓存的精确 runtime。若该安装不包含 GSAP，可把现有本地 vendor 放到本版 `.staging/` 并传 `vendorSource`。缺少 runtime 时明确报错，不自动安装。静态 Cue 可以先建立；bootstrap 不产生 Motion 依据。`runtimeIdentity` 区分同指纹修复与实际变更，固定 vendor 也由 runtime writer 独占。

Agent 把代码和素材准备到 `.staging/`，用 `operation: "edit"` 的 `files: [{path, source}]` 与 `patch: {brief, cues, project}` 一次发布。无需手改 manifest、写连接脚本或维护阶段字段。具体源格式见 [制作源合同](references/hyperframes-single-source.md)。

静态请求为 `{"requestId":"board-1","expectedRevision":1,"scope":"storyboard","cueIds":["A"]}`，无需 Motion 源；静态 layout 不得包含可执行或随时间推进的内容。局部 Motion 指定 `workCueIds`（可兼容 `cueIds`）、`segmentIds` 或有理数 `range`。完整小样与必要重叠 Cue 的完整补充小样组成审阅集合。请求的呈现范围有缺失时默认拒绝；`allowDraft: true` 只能生成讨论稿，且在目标覆盖前不完成任务。明确排除可完成该次委托，但不能形成正式 full Review。

取得首次资格后，依据真实用户指令生成整版的请求示例：

```json
{"requestId":"demo-1","expectedRevision":3,"scope":"full","taskId":"task-1","workCueIds":["A"],"excludedCueIds":[],"decision":{"kind":"authorize-demo","taskId":"task-1","cueIds":["A"],"presentationCueIds":["A","D"],"excludedCueIds":[],"source":{"channel":"chat","text":"只改 A，D 不动，改完给整版","reference":"对应消息引用"}}}
```

这里 A 是创作范围，A 与 D 是呈现范围；D 可以复用有效媒体，缓存缺失时按原实现重建。`taskId` 覆盖任务内恢复和必要重算，不授权以后新的改版。

首次设计以真实、当前的 Storyboard snapshot 的明确 `storyboardIds` 确认；每个对象须有有效 board、非空最终动画说明和完整的 Cue 内容事实。`contentContext` 分别声明 `narration` 与 `screenText` 为 `present`、`none` 或 `unknown`：实际文本仍只来自既有 Cue、显式关联的段落或屏幕文字字段；`none` 必须有 `{text, reference}` 依据，`unknown` 不能被另一渠道的文字掩盖。`review-submit` 只提交反馈轮次，不能自动确认。确认请求可附带用户来源的 `feedbackResolutions: [{feedbackId, action:"accept"|"defer"|"withdraw"}]`，与确认原子完成。完整 Demo 需要稳定 `taskId` 的 `authorize-demo` 决定，并分别声明工作 Cue、时间范围、展示 Cue 与排除 Cue。候选视觉探索仅供比较；采用时通过范围明确的 `exploration-adopt` 事务更新 canonical cue。

合并批准与授权的交付请求：

```json
{"requestId":"deliver-1","expectedRevision":2,"decision":{"kind":"approve-and-deliver","reviewSetId":"<当前集合ID>","source":{"channel":"chat","text":"用户明确要求批准并制作这版交付的原话","reference":"对应消息引用"}}}
```

示例中的 revision、ID 与原话必须来自真实当前状态和用户决定。只认可画面时记录 approve，之后可以 authorize；不得用示例文字制造授权。恢复任务传 `jobId` 和当前 revision。

## 文件与交付

```text
AfterForge/
├── AGENTS.md, CLAUDE.md
├── 交付/<集名--ID>/交付0001/<集名>.fcpxmld
└── 工程/
    ├── project.json, 创作记忆.md, frame.md
    └── episodes/<episodeId>/<versionId>/
        ├── animation-manifest.json, compositions/, assets/
        ├── previews/, cache/, jobs/
        └── releases/
```

页面保留通用 shell 的脚本思路、Storyboard、可选视觉探索、Demo 与交付入口；Storyboard 同页呈现旁白、主审／辅助帧、最终动画说明和就地反馈。提交本轮反馈只交棒，设计确认独立操作；反馈目标由同一解析器用于确认、批准与交付。未采用的探索候选评论不会阻塞 canonical 成果，采用时才按冻结的候选 revision、内容身份与对象范围参与核验。支持从当前版本内容导出 Markdown 脚本、局部时间定位、多 Cue 评论、版本对照与独立 MOV 下载。480p 预览保留原粗剪声音；正式交付为源帧率 1920×1080 ProRes 4444。包内仅 Info.fcpxml 与 MOV，源时间线不改。

快照记录实际依赖、已批准审阅和完整素材。相同输入复用经核验包；草稿继续修改不会覆盖历史包，也不必等待旧包 FCP 验收。实际导入用 `update operation: "decision", kind: "accept-import"` 记录；首次协议 2 的 FCP re-export 用 `operation: "roundtrip"` 验证并建立基线。自动测试不代替实际 FCP 验收。

## 开发验证

首次依赖设置经授权后执行 `python3 -m venv .venv` 和 `.venv/bin/python -m pip install -r requirements.txt`。常规检查：

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
.venv/bin/python scripts/sync_workflow_stage_contract.py --check
```

另有显式、隔离的真实一分钟样片回归；使用合成媒体与已有本地中文字体，输出目录不得已存在：

```bash
.venv/bin/python -B tests/work_model_real_smoke.py --run --root /private/tmp/afterforge-real-check --runtime 0.8.33 --gsap-source /absolute/local/gsap.min.js --font-source /absolute/local/chinese.woff2
```

不修改已交付《楚门》工程，不默认 commit、push、安装、迁移或 FCP 导入。事故恢复与正式 Storyboard 基线的隔离命令见 [CURRENT](docs/CURRENT.md)；协议 2 实际 FCP 往返仍需另行验证。

开发约束见 [AGENTS.md](AGENTS.md)，项目边界见 [PROJECT](docs/PROJECT.md)，可靠状态见 [CURRENT](docs/CURRENT.md)，接口与实现见 [ARCHITECTURE](docs/ARCHITECTURE.md)，决策适用范围见 [DECISIONS](docs/DECISIONS.md)。
