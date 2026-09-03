# 架构基线

## 文档职责

本文档定义 `fcpxml-animation-pipeline` 的长期架构基线：系统分层、组件职责、核心数据流、V1 输入输出、渲染后端边界和 FCPXML 回填边界。后续实现可以细化内部技术方案，但不得在未更新 `docs/PROJECT.md` 和 `docs/DECISIONS.md` 的情况下改变这里确定的核心设计。

本文档不记录开发进度；当前实现状态以 `docs/CURRENT.md` 为准。

## Workflow 生命周期与 Stage Contract

完整 invocation 由连续的 A-stage（分析、创意审核与授权）和 D-stage（工程交付）组成；A14 的用户授权完成后，D1 重新验证当前输入和全部门禁，D2 才能启动正式渲染。Stage ID、正式名称、稳定职责和版本兼容关系只由 `references/workflow-stage-contract.json` 定义；`references/workflow-stage-contract.md` 是确定性生成的人类视图，本文不复制完整阶段表。

单个 Vn 的 manifest 只保存 `stageContractVersion` 和实例 evidence。`workflow_status.py` 根据实际锁、文件哈希、comment、用户批准、授权、render ledger、注册资产和发布包推导 `activeContext`、`blockingStage`、`nextEligibleStage` 与 `completedStages`，不保存需要各工具同步的 `currentStage`。旧 contract version 的合法 evidence 保留为历史事实；只有被 registry 明确声明语义兼容时才能用于当前判断，未知、损坏或当前语义不兼容的 evidence 不可作为当前完成依据。

## 总体架构

项目采用“Codex Skill + 确定性脚本工具链”的结构。Skill 负责需要理解语义、上下文和创作意图的判断；脚本负责必须稳定、可重复、可校验的机械操作。二者通过 `animation-manifest.json` 解耦。

```text
实际项目工作区
├── user-inbox/（用户维护，Skill 只读）
│   └── YYYY-MM-DD_Vn/（用户创建和选择，材料平铺）
│       ├── 必要：rough-cut.fcpxml / .fcpxmld
│       ├── 必要：低码粗剪参考视频
│       ├── 可替代旁白证据：SRT、时间线字幕、转写稿或已有文字稿
│       └── 可选设计约束：动画脚本、Marker、时间线文字、notes
└── AfterForge/（Skill 维护，唯一默认写入区；显示名可替换）
    ├── AGENTS.md（项目级 Agent 规则，只在项目初始化时创建）
    ├── CLAUDE.md（项目级 Claude 入口，只在项目初始化时创建）
    ├── frame.md（当前视频项目视觉规范的 canonical source）
    ├── AfterForge__<sourceVersion>__d-<fingerprint>.fcpxmld/（正式扁平交付包）
    │   ├── Info.fcpxml
    │   └── AF__<stableCueId>__<semanticSlug>.mov
    └── YYYY-MM-DD_Vn/（本版可独立重渲染的 HyperFrames 工程与内部交付资产）
        ├── animation-manifest.json
        ├── frame.md（本版构建时快照）
        ├── STORYBOARD.md
        ├── package.json
        ├── hyperframes.json
        ├── meta.json
        ├── index.html
        ├── compositions/
        │   ├── cues/（正式 DOM、布局与 CSS 唯一源）
        │   ├── motion/（独立运动时间线）
        │   ├── review/（自动生成 854×480 A11 projection）
        │   └── delivery/（自动生成 1920×1080 单 cue render host）
        ├── approvals/a11/（批准 hero poster）
        ├── assets/
        ├── previews/*.mp4
        └── delivery/
            ├── prores4444/*.mov（canonical 正式渲染资产）
            └── render-ledger.json（渲染执行证据）
```

`fcpxml-animation-pipeline` Skill 负责分析时间线、对齐旁白与动画要求、细化设计、生成 manifest、调用 HyperFrames、转码透明动画、回填新的 FCPXML 和执行完整性检查。项目级长期资产与 Vn 版本资产物理分层，不能把通用脚手架文件误计为每版创作成果。

## Skill 与 scripts 分工

### Skill 负责创作性判断与流程编排

`SKILL.md` 负责指导 Agent：

- 理解口播内容及其表达目的；
- 结合字幕和粗略动画要求细化画面表现；
- 在 A7 审核用户主动提供的动画脚本是否能与口播、原画、FCPXML 时间线、当前范围和制作后端可靠衔接；
- 判断哪些位置保留电影原片，哪些位置使用文字动画、图形演示或其他视觉辅助；
- 统一动画节奏、信息层级和视觉风格；
- 在信息不足或无法可靠对齐时生成明确的人工确认项；
- 决定何时先输出动画清单或低分辨率预览供用户确认；
- 按既定顺序调用确定性脚本，并根据验证结果决定是否继续。

Skill 不自行承担 FCPXML 时间运算、XML 拼装、媒体转码或文件完整性校验。

### 第一阶段项目入口

Skill 首先接收用户的实际项目工作区路径，依次创建或识别 `AfterForge/` 和 `user-inbox/`，再对用户明确指定的投放版本目录调用 `scripts/intake_project.py` 执行只读扫描。

用户工作目录初始化器遵守以下边界：

- 默认显示名为 `AfterForge`，可通过参数替换；
- 内部 `skill_id` 始终为 `fcpxml-animation-pipeline`，显示名不进入既有业务协议；
- 目标不存在时只创建该目录，不在其中预建文件或子目录；
- 目标目录已存在时原样复用，不修改其内容；
- 同名路径是文件或符号链接时阻塞，不覆盖、不跟随；
- 本阶段真实项目中除该目录外不允许其他写入。

上述目录初始化只负责建立 `AfterForge/` 门牌和读写边界。后续的一次性 AfterForge 视频项目初始化是独立步骤，只在项目尚未初始化时于根层创建项目级 `AGENTS.md` 和 `CLAUDE.md`；两者已存在时必须原样保留，不得因创建新 Vn、普通制作、HyperFrames CLI 或 skills 升级而重写。`CLAUDE.md` 创建后不进入日常同步维护，只有未来实际使用 Claude Code 且用户明确要求时，才依据届时规则更新。

Vn 版本创建与项目初始化完全解耦。Vn 由仓库控制的确定性 HyperFrames 适配脚手架创建，不以每版执行通用 `hyperframes init` 为前提。版本标记接受大写 `V` 或小写 `v`；输入拼写作为本轮版本身份原样保存，脚手架发现仅大小写不同的既有条目时必须阻塞，不得创建、合并或隐式规范化。版本脚手架只写入新 Vn 目录，目标已存在时阻塞，不得触碰 AfterForge 根层的 `AGENTS.md`、`CLAUDE.md` 或 canonical `frame.md`。脚手架在创建瞬间解析官方当前 HyperFrames 版本，或接受调用方显式给出的精确版本，并在临时 Vn 通过兼容性检查后把该精确版本固定进所有 managed package scripts；解析或检查失败时不发布目标，也不回退到仓库硬编码默认值。HyperFrames skills 的安装或升级仍属于机器环境维护，不由项目初始化或 Vn 创建隐式触发。

