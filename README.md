# AfterForge · FCPXML Animation Pipeline

用同一份制作源理解脚本、试做动画、接收反馈并生成可导入 Final Cut Pro 的透明动画包。以“电影系列 → 单集 → 制作版本 → 修改与交付”组织工作，支持文案起步和粗剪起步。

新版使用 manifest 3.0 / work model 2.2.0。每条动画先生成或导入真实概念图，确认视觉方向后进入代码制作，再检查实际 Storyboard 与动画；已确认对象可直接按普通制作反馈修改和局部试做。完整 Demo、完整 Review 批准与正式交付授权分别记录。改说明不重渲，改摆放复用动画媒体。旧 schema 2.0 工程原位只读展示，继续制作明确创建新副本，不继承旧授权。

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

绑定粗剪时增加用户明确选择的 `inputDirectory`；多个合理输入候选由 canonical `inputSelection: {fcpxml, reference_video}` 明确指定，兼容别名 `selections`。两个字段同时出现时，按该输入目录归一化后的完整选择必须相同，否则请求被拒绝；不按排名或字段优先级替用户选择。目前只支持单 Project sequence 输入。同一集新版本使用 `episodeId`；`copyFrom` 必须附用户明确跨版本委托的 `commission: {channel, text, reference}`，并明确 `copyMode: "restart"`，或为每个动画目标 Cue 提供 `objectContinuity`（`{kind:"new"}` 或 `{kind:"continue",sourceObjectId:"..."}`）。continue 仅承接历史资格来源，新 2.2 版仍须自己的概念确认，不承接 Review、批准或 Demo 授权。`user-inbox/` 从不写入。源 FCPXML、参考视频与旁白材料在制作版内保存所需副本。

新创作以内容和确认概念为依据，不沿用过去妥协形成的审美默认；保留叙事、可读性及字体兼容经验，一次通过不自动成为长期偏好。旧默认不适用时 fresh open 明确用 `useSeriesDefaults: false`，不改历史版本。

从旧工程创建副本时，仅继承视觉与运动默认；新副本会替换已知旧审核模板，并明确旧阶段文字不再是执行指令。原规范不改，旧规范路径和冻结哈希不进入新副本。新建版遇到已有系列默认时，明确传 `useSeriesDefaults: true|false`；采用时同时记录 `commission`。既有项目的 AGENTS/CLAUDE 和根层规范须在明确授权的衔接清理中同步，普通 open 不自动覆盖或迁移这些文件。

新制作可使用已验证的精确 runtime 0.8.146，历史 pin 保持。初次制作通过 `update` 的 `operation: "runtime", version: "X.Y.Z"` 初始化本地已缓存的精确 runtime。若该安装不包含 GSAP，可把现有本地 vendor 放到本版 `.staging/` 并传 `vendorSource`。缺少 runtime 时明确报错，不自动安装。静态 Cue 可以先建立；bootstrap 不产生 Motion 依据。`runtimeIdentity` 区分同指纹修复与实际变更，固定 vendor 也由 runtime writer 独占。

确认概念方向后，Agent 把代码和素材准备到 `.staging/`，用 `operation: "edit"` 的 `files: [{path, source}]` 与 `patch: {brief, cues, project}` 一次发布。无需手改 manifest、写连接脚本或维护阶段字段。具体源格式见 [制作源合同](references/hyperframes-single-source.md)。

静态请求为 `{"requestId":"board-1","expectedRevision":1,"scope":"storyboard","cueIds":["A"]}`，无需 Motion 源；静态 layout 不得包含可执行或随时间推进的内容。局部 Motion 指定 `workCueIds`（可兼容 `cueIds`）、`segmentIds` 或有理数 `range`。完整小样与必要重叠 Cue 的完整补充小样组成审阅集合。请求的呈现范围有缺失时默认拒绝；`allowDraft: true` 只能生成讨论稿，且在目标覆盖前不完成任务。明确排除可完成该次委托，但不能形成正式 full Review。

Cue 总体说明继续使用 `finalAnimationDescription`，局部说明写在 `storyboard.animationNotes: [{id, frameIds, text}]`。一条可关联多帧，多条可共享帧；帧增删或重排时同步维护引用。纯说明修改后仍通过 Storyboard 预览发布新审阅快照：核验输入和 SHA 后复用 PNG，保留旧快照及反馈，旧快照不能确认新内容。后台 `hero` 规则不变，页面统一呈现静帧。

