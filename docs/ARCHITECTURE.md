# 架构基线

## 文档职责

本文档定义 `fcpxml-animation-pipeline` 的长期架构基线：系统分层、组件职责、核心数据流、V1 输入输出、渲染后端边界和 FCPXML 回填边界。后续实现可以细化内部技术方案，但不得在未更新 `docs/PROJECT.md` 和 `docs/DECISIONS.md` 的情况下改变这里确定的核心设计。

本文档不记录开发进度；当前实现状态以 `docs/CURRENT.md` 为准。

## 总体架构

项目采用“Codex Skill + 确定性脚本工具链”的结构。Skill 负责需要理解语义、上下文和创作意图的判断；脚本负责必须稳定、可重复、可校验的机械操作。二者通过 `animation-manifest.json` 解耦。

```text
实际项目工作区
├── user-inbox/（用户维护，Skill 只读）
│   └── YYYY-MM-DD_Vn/（用户创建和选择，材料平铺）
│       ├── 必要：rough-cut.fcpxml / .fcpxmld
│       ├── 必要：低码粗剪参考视频
│       ├── 可替代旁白证据：SRT、时间线字幕、转写稿或已有文字稿
│       └── 可选设计约束：Marker、时间线文字、notes
└── AfterForge/（Skill 维护，唯一默认写入区；显示名可替换）
    ├── AGENTS.md（项目级 Agent 规则，只在项目初始化时创建）
    ├── CLAUDE.md（项目级 Claude 入口，只在项目初始化时创建）
    ├── frame.md（当前视频项目视觉规范的 canonical source）
    └── YYYY-MM-DD_Vn/（本版可独立重渲染的 HyperFrames 工程与交付）
        ├── animation-manifest.json
        ├── frame.md（本版构建时快照）
        ├── STORYBOARD.md
        ├── package.json
        ├── hyperframes.json
        ├── meta.json
        ├── index.html
        ├── compositions/
        ├── assets/
        ├── previews/*.mp4
        ├── animations/*.mov
        ├── audio/sfx/*.wav
        ├── audio/music/*.wav
        └── completed.fcpxml
```

`fcpxml-animation-pipeline` Skill 负责分析时间线、对齐旁白与动画要求、细化设计、生成 manifest、调用 HyperFrames、转码透明动画、回填新的 FCPXML 和执行完整性检查。项目级长期资产与 Vn 版本资产物理分层，不能把通用脚手架文件误计为每版创作成果。

## Skill 与 scripts 分工

### Skill 负责创作性判断与流程编排

`SKILL.md` 负责指导 Agent：

- 理解口播内容及其表达目的；
- 结合字幕和粗略动画要求细化画面表现；
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

Vn 版本创建与项目初始化完全解耦。Vn 由仓库控制的确定性 HyperFrames 适配脚手架创建，不以每版执行通用 `hyperframes init` 为前提。版本脚手架只写入新 Vn 目录，目标已存在时阻塞，不得触碰 AfterForge 根层的 `AGENTS.md`、`CLAUDE.md` 或 canonical `frame.md`。HyperFrames skills 的安装或升级属于机器环境维护，也不得绑定到项目初始化或 Vn 创建。

`user-inbox/` 初始化器遵守以下边界：