`user-inbox/` 初始化器遵守以下边界：

- 只创建或识别项目根目录下的 `user-inbox/` 顶层目录；
- 已存在时原样复用，不修改其中任何版本目录或材料；
- 同名路径是文件或符号链接时阻塞，不覆盖、不跟随；
- 不创建 V1，不递增版本号，不选择“最新版本”，不执行其他版本管理；
- `YYYY-MM-DD_Vn/` 或 `YYYY-MM-DD_vn/` 由用户创建、选择和维护，其材料直接放在版本目录根层；
- intake 对版本目录使用 `--flat`，只读取根层材料；原有递归模式保持不变，避免既有调用回归；
- Skill 对 `user-inbox/` 全树只读，所有工作产物仍只能默认写入 `AfterForge/`。

随后，intake 工具负责：

- 自动发现并唯一选择粗剪 FCPXML/FCPXMLD 和对应低码参考视频；
- 发现旁白 SRT、转写稿、文字稿、notes 及 FCPXML 内的 Marker 和时间线文字；
- 解析 sequence/spine、项目规格、显式 `<gap>` 和 primary storyline 中的隐式时间洞；
- 依据 caption 元素、name/role 语义和外部文本匹配，将文字标为 `narration_subtitle`、`design_text` 或 `ambiguous`；
- 输出 `ready`/`blocked`、具体证据、blocker、warning 和最小问题清单。

FCPXML/FCPXMLD 与低码粗剪参考视频是入口硬要求。animation brief、逐镜设计稿、品牌资料和重复旁白格式不是硬要求。普通文字歧义不阻塞入口；只有缺少必要输入、必要候选无法唯一确定或 FCPXML 无法解析时，才在入口阶段向用户提问。

SRT、时间线字幕、转写稿和文字稿都属于旁白对齐证据，不要求用户事先人工校正错别字。参考视频实际口播负责旁白措辞，FCPXML/FCPXMLD 负责时间位置、项目帧率和时间基准；任何外部文字时间码都不得替代源 XML 成为回填权威。

### scripts 负责确定性操作

V1 计划由以下脚本组件承担机械操作；名称表达职责，具体模块边界可在实现计划中细化，但不得改变 Skill 与脚本的分工原则。

- `inspect_fcpxml.py`：解析画幅、帧率、时间基准、故事线和素材引用；
- `align_narration.py`：对齐旁白、字幕和动画提示；
- `build_manifest.py`：生成并校验统一动画清单；
- `init_afterforge_project.py`：一次性创建项目级 Agent 指令入口；已存在时不覆盖，且不承担 Vn 创建；
- `scaffold_hyperframes.py`：使用仓库控制的最小模板，根据动画清单创建一个新的、可独立重渲染的 Vn HyperFrames 工程；不调用通用 `hyperframes init`，不生成或更新项目级 Agent 文件；
- `sync_storyboard.py`：从 manifest v2 生成 `STORYBOARD.md` 和只引用 canonical cue 的 A11 review projection；
- `layout_lock.py`：冻结并验证 A11 已批准 composition、样式、字体、review projection、投影规格与 hero poster 的 SHA-256；
- `assemble_hyperframes.py`：按 manifest 中的 FCPXML 有理数时间装配正式 cue composition；
- `sync_delivery.py`：为每条 animated cue 生成原生 delivery 尺寸的透明渲染 host；
- `validate_hyperframes_adapter.py`：检查 adapter 路径、ID、canonical/delivery 尺寸、依赖、review projection、motion/layout 边界与 layout lock；
- `migrate_single_source.py`：把旧 Vn 的最新 animation composition 拆分为 canonical cue 与 motion，同时保留旧目录作迁移对照；
- `migrate_delivery_layout.py`：把旧 854×480 canonical cue 包装为 delivery-native root，并强制重新执行等价验收；
- `migrate_workflow_stage_contract.py`：把一个 legacy Vn 显式绑定到当前合同，保留旧 reviews，但不继承旧用户批准；
- `workflow_status.py`：从当前 evidence 推导阶段状态与失效结果；
- `serve_workflow_review.py`：启动绑定单个 Vn 的本地 Review，受控写入 A11/A13 comment、用户批准、A14 授权和 D5 验收；
- `render_animations.py`：只有 resolver 证明 A11–A14 与 D1 当前有效时，才按 composition 原生尺寸渲染透明 ProRes 4444；
- `validate_delivery.py`：检查 ProRes 4444、alpha、尺寸、帧率与逐 cue 时长；
- `register_delivery_assets.py`：重新探测 ledger 对应的实际 MOV，只把验证通过的稳定 `deliveryAsset` 注册进 manifest；
- `fcpxml_timing.py`：负责宿主定位、有理数时间、`offset` / `start`、lane 分配和 `timeMap` 边界；
- `inject_fcpxml.py`：克隆目标 Project、创建新 Event / Project 身份、注册资源并插入独立 connected clips；
- `build_delivery_package.py`：持有唯一 `deliveryProtocolVersion`，计算 `deliveryFingerprint`，创建临时扁平包，hard link 或复制 MOV，并原子发布；
- `validate_fcpxml_package.py`：验证媒体、DTD、引用图、时间位置、原时间线不变性、包结构和幂等复用；
- `compare_fcpxml_roundtrip.py`：对首次 FCP 导入以及后端协议变化后的再导出结果执行回归验证。

上述 FCPXML 交付后端职责已有确定性实现；首次真实 FCP 导入与再导出 round-trip 仍是协议基线的人工作业边界，不由脚本伪造。

脚本必须把原始项目输入视为只读，并产生可单独检查的新输出。

## `animation-manifest.json` 中间层

`animation-manifest.json` 是内容分析、动画渲染与 FCPXML 回填之间的稳定契约，也是项目泛用性的核心。分析阶段先生成清单，渲染后端消费清单，回填阶段同时依据清单和实际渲染结果定位素材。

概念结构如下：