本版临时要求通过 `update operation: "working-intent"` 保存，使用 `upserts` 和 `removeIds` 定向更新。每条含 `id`、`kind: "focus"|"preserve"`、`text`、`locator` 与真实用户 `source`；更新时间由接口填写。`status.workingIntent.items` 供跨会话恢复，页面只读显示“本轮重点／暂时保持”。它不提供批准或制作资格，不改变渲染、审阅与交付判断，也不自动继承到新版本。完整接口见 [制作源合同](references/hyperframes-single-source.md)。

取得首次资格后，依据真实用户指令生成整版的请求示例：

```json
{"requestId":"demo-1","expectedRevision":3,"scope":"full","taskId":"task-1","workCueIds":["A"],"excludedCueIds":[],"decision":{"kind":"authorize-demo","taskId":"task-1","cueIds":["A"],"presentationCueIds":["A","D"],"excludedCueIds":[],"source":{"channel":"chat","text":"只改 A，D 不动，改完给整版","reference":"对应消息引用"}}}
```

这里 A 是创作范围，A 与 D 是呈现范围；D 可以复用有效媒体，缓存缺失时按原实现重建。`taskId` 覆盖任务内恢复和必要重算，不授权以后新的改版。

新 work model 2.2 的“脚本与思路”页先展示每条动画的真实概念图、对应文字、创意和运动说明，以桌面每行三张的卡片浏览（窄窗口降为两张或一张），点图放大后可用两侧箭头或键盘左右键查看当前 Cue 的其他候选，首尾停止；说明按需展开，支持历史候选与批量确认，顶部列出未确认 Cue 及原因。迭代过程图也保留在历史候选中，可逐稿留言，不改变已选方案。默认用 Codex 可用的图像生成能力；用户从其他模型带来的图片同等接入。未确认可自由改稿和推荐，上传本身不算采用；明确的聊天采用可直接登记，无需网页重复确认。确认后才发布静态／运动代码或代码型探索、生成实际 Storyboard 与动画。Storyboard 检查制作结果，不再承担第二次首次设计确认。顶部「通过并开始制作动画」可勾选本轮制作范围，存在暂缓意见的 Cue 默认不选；提交后持久显示交棒状态，回到对话让 Agent 继续制作，完成后在 Demo 审阅。只有用户明确要求修改概念图才开启新确认轮次，普通制作反馈沿用确认。

概念图制作先向图像模型说明视频情境、准确内容、参考图用途和时间中的呈现关系，保留可发挥的设计空间。Agent 看图后主动筛选并多轮修改，方向错误时回到原始素材重起，再提交值得比较的候选；用户无需逐张指导修复。多方案分别解决同一视频需求，以表达和编排的实质差异供选择，不固定生成数量或默认审美。方法见 [概念图设计参考](references/visual-grammar.md)，实际运动在采用后的制作中验证。

`update operation: "concept", action: "register"` 从本版 `.staging/` 接收实际 PNG/JPEG/单帧 WebP，保存到受控资产目录；`decision kind: "confirm-concept", conceptIds` 可批量确认。明确提供并采用可用 `register` 的 `adopt: true` 加真实用户 `source` 原子完成。概念图和原稿反馈永久对应，不能用新图替换旧记录。内容事实仍分别声明 narration/screenText 的 `present`、`none` 或 `unknown`，明确无内容需有依据，未知不能靠另一渠道掩盖。确认可携带有用户来源的 `feedbackResolutions`。完整 Demo 的 taskId、工作／时间／展示范围及独立批准规则不变。概念接口示例见 [制作源合同](references/hyperframes-single-source.md)。历史 2.1 版本保留原 Storyboard 确认语义，新版不从历史资格推断概念确认。

合并批准与授权的交付请求：

```json
{"requestId":"deliver-1","expectedRevision":2,"decision":{"kind":"approve-and-deliver","reviewSetId":"<当前集合ID>","source":{"channel":"chat","text":"用户明确要求批准并制作这版交付的原话","reference":"对应消息引用"}}}
```

示例中的 revision、ID 与原话必须来自真实当前状态和用户决定。只认可画面时记录 approve，之后可以 authorize；不得用示例文字制造授权。恢复任务传 `jobId` 和当前 revision。

## 文件与交付

<!-- delivery-contract:start -->
当前正式交付协议：3。
目录：`AfterForge/交付/{episode}-D{number}/`。
XML：`{episode}-D{number}.fcpxml`，与当前 XML 使用的全部 AfterForge 动画 MOV 同级。
同一 SHA-256 只保存一个物理媒体实体；正式版本间可硬链接。内部仅保留元数据和 XML 证据。
<!-- delivery-contract:end -->