- 只创建或识别项目根目录下的 `user-inbox/` 顶层目录；
- 已存在时原样复用，不修改其中任何版本目录或材料；
- 同名路径是文件或符号链接时阻塞，不覆盖、不跟随；
- 不创建 V1，不递增版本号，不选择“最新版本”，不执行其他版本管理；
- `YYYY-MM-DD_Vn/` 由用户创建、选择和维护，其材料直接放在版本目录根层；
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
- `render_animations.py`：检查并渲染动画；
- `transcode_alpha.py`：将透明动画转换为 ProRes 4444；
- `inject_fcpxml.py`：将动画和音效引用写入新的时间线；
- `validate_delivery.py`：检查素材路径、帧率、时长、引用关系和 XML 合法性。

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
      "videoCodec": "prores-4444",
      "audio": "pcm-wav-48khz-24bit"
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
      "audio": [
        {
          "id": "sfx_001",
          "triggerPhrase": "真的是世界本身吗",
          "kind": "low-impact"
        }
      ],
      "layer": 2
    }
  ]
}
```

正式实现前必须把该概念结构收敛为可验证的数据模式。至少应表达：

- 项目画幅、帧率和时间基准；
- 480p 审阅与 1080p 最终交付规格；
- 当前视频项目已确认的整体视觉包装规范引用，以及跨渲染器的统一运动气质、节奏、缓动、重量感、转场原则和动效禁区；
- 每个动画提示的稳定标识、用户原始旁白锚点和可选触发词句；
- 系统依据参考口播和 FCPXML 解析出的精确时间位置与时长；
- 对应口播、字幕范围、用户原始要求及其证据来源；
- 每条动画的主次信息功能、与原画的主次关系、参考视觉语言及简短判断理由；
- 动画类型、视觉意图、展示文字和层级；
- 音乐或音效的稳定 ID、旁白触发词句、用途和独立文件引用；
- 人工确认状态；
- 渲染结果及其可回填引用。

用户脚本中的旁白词句是语义锚点，不是精确时间输入。开始或结束触发词句留空时，默认使用整段对应旁白范围。所有写入 FCPXML 的时间最终必须转换为符合源项目时间基准的精确有理数表示；SRT 时间、文档时间码和未经校验的浮点秒数不得直接回写。

## 视频级创意方向与 Storyboard 审阅层

具体动画在形成逐条方案之前经过视觉语法路由层。该层由 Skill 依据 `references/visual-grammar.md` 执行，判断顺序固定为“信息功能 → 与原画的关系 → 可参考的视觉语言”。内部采用两次连续推理：A8 之前先判断功能和原画关系，用真实需求约束项目级视觉候选；A8 确认 `frame.md` 后，再在已确认范围内选择参考语言并完成路由。两次推理不增加新的用户验收。该层是跨项目的创作判断方法，不是项目级设计规范、风格预设或渲染组件库。

每条 cue 以 `designRoute` 保存实际判断：一个主功能及可选次要功能、一个主原画关系及可选辅助关系、一个主要参考语言及可选辅助语言，以及简短理由。功能与参考语言使用开放词汇；Agent 可以在现有索引不足时扩展，但不得为了匹配枚举而错误归类。A、B 两种原画关系允许混合，但必须确定主关系，不能用“混合”回避构图判断。“照顾、避让、保留原画可见性”本身不构成 B；只有原画承担不可替代的信息或叙事功能时才计入 B。混合态必须通过双删除测试：分别假设删除包装和删除原画，只有两层各自都承担不可由另一层替代的信息或叙事功能时，才记录主辅混合关系。

Agent 默认自主完成该路由，不新增逐条用户确认。只有分叉会显著改变任务范围、违反已经确认的约束或产生难以逆转的后果时才单独请求确认；普通设计分歧和可低成本返工的选择统一在既有 A11 storyboard 验收中暴露。

每个视频项目都在 `AfterForge/frame.md` 建立一份项目级 canonical visual spec。它是该视频整体视觉包装审美的长期规范，不是跨项目通用皮肤，也不只记录颜色和字体。它至少约束艺术方向、画面构成原则、信息层级、图形语言、背景与前景关系、形状和组件处理、材质与纹理、影像处理、色彩、字体、间距以及明确的视觉禁区。

创建新 Vn 时，`scaffold_hyperframes.py` 把当时的 canonical `frame.md` 复制到 Vn HyperFrames 工程根层，作为该版本的构建快照，并在本版 `animation-manifest.json` 中记录 canonical 相对路径、快照相对路径和 SHA-256。Vn 进入制作后，后续 canonical 更新不得静默改变旧版快照；检查和重渲染旧 Vn 时必须使用其本地快照。HyperFrames 使用快照实现本版视觉一致性；更换渲染后端时，应依据 manifest 与该快照生成等价适配规范。

除视觉包装外，每个视频还必须在正式动画实施前冻结统一的运动气质。该约束记录在 `animation-manifest.json` 的视频级 `creativeDirection.motionDirection` 中，至少表达运动性格、整体节奏、速度与重量感、缓动倾向、元素入场与退场逻辑、转场原则、停顿方式、音画力度关系和明确禁止的动效倾向。逐条动画可以根据内容变化强弱，但不得无理由偏离该视频已经确认的运动气质。

`STORYBOARD.md` 是 HyperFrames 适配层从草稿状态 `animation-manifest.json` 生成的人工审阅视图，不是独立权威源，也不负责精确时间。它利用 HyperFrames Studio 的关键画面联系表和逐卡反馈能力，把每条动画的稳定 cue ID、用户材料中的原镜号、视觉语法路由、文字方案、真实展示文案、信息层级、元素数量、从属关系、构图、运动意图和声音方向与对应静态关键画面放在一起审阅；用户材料未提供镜号时不伪造原镜号。

内部制作仍按“先形成文字方案，再制作使用真实文案的静态关键画面”的顺序执行，但不在两步之间打断用户。只有两部分都准备好后才合并提交一次用户验收。反馈先修正草稿 manifest，再重新生成 storyboard 和受影响的静态关键画面；确认后 manifest 才标记为 `approved` 并进入完整动画制作。HyperFrames 所称 storyboard frame 是关键画面卡，不是 FCPXML 的帧级时间输入。

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

V1 中，HyperFrames 使用同一套响应式布局和动画逻辑生成两个输出层级：

- 审阅层：854×480 合成 MP4，把动画叠加在对应粗剪画面上，并可包含参考口播和临时音效或音乐混合；该文件只用于效果确认；
- 交付层：用户确认后生成 1920×1080 透明动画，并转换为适合 Final Cut Pro 合成的 ProRes 4444 MOV；帧率始终跟随源 FCPXML。

源时间线分辨率不决定动画交付分辨率。当前 16:9 自媒体 V1 即使接入 4K 电影素材时间线，也不生成 4K 动画；720p 不作为统一最终规格。

## 音频交付边界

最终音效和音乐统一为 48 kHz、24-bit PCM WAV。音效按触发项逐条输出，音乐保持独立，不生成 MP3 试听副本，也不把完整时间线预混为最终音频。每条音频使用旁白词句作为触发锚点，便于回到 Final Cut Pro 后继续微调；480p 审阅视频中的临时混音不构成回填素材。

## FCPXML 回填边界

回填阶段只根据已经确认的动画清单和实际存在的渲染素材工作，并遵守以下边界：

- 永不覆盖原始 FCPXML 或 FCPXMLD；
- 输出一个新命名的 Final Cut Pro 项目描述；
- 保留原有粗剪结构，不把动画生成流程变成重新剪辑电影原片；
- 将动画作为可继续调整的连接片段放置在对应画面上方；
- 将音效和音乐素材以独立引用保留，便于后续混音；
- 用户不负责提供帧级精确出点；回填使用系统解析出的精确开始位置和实际渲染素材时长，并允许透明动画保留便于剪辑的前后余量；
- 使用可迁移、可校验的项目素材路径；
- 回填前后校验项目帧率、时间基准、总时长、片段位置和素材引用；
- 不直接修改 Final Cut Pro 资源库，最终由用户导入新 FCPXML；
- 无法可靠对齐或无法验证的项目不得静默写入，必须进入人工确认清单。

## V1 工作流

V1 采用先审阅、后高质量渲染与回填的两阶段工作模式。

### 阶段一：分析与确认

1. 在用户提供的实际项目根目录创建或识别 `AfterForge/` 和 `user-inbox/`；
2. 紧接上一步、不中断用户地检查 AfterForge 视频项目是否已经初始化；未初始化时一次性创建根层 `AGENTS.md` 和 `CLAUDE.md`，已存在时不更新。步骤 1、2 保留各自编号和内部职责，但作为一次连续后台动作执行；
3. 由用户创建并明确当前使用的 `user-inbox/YYYY-MM-DD_Vn/`；
4. 从该扁平版本目录发现 FCPXML/FCPXMLD、低码参考视频、已有旁白证据和可选设计约束；
5. 判断必要输入是否存在且可唯一确定，缺失时只索取真正阻塞的材料；
6. 解析项目规格、时间线、素材引用、显式/隐式空缺和文字证据；
7. 依据参考视频实际口播校正明显文字错误，将旁白原句和可选触发词句对齐到 FCPXML 时间线；对每条候选动画先判断主次信息功能和与原画的主次关系，没有主观动画提示时由 Skill 自主完成；
8. 根据本视频的实际功能与原画关系统计，向用户提出适合当前视频的整体视觉包装与运动气质候选；确认后创建或更新项目级 canonical `AfterForge/frame.md`，并把统一运动气质写入草稿 `animation-manifest.json`；
9. 使用确定性版本脚手架创建新的 Vn HyperFrames 工程，复制 canonical `frame.md` 为本版快照并记录 SHA-256；不得调用通用 `hyperframes init` 或触碰项目级 Agent 文件；
10. 在已确认的项目视觉规范内为每条动画选择主要及可选辅助参考语言，完成 `designRoute`；随后内部先细化逐条动画文字方案，再制作使用真实文案的静态关键画面，由草稿 manifest 生成 `STORYBOARD.md`；
11. 将视觉语法路由、文字方案与静态关键画面合并为一次用户验收，不新增逐条确认；依据反馈修正草稿 manifest、storyboard 和受影响的关键画面，确认后将 manifest 标记为 `approved`；
12. 根据已确认方案制作完整动画和临时声音，输出时间线分析、逐句对齐结果、动画清单和 854×480 合成审阅 MP4；
13. 收集动画运动、整体观感和声音方向的最终确认，并保留无法可靠判断的人工确认项。

### 阶段二：渲染、回填与验证

1. 根据已确认清单创建并渲染 1920×1080 HyperFrames 透明动画，帧率跟随源 FCPXML；
2. 将透明动画转换为 ProRes 4444 MOV；
3. 生成逐条音效和独立音乐 WAV；
4. 将渲染结果注册并写入新的 FCPXML；
5. 验证 XML、素材引用、时间位置、帧率和总时长；
6. 交付完整、可迁移的项目目录，由用户导入 Final Cut Pro 继续检查和编辑。

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
- 创意判断：逐条遵循“功能 → 与原画关系 → 可参考视觉语言”，路由写入 manifest 并在 storyboard 中验收，不建立额外权威源；
- 视觉场景：以 16:9 横屏口播类视频为首要目标；
- 渲染：HyperFrames；
- 审阅：854×480 合成 MP4，只用于确认构图、节奏和声音效果；
- 透明动画交付：1920×1080 ProRes 4444 MOV，帧率跟随源 FCPXML；
- 音频交付：逐条音效和独立音乐使用 48 kHz、24-bit PCM WAV，不生成 MP3 或最终整段预混；
- 回填：生成新的 FCPXML 和关联媒体，不覆盖原始输入；
- 审阅门槛：先确认当前视频的整体视觉包装与运动气质；文字方案与真实文案静态关键画面合并为一次验收；完整动画制作后再确认 480p 合成预览；
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