```json
{
  "project": {
    "source": {
      "width": 3840,
      "height": 2160,
      "frameDuration": "100/2400s"
    },
    "preview": {
      "width": 854,
      "height": 480
    },
    "delivery": {
      "width": 1920,
      "height": 1080,
      "videoCodec": "prores-4444"
    },
    "creativeDirection": {
      "visualSpec": {
        "canonical": "../frame.md",
        "snapshot": "frame.md",
        "snapshotSha256": "<sha256>"
      },
      "motionDirection": {
        "character": "沉稳、克制、具有重量感",
        "rhythm": "缓慢建立、重点落下、留出停顿",
        "easing": "避免轻弹和玩具感，强调受控减速",
        "transitions": "少量、连续、服务叙事",
        "avoid": ["喜剧感", "轻快弹跳", "无依据的故障效果"]
      }
    }
  },
  "cues": [
    {
      "id": "anim_001",
      "narrationAnchor": "我们看到的世界，真的是世界本身吗？",
      "trigger": {
        "startPhrase": null,
        "endPhrase": null,
        "blankMeans": "whole-narration-segment"
      },
      "guidanceReview": {
        "status": "agent-normalized",
        "notes": ["保留表达目的，时间位置改由 FCPXML 对齐"]
      },
      "resolvedTimeline": {
        "start": "38s",
        "duration": "24/5s",
        "authority": "fcpxml"
      },
      "designRoute": {
        "functions": {
          "primary": "emphasize-narration",
          "secondary": []
        },
        "sourceRelationship": {
          "primary": "B-source-led",
          "secondary": null
        },
        "referenceLanguages": {
          "primary": "film-titles",
          "secondary": []
        },
        "rationale": "突出疑问句，同时服从原镜头的既有构图"
      },
      "type": "kinetic-title",
      "visualIntent": "空间逐渐收紧，制造被监视感",
      "text": ["我们看到的世界", "真的是世界本身吗？"],
      "layer": 2
    }
  ]
}
```

当前 HyperFrames adapter 使用 manifest schema v2；机器可读约束见 `references/animation-manifest.schema.json`。至少表达：

- 项目画幅、帧率和时间基准；
- 480p 审阅与 1080p 最终交付规格；
- 当前视频项目已确认的整体视觉包装规范引用，以及跨渲染器的统一运动气质、节奏、缓动、重量感、转场原则和动效禁区；
- 每个动画提示的稳定标识、用户原始旁白锚点和可选触发词句；
- 系统依据参考口播和 FCPXML 解析出的精确时间位置与时长；
- 对应口播、字幕范围、用户原始要求及其证据来源；
- 用户主动提供动画脚本时，每条相关 cue 的可执行性审核状态与简短依据；
- 每条动画的主次信息功能、与原画的主次关系、参考视觉语言及简短判断理由；
- 动画类型、视觉意图、展示文字和层级；
- 人工确认状态；
- 渲染结果及其可回填引用。

正式渲染通过后，每条 `animated` cue 注册一个渲染后端无关的 `deliveryAsset`，至少保存稳定文件名、SHA-256、宽高、源帧率、实际有理数时长、codec 和 alpha 状态。manifest 不保存正式包的绝对路径；`source-only` cue 不得拥有 `deliveryAsset`。具体 schema 字段在后端实施时落地，但这项职责与权威边界已经冻结。

`guidanceReview` 是可选的 cue 级内部审核记录，只在用户主动提供动画脚本或逐镜要求时出现。`status` 使用 `ready`、`agent-normalized`、`needs-material`、`needs-clarification`、`out-of-scope` 或 `unaligned`，`notes` 保存判断依据和不改变范围的规范化说明。它不建立第二份审核报告，不参与 intake 的 `ready` / `blocked` 判定，也不进入 A11 layout lock；未提供脚本时该字段缺省。需要素材时，A7 先记录具体需求，待 Vn 已建立且相关 cue 进入具体设计后再向用户索取，并把用户在窗口提交的文件复制到该 Vn 的素材目录、纳入对应 layout dependencies，不长期引用聊天临时路径。

当 cue 要求在生成动画内重放、重排、裁切、遮罩、平铺或以其他方式重新合成两段或以上独立原片时，A7 默认标记 `needs-material`。粗剪参考视频和 FCPXML 源引用只能证明上下文与可用候选，不证明用户对精确取段和进入顺序的创作选择。默认要求每个语义片段独立导出且带可用余量；只有用户明确给出精确源范围并授权代为提取时才可例外。该结论只阻塞受影响 cue，不改变整个 intake 的就绪状态。

独立动画原片的标准可接受输入为 1920×1080 H.264、匹配源 FCPXML 的恒定帧率、Rec.709 SDR、无预烘焙裁切/调速/边框/动画，目标动作前后各至少约 0.5 秒可用余量，过渡或选段尚需弹性时建议 1 秒；音频可省略。只有经批准方案需要大幅放大裁切、抠像、重度影像处理或近全画幅重用时，才按需索取更高分辨率或帧内编码。该输入规格不改变最终 1920×1080 透明 ProRes 4444 交付协议。

独立原片的素材身份、进入顺序和可用内容以用户最新明确说明，以及实际投放文件的名称、编号顺序和可检查画面为权威。动画脚本中列出的素材类型默认只是规划参考；实际素材与用户说明一致但与脚本举例不同时，A7 保留原表达目的、在 `guidanceReview.notes` 记录替换依据，并以 `agent-normalized` 继续。只有用户说明、文件名、编号顺序或实际画面相互冲突时才进入 `needs-clarification`。该规则不改变脚本对 cue 风格、运动或表达目的的明确要求。

项目级 `frame.md` 与视频级统一运动气质承担 cue 未特别说明部分的默认风格。用户脚本若对单条镜头明确指定视觉或运动风格，该要求在该 cue 及其明确属性范围内优先；覆盖证据和范围写入 `guidanceReview.notes`，实际选择同步进入 `designRoute` 与 A11。未指定属性继续继承项目默认。逐镜风格要求不改变 FCPXML 时间权威、AfterForge 范围、读写边界、交付协议或后端能力边界；覆盖范围本身不清时进入 `needs-clarification`，不得由 Agent 猜测或扩大。

用户脚本中的旁白词句是语义锚点，不是精确时间输入。开始或结束触发词句留空时，默认使用整段对应旁白范围。所有写入 FCPXML 的时间最终必须转换为符合源项目时间基准的精确有理数表示；SRT 时间、文档时间码和未经校验的浮点秒数不得直接回写。

## 视频级创意方向与 Storyboard 审阅层

具体动画在形成逐条方案之前经过视觉语法路由层。该层由 Skill 依据 `references/visual-grammar.md` 执行，判断顺序固定为“信息功能 → 与原画的关系 → 可参考的视觉语言”。内部采用两次连续推理：A8 之前先判断功能和原画关系，用真实需求约束项目级视觉候选；A8 确认 `frame.md` 后，再在已确认范围内选择参考语言并完成路由。两次推理不增加新的用户验收。该层是跨项目的创作判断方法，不是项目级设计规范、风格预设或渲染组件库。