```text
AfterForge/
├── AGENTS.md, CLAUDE.md
├── 交付/<集名>-D0001/
│   ├── <集名>-D0001.fcpxml
│   └── *.mov                       # XML 使用的全部 AfterForge 动画
└── 工程/
    ├── project.json, 创作记忆.md, frame.md
    └── episodes/<episodeId>/<versionId>/
        ├── animation-manifest.json, compositions/, assets/
        ├── previews/, cache/, jobs/
        └── releases/
```

页面保留通用 shell 的脚本思路、Storyboard、可选视觉探索、Demo 与交付入口；Storyboard 同页呈现旁白、Cue 总体说明、三列等尺寸静帧（窄屏两列）与局部动画说明。局部说明只显示一次，位于关联的最后一帧下；点击对应帧编号高亮关联图片，不改变留言目标。点击图片可放大，Esc 关闭。留言框默认展开，按版本、创意对象与稳定帧 ID 记住开合；桌面反馈栏随滚动保持可见。顶部保留单集、制作版、历史版及 Cue 导航。提交本轮反馈只交棒，设计确认独立操作；反馈目标由同一解析器用于确认、批准与交付。未采用的探索候选评论不会阻塞 canonical 成果，采用时才按冻结的候选 revision、内容身份与对象范围参与核验。支持从当前版本内容导出 Markdown 脚本、局部时间定位、多 Cue 评论、版本对照与独立 MOV 下载。Demo 默认展示最新完整视频，动画 Cue 导览只跳转播放位置；静帧不混入视频列表，其他视频与以往意见折叠。视频下方保存单条意见，「取当前播放时间」暂停并定位反馈；文本输入区以外的空格控制播放／暂停。「提交本轮反馈」将当前完整 Demo 的已保存意见交棒，不批准效果；「本版效果通过」只批准当前完整 Review，之后才显示交付操作，仍需单独授权。480p 预览保留原粗剪声音，采用 H.264 CRF 23、3 Mbps 峰值约束、6 Mb 缓冲、约两秒关键帧与 MP4 faststart；不使用无损 H.264，整版、局部与补充 Cue 视频共用此设置。仅编码变化且内容输入指纹相同的当前预览，继续展示既有反馈而不改写反馈绑定；正式交付为源帧率 1920×1080 ProRes 4444。正式目录中仅同级普通 XML 与 MOV，源时间线不改。

请先把该目录内**全部 MOV** 导入并管理到 FCP Library，再导入同目录 XML；历史沿用动画也已包含在这一批媒体中。内部 `releases/dNNNN/` 仅留冻结 manifest、必要源 XML、依赖哈希、验证清单与批准关联，不复制 MOV、字体、插画、Demo 或粗剪。正式目录是媒体权威；相同内容只用普通硬链接，失败即拒绝，不退回复制。AfterForge 内的受保护历史路径也参与唯一性核验；用户管理到 FCP Library 的副本不计入此范围。

后端从实际资源图解析全部动画，包含嵌套和历史复用；以登记来源与实际哈希确认归属，未知 AfterForge 资产阻止发布。XML、冻结媒体清单和目录必须一致；原始输入只读，输出移除动画旧 bookmark、替代媒体定位，使用同级相对引用。生成、发布、重试、已完成任务返回及恢复均核验；当前协议无跳过检查或降级参数。协议 1/2 仅历史读取/验证与明确迁移；旧 `build_delivery_package` 不再生产新包。

相同输入复用已验证正式交付，草稿继续修改不覆盖旧版。实际导入用 `update operation: "decision", kind: "accept-import"` 记录；协议 3 首次真实 FCP re-export 用 `operation: "roundtrip"` 验证全部正式动画媒体并建立基线。自动测试不代替实际 FCP 验收。一次性旧工程清理需独立固定清单与明确授权，不提供长期 storage/retention 管理功能。

回导允许经核实的 FCP 1.14 Basic Title 颜色空间转换和默认选择器省略，并逐项保存依据；实际文字、字体、对齐、媒体及时间变化仍会拒绝。颜色转换由 macOS 自带 ColorSync 核验，无须安装额外依赖；缺少校验环境时明确失败，不静默忽略差异。

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

不修改已交付《楚门》工程，不默认 commit、push、安装、迁移或 FCP 导入。事故恢复与正式 Storyboard 基线的隔离命令见 [CURRENT](docs/CURRENT.md)；协议 3 实际 FCP 往返结果见 [CURRENT](docs/CURRENT.md)，与自动测试证据分别记录。

开发约束见 [AGENTS.md](AGENTS.md)，项目边界见 [PROJECT](docs/PROJECT.md)，可靠状态见 [CURRENT](docs/CURRENT.md)，接口与实现见 [ARCHITECTURE](docs/ARCHITECTURE.md)，决策适用范围见 [DECISIONS](docs/DECISIONS.md)。