每条 cue 以 `designRoute` 保存实际判断：一个主功能及可选次要功能、一个主原画关系及可选辅助关系、一个主要参考语言及可选辅助语言，以及简短理由。功能与参考语言使用开放词汇；Agent 可以在现有索引不足时扩展，但不得为了匹配枚举而错误归类。A、B 两种原画关系允许混合，但必须确定主关系，不能用“混合”回避构图判断。“照顾、避让、保留原画可见性”本身不构成 B；只有原画承担不可替代的信息或叙事功能时才计入 B。混合态必须通过双删除测试：分别假设删除包装和删除原画，只有两层各自都承担不可由另一层替代的信息或叙事功能时，才记录主辅混合关系。

Agent 默认自主完成该路由，不新增逐条用户确认。分叉会显著改变任务范围、违反已经确认的约束或产生难以逆转的后果时，必须单独请求确认。初始设计或后续 A11/A13 comment、聊天反馈修改中，用户措辞或累积的已确认约束仍支持两种以上合理解释，且不同解释会实质改变最终构图、必须出现的内容、运动方式或特殊约束时，Agent 必须在选择或实施受影响 cue 的方案前提出一个聚焦问题。已有批准、赶时间、低成本返工或后续仍可审核都不能把这类解释权转给 Agent。澄清不新增批准门，也不等于批准；用户选定的影响范围及既有审核、失效规则不变。结果已经明确而只剩 DOM/CSS、缓动参数等技术实现细节时仍由 Agent 自主决定；普通审美差异在既有 Storyboard / Demo 验收中暴露。

每个视频项目都在 `AfterForge/frame.md` 建立一份项目级 canonical visual spec。它是该视频整体视觉包装审美的长期规范，不是跨项目通用皮肤，也不只记录颜色和字体。它至少约束艺术方向、画面构成原则、信息层级、图形语言、背景与前景关系、形状和组件处理、材质与纹理、影像处理、色彩、字体、间距以及明确的视觉禁区。

创建新 Vn 时，`scaffold_hyperframes.py` 把当时的 canonical `frame.md` 复制到 Vn HyperFrames 工程根层，作为该版本的构建快照，并在本版 `animation-manifest.json` 中记录 canonical 相对路径、快照相对路径和 SHA-256。Vn 进入制作后，后续 canonical 更新不得静默改变旧版快照；检查和重渲染旧 Vn 时必须使用其本地快照。HyperFrames 使用快照实现本版视觉一致性；更换渲染后端时，应依据 manifest 与该快照生成等价适配规范。

同一个 Vn 的 HyperFrames runtime 也遵循快照式生命周期。`package.json` 中四个 managed scripts 的统一精确 pin 是当前 runtime 的唯一 machine authority；`meta.json.toolchain.hyperframes.createdWithVersion` 只保存不可变创建来源，`migrations` 保存后来显式发生的版本事件，不再复制一个可独立漂移的 current version。普通 invocation 恢复只验证并使用既有 pin，不探测或采用 npm latest。只有用户明确授权时，`migrate_hyperframes_runtime.py` 才能迁移到另一个精确版本；事件必须逐项记录实际运行的兼容性检查，并分别列出 preserved、rebound、invalidated 的审核 evidence，不能以含义不明的 `validated` 总状态代替。

HyperFrames runtime 是审核输入的一部分。A11 layout lock 与逐 cue approval 绑定生成它们的 runtime pin，A12 及下游 `inputFingerprint` 也包含该 pin。实际版本变化默认使 A11 及其下游 evidence 失效；只有版本未变化且现有产物可以被证明确由当前 pin 生成的历史核对，才允许把未绑定的 A11 evidence 重新绑定而不要求用户重复审核。

除视觉包装外，每个视频还必须在正式动画实施前冻结统一的运动气质。该约束记录在 `animation-manifest.json` 的视频级 `creativeDirection.motionDirection` 中，至少表达运动性格、整体节奏、速度与重量感、缓动倾向、元素入场与退场逻辑、转场原则、停顿方式和明确禁止的动效倾向。逐条动画可以根据内容变化强弱，但不得无理由偏离该视频已经确认的运动气质。

新制作的运动默认以流畅、可读、可感知缓动及后续剪辑空间为目标，不统一秒数或入退场比例，不以“不漂浮”禁止有明确用途的持续运动；具体执行规则由 `SKILL.md` 承担。该默认只影响新方向的建立，不自动更新既有 Vn 快照或批准，也不授予移动时间线起点、修改源 XML 或实现素材子区间摆放的权限。

Storyboard 审核页是 HyperFrames 适配层从草稿状态 `animation-manifest.json` 生成的人工审阅视图，不是独立权威源，也不负责精确时间。每张 cue 卡按对应旁白、主审帧与必要辅助帧、`finalAnimationDescription`、逐帧 comment 与批准操作排列；用户材料未提供镜号时不伪造原镜号。`finalAnimationDescription` 是 cue 级单一自然语言字符串，只描述所有必要澄清完成后、截至进入 A11 时该镜最终如何呈现，不采用固定字段清单，也不展示澄清过程、讨论理由或修改历史；页面不得从聊天重构说明或维护第二份副本。页面在当前 cue / still 旁就地提供 comment、处理状态和批准操作，不要求用户重复选择 A11、cue 或时间码；只有当前 layout lock 有效、最终动画说明存在且没有开放 comment 的 cue 才可单独或批量批准，机器仍保存逐 cue evidence。提交 comment 只使相关批准证据与下游状态失效，当前锁定静帧继续显示为被评论的待修改版本；直到 composition、projection、依赖或审核帧字节真实变化，layout lock 才因哈希不符而失效。评论保存结果必须独立反馈，不能用批准 blocker 暗示写入成败。记录持久化到当前 Vn，而不是只留在浏览器临时状态或聊天历史中。候选联系表只作方案比较材料，不能替代正式审核页。

Review shell 与其中承载的受审内容是两个独立视觉层。Reviewer 自身的页面背景、字体、导航、按钮、表单、状态和容器样式由仓库级 Review 实现固定维护，不读取项目级 `AfterForge/frame.md`，也不读取 Vn 内的 `frame.md` 快照；这些项目视觉规范只影响 iframe、静帧或视频中实际被审核的动画内容。当前 `serve_workflow_review.py` 的视觉 shell 暂时作为仓库级 Review UI 基线，后续只能通过显式的仓库级 UI/UX 变更调整，不能随项目或 Vn 视觉规范变化。

每个 cue 必须有 1 张主审帧：选择主要元素已经进入并停稳、文字完整可读、原片主体自然清晰且静态设计信息最完整的代表状态，不机械选择中间帧，也不使用转场、过冲、遮挡或退场状态。若存在主审帧无法表达的其他静态构图状态，可额外增加 1–2 张辅助帧，因此每镜总计 1–3 张静帧；辅助帧不展示运动路径。A/B/C 候选必须固定相同语义状态、相同原片帧与相同真实文案，只比较设计变量。

每条 animated cue 的真实文案、DOM、布局和 CSS 终态只写在 `compositions/cues/<cue>.html`，其 root 尺寸必须与 `project.delivery` 完全一致。A11 不再另写静态 frame：`sync_storyboard.py` 生成的 854×480 `compositions/review/<cue>.html` 把对应原画 still 与该 1920×1080 正式 cue composition 按 manifest 比例叠加，并由 `heroTime` 选择静态验收状态。A12 的 854×480 合成入口同样投影该 cue；`sync_delivery.py` 则生成不缩放的 1920×1080 单 cue render host。review、delivery host、`STORYBOARD.md` 与顶层 `index.html` 都是 projection，不是可独立编辑的布局源；生成器只允许覆盖带自身 marker 的文件。

运动写在 `compositions/motion/<cue>.js`。它可以控制时间、transform、opacity、clip/mask 进度等动画状态，但不得改写 `left/top/width/height/font/gap/display` 等布局属性。A11 用户逐镜解决 comment 并批准静态设计后，`layout_lock.py` 用获批主审帧及必要辅助帧、`layoutDependencies` 中 canonical HTML/CSS/字体、生成的 review projection 及其尺寸规格建立 SHA-256 锁；任一审核帧、依赖或投影变化都使该 cue 回到 A11，并向下使 480p Demo 批准和原生渲染授权失效，而不是在运动阶段静默重新对位。`source-only` cue 只有原画 review projection，不创建正式 composition、motion、delivery host 或渲染槽。完整 adapter 协议见 `references/hyperframes-single-source.md`。

内部制作仍按“先形成文字方案，再制作使用真实文案的静态关键画面”的顺序执行，但不在两步之间增加批准门。若文字方案存在会实质改变最终呈现的解释分叉，则先用一个聚焦问题完成必要澄清；结果明确后不再打断，直接制作静态关键画面。只有文字方案和画面都准备好后才合并提交一次 Storyboard 静态样式验收。反馈先修正草稿 manifest，再重新生成审核页和受影响的静态关键画面；全部逐镜 comment 解决并确认后，静态审核才标记为 `approved`，随后进入完整运动制作。HyperFrames 所称 storyboard frame 是关键画面卡，不是 FCPXML 的帧级时间输入。

A8 与 A11 使用“可验收性门槛”而不是 Agent 质量验收门槛：完成当前产物后应尽快交给用户查看。低成本、确定性的自动检查可以执行，但结果默认只作为非阻塞自检；内容复读、结构复查、浏览器截图比较和 Agent 自行判断视觉完成度不得成为重复往返或延迟交付的理由。只有 storyboard 无法打开、关键资源缺失、页面明显报错等使用户无法正常查看目标产物的问题才构成 blocker。检查工具自身失败但用户仍能查看结果时，记录限制并继续交付。该宽松边界只适用于 A8、A11，不降低后续动画渲染、透明素材、FCPXML 回填和最终交付的工程验证要求。

## Agent 指令文件边界

`AGENTS.md` 与 `CLAUDE.md` 是 AfterForge 视频项目级长期操作入口，不是 Vn 创作成果，也不是 HyperFrames 独立重渲染所需运行时依赖。正常 Vn 工程不得包含由通用 HyperFrames scaffold 自动复制的这两份文件。项目级 `AGENTS.md` 负责 AfterForge 的资产边界、非破坏性规则和验证约束；项目级 `CLAUDE.md` 只承担未来 Claude Code 的发现入口，创建后默认不随 `AGENTS.md` 日常同步维护。

若未来某个 Vn 确实需要版本专属 Agent 规则，必须由具体需求单独确认并记录为例外，不能因为 CLI 会自动生成而保留。Vn 的独立重渲染由固定版本的 `package.json`、`hyperframes.json`、`meta.json`、本地 `frame.md` 快照、`index.html`、`compositions/` 和 `assets/` 保证，不依赖 Agent 指令文件。

## 渲染后端边界

HyperFrames 是 V1 的动画渲染后端，但不是整个系统的架构中心。它负责根据动画清单生成可预览、可渲染的动画工程和素材，不负责：

- 解析或修改 FCPXML；
- 决定口播与字幕的语义对应关系；
- 定义整个项目的中间数据结构；
- 直接操作 Final Cut Pro 资源库。

未来可以用 Apple Motion 模板、After Effects、Remotion、Blender 或人工制作替换渲染后端。替换时只应新增或更换渲染适配层，不应重写前端分析、`animation-manifest.json` 或 FCPXML 回填逻辑。

V1 中，HyperFrames 使用同一 delivery-native canonical cue composition 和独立 motion 生成两个输出层级：

- 审阅层：把 1920×1080 canonical cue 自动投影为 854×480 合成 MP4，叠加在对应粗剪画面上并保留粗剪参考视频自带的原声；该文件只用于动画效果确认；
- 交付层：Storyboard 静态审核、480p Demo 运动审核和用户显式原生渲染授权三项均有效后，通过自动生成的 1920×1080 delivery host 在 composition 原生尺寸直接渲染透明 ProRes 4444 MOV；帧率始终跟随源 FCPXML，禁止 `--resolution` 和后期放大。

审阅与交付之间必须存在三项独立事实：Storyboard 静态样式审核已通过、绑定当前文件哈希的 480p Demo 运动审核已通过、用户已针对这组获批输入显式授权原生渲染。Demo 审核页自动记录当前播放时间和对应 cue，持续性问题才由用户附加时间范围；自由文本与机器影响范围分离，同一 comment 可由用户选择影响 static、motion 或二者。涉及 static 时重开受影响 A11 并完整向下失效，仅 motion 时保留有效 A11 并重开 A13/A14；两者都不强制用户退出当前 Demo 页面。页面记录是验收与机器门禁依据，聊天只负责实时讨论。`render_animations.py` 在三项事实、有效 layout lock、输入指纹或授权指纹任一缺失或不匹配时 fail closed，并由 D2 ledger 将正式 MOV 哈希绑定到授权状态。详细设计见 `docs/superpowers/plans/2026-09-02-review-gates-design.md`。

旧 Vn 若仍以 854×480 为 canonical root，先用确定性 legacy stage 把既有布局映射进 1920×1080 root。该映射仍由浏览器在 1920×1080 capture 中绘制 CSS、文字和图形，不放大已编码视频；迁移会清除旧 lock、在 `layoutRevision` 保留修订基线，并要求用户重新确认 480p hero 与完整动画等价性。新批准锁必须从保留基线单调递增。新 Vn 不使用兼容 stage，直接按 delivery 坐标创作。

源时间线分辨率不决定动画交付分辨率。当前 16:9 自媒体 V1 即使接入 4K 电影素材时间线，也不生成 4K 动画；720p 不作为统一最终规格。

## 声音制作边界

AfterForge 不生成、设计、混合、交付或回填音效与音乐。粗剪参考视频自带的原声只作为旁白内容、节奏判断和 480p 合成审阅的证据，不成为 Vn 交付素材；manifest、storyboard、HyperFrames 工程和 FCPXML 回填协议均不建立声音制作字段或引用。

## FCPXML 回填边界

回填阶段只根据已经确认的动画清单和实际存在的渲染素材工作，并遵守以下边界：

- 永不覆盖原始 FCPXML 或 FCPXMLD；
- 输出一个新命名的 Final Cut Pro 项目描述；
- 保留原有粗剪结构，不把动画生成流程变成重新剪辑电影原片；
- 将动画作为可继续调整的连接片段放置在对应画面上方；
- 用户不负责提供帧级精确出点；回填使用系统解析出的精确开始位置和实际渲染素材时长，并允许透明动画保留便于剪辑的前后余量；
- 使用可迁移、可校验的项目素材路径；
- 回填前后校验项目帧率、时间基准、总时长、片段位置和素材引用；
- 不直接修改 Final Cut Pro 资源库，最终由用户导入新 FCPXML；
- 无法可靠对齐或无法验证的项目不得静默写入，必须进入人工确认清单。

### 产品结果与数据权威

正式结果是一份可导入 Final Cut Pro 的新 `.fcpxmld`：它包含原目标 Project 的完整时间线副本，并在其上增加每条 `animated` cue 对应的透明动画 connected clip。`source-only` cue 不生成动画、空文件或占位片段。用户导入后可以逐条移动、裁切、禁用或复制动画；AfterForge 不替用户完成最终帧级剪辑。

各数据源职责固定如下：

- 原 FCPXML / FCPXMLD 是源 Project 时间线结构、帧率、有理数时间、原媒体、转场、变速、音频和嵌套故事线的唯一权威，始终只读；
- `animation-manifest.json` 是 cue 身份、`animated` / `source-only` 状态、系统解析的粗略回填区间和已验证 `deliveryAsset` 的长期机器契约；
- `render-ledger.json` 只是一轮渲染命令、实际路径、探测结果、哈希和 layout lock 对应关系的执行证据，不是 FCPXML 的长期权威；
- 正式注册必须根据 ledger 重新探测实际 MOV，再把稳定媒体属性写入 manifest；FCPXML 生成器不得直接依赖 HyperFrames 私有 ledger；
- 生成的 `Info.fcpxml` 是原 FCPXML、manifest 和已注册媒体的派生交付物，不反向成为时间、设计或媒体状态权威；
- 不建立第二份 delivery manifest。

### 扁平交付包与媒体引用

正式包直接创建在项目级 `AfterForge/` 根层，命名为 `AfterForge__<sourceVersion>__d-<deliveryFingerprint>.fcpxmld`。包根目录只允许一个 `Info.fcpxml` 和全部已注册动画 MOV，不创建 `Media/`、`delivery/` 或其他子目录，也不放入 manifest、ledger、日志、验证报告、临时文件和原电影媒体。

动画文件名来自 manifest 的 `deliveryAsset.fileName`，建议形式为 `AF__<stableCueId>__<semanticSlug>.mov`；XML 只使用包根目录同级相对引用，例如 `./AF__p1s01-c01-question.mov`，禁止写入构建机绝对路径或 Vn 内部路径。原 Project 已有媒体引用保持源 XML 语义，不复制原电影素材。

正式 MOV 的 canonical source 仍位于 Vn 内部 delivery 区。构建包时，同一文件系统优先创建 hard link，不可用时复制；无论采用哪种方式，发布前都重新计算包内文件哈希。canonical MOV 与已经发布的 `.fcpxmld` 都不可原地覆盖。

### 新 Event、Project 与 connected clips

输出明确创建新的 `AfterForge__<sourceVersion>` Event 和其中新的 `AfterForge__<sourceVersion>__<sourceProjectName>` Project。用户在导入时选择目标 Library；输出不得指定、更新或直接操作既有 Library、Event 或 Project。

生成器从源 XML 克隆目标 Project 的完整 sequence，并建立新的导入身份：不沿用原 Event `uid`，不沿用原 Project `uid`、`modDate` 等可能被识别为更新既有对象的字段，不复制与目标 Project 无关的原 Event 组织内容。V1 保留原 `resources` 集合后再确定性追加动画资源，不提前裁剪可能被嵌套结构引用的资源。除明确新增的身份、动画资源和 connected clips 外，sequence 总时长、主故事线、原媒体、音频、转场、变速和既有元数据语义必须保持不变。

每个 `deliveryAsset` 对应一个新的纯视频 asset resource，引用包根目录同名 MOV，并使用实际时长、无音频属性和匹配的 1920×1080 源帧率 format；没有匹配 format 时确定性新增。resource ID 从现有资源集合中分配，不假设连续。

动画分别写为独立 connected clips，不合并为 compound clip、统一 secondary storyline 或完整透明时间线。lane 根据回填后的时间区间确定：重叠 cue 使用不同正向 lane，不重叠 cue 使用最低可用正向 lane，不把镜号硬编码为 lane。

### 粗放定位与精确时间记账

回填只要求动画落在正确镜头或旁白语义段落附近，不要求踩中某个字、某一帧或严格旁白出入点，也不把实际 MOV 拉伸到 manifest 粗略区间长度。工程表达仍必须严格使用源 FCPXML 的帧率、合法结构和有理数时间。

时间映射模块必须从 cue 的序列时间找到对应主故事线宿主，将序列时间转换为合法 connected-clip `offset`；存在嵌套、非零 `start`、局部 `offset` 或 `timeMap` 时，必须处理宿主局部时间和序列时间之间的映射。写入后再从输出 XML 反算序列位置，确认动画仍落在目标镜头或语义段落范围内。该验证防止放错镜头，不替用户完成帧级同步。

### 交付指纹与单一生成语义版本

FCPXML 交付后端使用 `deliveryFingerprint` 识别可验证、可复用且不可原地覆盖的正式交付包。指纹的规范化输入至少包括：原 FCPXML 文件哈希、按 cue ID 排序后的已验证 `deliveryAsset` 注册信息、系统解析出的粗略回填位置，以及后端持有的稳定常量 `deliveryProtocolVersion`。

`deliveryProtocolVersion` 是交付输出语义的唯一版本，也是交付设计中“回填策略版本”的规范名称；两者不是并行字段或两套版本机制。它不写入 `animation-manifest.json` 充当第二个业务权威，也不参与 A11 layout lock。相同业务输入只有在当前 `deliveryProtocolVersion` 也相同时，才允许命中同一 `deliveryFingerprint` 并验证、复用已有交付包。

只要后端变化会使相同业务输入产生语义不同的正式交付结果，就必须提升 `deliveryProtocolVersion`，包括 FCPXML 注入结构、时间映射、lane 分配、媒体引用、Event / Project 身份处理、交付包结构或既有包复用语义的变化。纯重构、日志、测试、性能或错误提示变化若不改变交付输出语义，则不提升版本。版本提升后，当前后端重新计算的指纹必须与旧包不同；不得用 Git commit、实现文件哈希或另一套隐式版本替代这项显式契约。

### 确定性生成、失败恢复与原子发布

正式流程固定为：验证原 FCPXML、approved manifest、layout lock、render ledger 和实际 MOV；注册 `deliveryAsset`；执行交付预检；在内存中克隆目标 Project 并注入资源和 connected clips；在 `AfterForge/` 根层创建同文件系统临时包；生成 `Info.fcpxml` 并 hard link 或复制 MOV；通过全部自动验证后，原子重命名为正式 `.fcpxmld`。

任何输入缺失、哈希不符、锁失效、媒体规格错误、时间越界或 XML 构建错误都必须在正式发布前阻塞。失败时只清理本轮创建且可明确识别的临时包，不删除或修改原输入、canonical MOV 或既有正式包。检测到同 fingerprint 包时先完整验证：通过则幂等复用，失败则报告损坏并阻塞，不自动修补或覆盖。

### 自动验证与 Final Cut Pro 验收

回填属于工程交付，不沿用 A8/A11 的轻量审美检查策略。自动验证至少覆盖：

- 输入身份、源 XML 哈希、manifest、layout lock、ledger 与 Vn 对应关系；
- 只有 `animated` cue 拥有 `deliveryAsset`，实际 MOV 的名称、哈希、ProRes 4444、alpha、1920×1080、源帧率、实际时长和无音频属性与注册值一致；
- `Info.fcpxml` well-formed，并通过源 XML 版本对应 DTD；resource ID 唯一、全部 `ref` 可解析，动画资源和 connected clips 数量与 animated cues 精确一致；
- 动画只使用包根目录相对路径，不出现构建目录、Vn 深层目录、临时目录或音频节点；
- 同 lane 无重叠冲突，反算序列位置位于目标镜头或语义段落内，sequence 总时长不变；
- 排除新导入身份、AfterForge resources 和 connected clips 后，输出 Project / sequence 与源目标 Project 规范化比较一致；
- 包直接位于 `AfterForge/` 根层，只有一个 `Info.fcpxml` 和预期 MOV，不含子目录、隐藏临时文件或内部资产。

DTD 与自动检查通过不等于 Final Cut Pro 必然接受。首个真实基线 `2026-08-26_V1` 必须完成实际导入，确认新 Event / Project、完整粗剪、媒体在线、alpha、无音频、六条动画可独立编辑、第 6/7 镜无占位且未被强制代理或优化。随后从 FCP 再导出并执行 round-trip 比较，验证动画媒体身份、粗略位置、纯视频属性、主故事线和总时长。比较器应规范化 FCP 产生的非语义变化，包括 resource ID 重排、媒体 URL 前缀改写、等价有理数表示、微秒级 `timeMap` 舍入，以及不短于 connected clip 且不超过一帧的媒体 resource 物理尾差；connected clip 时长、语义区间、音频属性与原主故事线仍是硬约束。FCPXML 版本、时间映射或 `deliveryProtocolVersion` 发生语义变化时重新执行 round-trip；普通 Vn 在协议未变化时只需完整自动验证、一次实际导入和可编辑性确认。

## V1 工作流

V1 采用先审阅、后高质量渲染与回填的两阶段工作模式。

### 阶段一：分析与确认

1. 在用户提供的实际项目根目录创建或识别 `AfterForge/` 和 `user-inbox/`；
2. 紧接上一步、不中断用户地检查 AfterForge 视频项目是否已经初始化；未初始化时一次性创建根层 `AGENTS.md` 和 `CLAUDE.md`，已存在时不更新。步骤 1、2 保留各自编号和内部职责，但作为一次连续后台动作执行；
3. 由用户创建并明确当前使用的 `user-inbox/YYYY-MM-DD_Vn/`；用户需要规范填写动画要求时，Skill 可从 `assets/animation-script-template.docx` 向用户批准的位置提供副本，再由用户填写并自行放入该版本目录。模板不自动复制进项目，也不是进入下一步的条件；
4. 从该扁平版本目录发现 FCPXML/FCPXMLD、低码参考视频、已有旁白证据和可选设计约束；
5. 判断必要输入是否存在且可唯一确定，缺失时只索取真正阻塞的材料；
6. 解析项目规格、时间线、素材引用、显式/隐式空缺和文字证据；
7. 依据参考视频实际口播校正明显文字错误，将旁白原句和可选触发词句对齐到 FCPXML 时间线；存在 `materials.animation_guidance` 时逐条审核其是否可直接使用、可自主规范化、需要额外素材、需要澄清、超出范围或无法可靠对齐，并把 cue 级 `guidanceReview` 写入草稿 manifest；脚本对单条镜头明确指定的风格在该镜明确范围内优先于项目默认，其余属性继续继承项目规范；若受影响 cue 需在动画内重新合成两段或以上原片，默认要求独立带余量片段并标记 `needs-material`，不根据粗剪自行猜测取段和顺序；随后判断每条候选动画的主次信息功能和与原画的主次关系，没有主观动画提示时由 Skill 自主完成。该审核不新增用户验收轮次，只有未解决问题会改变 A8 方向或阻止受影响 cue 可靠继续时才单独询问；
8. 根据本视频的实际功能与原画关系统计，向用户提出适合当前视频的整体视觉包装与运动气质候选，并在产物可正常查看时尽快提交 A8 验收；确认后创建或更新项目级 canonical `AfterForge/frame.md`，并把统一运动气质写入草稿 `animation-manifest.json`；
9. 使用确定性版本脚手架创建新的 Vn HyperFrames 工程，复制 canonical `frame.md` 为本版快照并记录 SHA-256；不得调用通用 `hyperframes init` 或触碰项目级 Agent 文件；
10. 在已确认的项目视觉规范内为每条动画选择主要及可选辅助参考语言，完成 `designRoute`；对标记为 `needs-material` 的 cue，此时才索取已在 A7 明确的具体素材并复制进当前 Vn；随后内部细化逐条文字方案；若用户措辞或已确认约束仍存在会实质改变最终呈现的合理解释分叉，必须先提出一个聚焦问题，澄清后才在正式 `compositions/cues/` 完成真实文案、DOM、布局和 CSS 终态；
11. 从 manifest 和正式 cue composition 自动生成 cue / still 就地 comment 的 Storyboard 审核页与 review projection，将对应旁白、`finalAnimationDescription` 与主审帧合并为 A11 静态样式验收；每镜必须有 1 张主审帧，必要时再附 1–2 张静态构图辅助帧，所有审核帧进入 layout lock；当前合格 cue 可单独或批量批准并形成逐 cue evidence，全部 cue 通过后 A11 才完成；
12. 只在 A11 通过后，于独立 `compositions/motion/` 中实现运动并自动装配正式合成预览；不得复制或重写 A11 已批准布局；
13. 输出保留粗剪原声的 854×480 Demo，在播放器上下文自动绑定 comment 的时间点与 cue，按需增加时间范围，并由用户为一条完整意见选择 static、motion 或二者影响范围；全部 comment 解决后，由用户批准绑定当前 Demo 哈希的运动审核；
14. 静态与运动审核均通过后，另行取得用户针对当前获批输入的原生渲染授权；该授权不得从前两项批准或一般性的“继续”中推断。

### 阶段二：渲染、回填与验证

1. 验证 Storyboard 静态审核、绑定当前文件哈希的 480p Demo 运动审核和原生渲染显式授权均有效，canonical 尺寸等于 delivery，projection-aware layout lock 有效；
2. 为 animated cues 生成 1920×1080 delivery host，并在 composition 原生尺寸直接渲染透明 ProRes 4444 MOV；
3. 逐 cue 验证 codec/profile、alpha、尺寸、帧率和时长；
4. 重新探测实际 MOV，把稳定 `deliveryAsset` 注册进 manifest，`source-only` cue 保持无交付资产；
5. 计算包含 `deliveryProtocolVersion` 的 `deliveryFingerprint`，克隆原目标 Project，创建新 Event / Project 身份并注入独立 connected clips；
6. 在 `AfterForge/` 根层的同卷临时目录构建平铺 `.fcpxmld`，执行媒体、DTD、引用图、时间映射、原时间线不变性、包结构和幂等性验证；
7. 自动验证通过后原子发布正式包，由用户导入 Final Cut Pro 检查媒体在线、alpha、独立可编辑性和粗略位置；
8. 首次 V1 及交付协议语义变化时，从 Final Cut Pro 再导出并完成 round-trip 回归验证。

## V1 范围

第一版固定支持以下主流程：

- 入口：用户提供实际项目工作区，Skill 复用其中已有材料；
- 用户工作目录：默认在项目根目录使用 `AfterForge/`，仅作为可替换显示名，内部身份保持 `fcpxml-animation-pipeline`；
- 项目级长期资产：AfterForge 根层 `AGENTS.md` 与 `CLAUDE.md` 只初始化一次；canonical `frame.md` 在视觉方向确认后建立并独立于 Vn 维护；
- Vn 资产：每个版本保存自己的 manifest、storyboard、HyperFrames compositions、素材、固定构建配置和 canonical `frame.md` 的校验快照；不重复维护项目级 Agent 文件；
- 用户投料区：项目根目录使用 `user-inbox/`，版本目录由用户按 `YYYY-MM-DD_Vn/` 创建和选择，Skill 全程只读；
- 必要输入：FCPXML/FCPXMLD 与对应低码粗剪参考视频；
- 可替代旁白证据：旁白 SRT、时间线字幕、转写稿或已有文字稿；已有一种足够时不要求重复格式，也不要求用户人工校正自动转写错别字；
- 可选设计约束：Marker、时间线文字、notes 或其他已有材料；animation brief 不作为默认要求；
- 可选脚本模板：只在用户需要时从 Skill 资产提供副本，用户自行回填和投放；自由格式脚本和完全不提供脚本都继续受支持；
- 创意判断：逐条遵循“功能 → 与原画关系 → 可参考视觉语言”，路由写入 manifest 并在 storyboard 中验收，不建立额外权威源；
- 脚本审核：用户主动提供动画脚本时在 A7 做 cue 级可执行性判断，结论写入现有 manifest，不把可选脚本升级为 intake 硬要求或独立验收阶段；
- 多原片 cue 素材：需在动画内重新合成两段或以上原片时，默认要求用户提供独立带余量片段；文件名使用 `01-` 等顺序前缀，或保留 `animation-source`、“动画素材”等明确信号时进入 `materials.animation_source_clips`，不与低码粗剪参考视频竞争候选身份；带顺序前缀但包含粗剪关键词的文件仍是参考候选；素材身份以用户当前说明和实际文件为权威，脚本素材类型默认只作参考；
- 视觉场景：以 16:9 横屏口播类视频为首要目标；
- 渲染：HyperFrames；
- 静态审阅：cue / still 就地 comment 的 Storyboard 页面，每镜 1 张主审帧，存在额外静态构图状态时可再附 1–2 张辅助帧；
- 运动审阅：854×480 合成 Demo，comment 自动绑定播放器时间与当前 cue，可选持续范围，允许用户将同一意见声明为影响 static、motion 或二者；视频保留粗剪参考视频自带的原声；
- 透明动画交付：1920×1080 ProRes 4444 MOV，帧率跟随源 FCPXML；
- 声音边界：不生成、设计、混合、交付或回填音效与音乐；
- 回填：在项目级 `AfterForge/` 根层生成平铺、不可覆盖、可验证复用的 `.fcpxmld`，包含完整原 Project 副本和逐条独立动画，不覆盖原始输入；
- 审阅门槛：先确认当前视频的整体视觉包装与运动气质；再于 Storyboard 审核文字方案与静态样式；随后于 480p Demo 审核运动；两项均通过后仍需用户单独授权原生渲染；
- 异常处理：不能可靠对齐的内容进入人工确认清单。

V1 不包含 Plugin 打包、多用户分发、直接修改 Final Cut Pro 资源库，也不扩展为通用视频编辑平台。

## 预期 Skill 目录结构

以下结构是后续实现的边界说明，不代表相关文件已经存在：

```text
fcpxml-animation-pipeline/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
├── references/
├── assets/
│   └── animation-script-template.docx
└── docs/
    ├── PROJECT.md
    ├── CURRENT.md
    ├── DECISIONS.md
    └── ARCHITECTURE.md
```

遵循渐进披露原则：`SKILL.md` 只保留核心工作流和资源导航；详细数据模式、FCPXML 约束和渲染后端说明按需放入 `references/`；确定性实现放入 `scripts/`；输出模板或可复用工程资源放入 `assets/`。

## 架构验收原则

后续实现必须能够证明：

- Skill 的创作性判断与脚本的确定性操作边界清楚；
- `animation-manifest.json` 可以独立审阅、验证并驱动渲染和回填；
- 项目初始化与 Vn 创建互不产生隐式副作用，创建 Vn 不修改根层项目资产；
- 任意 Vn 在只保留其固定配置、frame 快照、compositions 和本地素材时仍可独立检查与重渲染；
- HyperFrames 可以被其他渲染后端替换而不破坏前后流程；
- 原始输入不被修改，输出可回退；
- FCPXML 的时间与素材引用经过自动校验；
- 最终交付能够由 Final Cut Pro 实际导入并继续编辑。
