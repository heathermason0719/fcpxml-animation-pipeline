# 当前状态

## 已可靠成立

- 仓库基础目录和权威文档结构已经按全局项目治理规则建立；
- 项目目标、当前范围、非目标、核心约束和初始架构决定已经记录；
- V1 架构基线已经正式记录在 `docs/ARCHITECTURE.md`，包括 Skill/scripts 分工、`animation-manifest.json` 中间层、可替换渲染后端、FCPXML 回填边界和 V1 工作流；
- 已建立 `SKILL.md`、`agents/openai.yaml` 和项目入口参考契约；
- `scripts/intake_project.py` 已能只读发现工作区材料、解析 FCPXML/FCPXMLD、识别显式/隐式空缺、提取 Marker，并按证据区分旁白字幕、设计文字与歧义文字；
- `scripts/init_user_workspace.py` 已能在项目根目录幂等创建或识别用户工作目录，默认显示名为 `AfterForge`，同时保持内部 ID `fcpxml-animation-pipeline`；
- `scripts/init_user_inbox.py` 已能幂等创建或识别用户维护、Skill 只读的 `user-inbox/`，且不会创建或修改任何版本目录；
- `scripts/init_afterforge_project.py` 已能在既有 AfterForge 工作目录中一次性初始化项目级 `AGENTS.md` 和 `CLAUDE.md`：只补缺失文件、逐字节保留既有文件，并且不创建或更新 canonical `frame.md`、任何 Vn 或版本资产；
- `scripts/scaffold_hyperframes.py` 已能在项目级 canonical `frame.md` 存在且目标 Vn 尚不存在时，原子创建隔离的 HyperFrames 版本工程：版本标记接受大写 `V` 或小写 `v` 并原样保留，发现仅大小写不同的既有版本时阻塞；复制 `frame.md` 与项目字体快照，固定 HyperFrames CLI 版本，生成最小可检查结构；不调用通用 `hyperframes init`，不生成或更新项目级 `AGENTS.md`、`CLAUDE.md`，目标已存在或前置条件缺失时阻塞且不修改既有内容；
- 已实现 HyperFrames 单一布局源 adapter：manifest v2 驱动 `compositions/cues/` 唯一正式布局、独立 `compositions/motion/`、自动生成的 `compositions/review/`、`STORYBOARD.md` 与正式合成 `index.html`；`layout_lock.py` 可冻结并验证 A11 布局依赖，adapter validator 可阻止路径/ID/依赖/布局运动分叉；
- 已实现 legacy Vn 迁移器：从既有最新 animation composition 提取 canonical cue 与 inline GSAP motion，迁移前完整预检，异常时恢复 manifest/storyboard/index，并保留旧 `compositions/frames/`、`compositions/animation/` 原文件用于对照；
- 项目入口步骤 A1、A2 保留独立编号和内部职责，但面向用户连续执行，中间不单独汇报或等待确认；
- `user-inbox/` 初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录保持为空且既有 `AfterForge/` 未改变；
- 已在 Sequoia 系统盘真实项目工作区 `/Users/xiaobaimac/Movies/trumen` 完成 `AfterForge/` 与 `user-inbox/` 初始化；首次运行返回 `created`，重复运行返回 `existing`，两个目录均未预建其他内容；
- 已在同一真实项目中执行一次性 AfterForge 项目初始化：既有 `AfterForge/` 与 `user-inbox/` 原样复用，只在 `AfterForge/` 根层创建缺失的项目级 `AGENTS.md` 和 `CLAUDE.md`，未创建 canonical `frame.md` 或 Vn；
- 用户工作目录初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录内未生成其他内容；
- 入口能以 `ready`/`blocked`、blocker、warning、ambiguity 和最小问题清单表达是否具备后续分析条件；
- 当前可靠行为已通过 75 个合成工作区自动化测试，并完成 Skill 流程对照场景验证；
- 已对真实投放版本 `/Users/xiaobaimac/Movies/trumen/user-inbox/2026-08-25_V2` 执行 `--flat` intake：唯一选择 `P1-sence-01-粗剪.fcpxmld` 和 `P1-sence-01 粗剪.m4v`，识别 `P1-sence-01 脚本.docx` 为旁白证据，结果为 `ready`，无 blocker、warning 或 ambiguity；
- intake 已新增 `materials.animation_guidance`，用于独立保留用户主动提供的动画脚本或逐镜要求；存在 SRT 时不再因旁白来源已经成立而丢弃动画脚本，脚本内时码仍不具备 FCPXML 时间权威；
- 已冻结 A7 动画脚本可执行性审核：intake 仍只发现并保留可选脚本，A7 才对照口播、原画、FCPXML、产品范围和当前后端给相关 cue 写入可选 `guidanceReview`；审核不新增独立报告或用户验收，不改变 intake 状态，只有真实方向分叉或受影响 cue 无法可靠继续时才询问；
- 已冻结多原片重编 cue 的素材门槛：动画需要内部重放、重排、裁切、遮罩或多画面合成两段或以上原片时，A7 默认要求用户提供独立带余量片段，不从粗剪猜测取段和顺序；标准接受 1920×1080 H.264、匹配项目的恒定帧率和 Rec.709 SDR，最终透明交付仍为 1920×1080 ProRes 4444；
- 已冻结独立原片的权威关系：素材身份、顺序与可用内容以用户最新明确说明和实际投放文件的名称、编号顺序、可检查画面为权威，脚本素材类型默认只作参考；实际素材与用户说明一致时的类型差异记为 `agent-normalized`，只在各权威证据彼此冲突时询问；该规则不改变脚本对逐镜风格、运动或表达目的的明确要求；
- intake 已新增 `materials.animation_source_clips`：文件名使用 `01-` 等顺序前缀，或含 `animation-source`、`source-clip`、“动画素材”、“原片素材”的视频与低码粗剪参考视频确定性分流，不会制造 `ambiguous_reference_video`；带顺序前缀但包含粗剪关键词的文件仍是参考候选，该材料类型本身不改变全局 intake 状态；
- 已冻结逐镜风格优先级：项目级 `frame.md` 与视频级运动气质作为默认；用户脚本对某一镜明确指定的视觉或运动风格，在该 cue 及明确属性范围内优先，未指定部分继续继承项目默认，覆盖证据写入 `guidanceReview.notes` 并进入 `designRoute` 与 A11；
- 已将八列、三行空白、横向单页的 `assets/animation-script-template.docx` 纳入 Skill 资产：只在用户索取时向其批准位置提供副本，用户自行回填并投放；文件名可被现有 intake 识别，模板缺失、结构漂移和声音字段回归由自动测试覆盖；
- 已对真实投放版本 `/Users/xiaobaimac/Movies/trumen/user-inbox/2026-08-26_V1` 重新执行 `--flat` intake：唯一选择 `P1-sence-01.fcpxmld` 与 `P1-sence-01 粗剪.m4v`，同时把 `P1-sence-01 字幕.srt` 保留为旁白证据、`P1-sence-01 脚本.docx` 保留为动画指导，结果为 `ready`，无 blocker、warning 或 ambiguity；
- 已确认首个真实项目的生产规格：FCPXML 负责时间位置、帧率和时间基准；参考视频实际口播负责旁白措辞；用户脚本和 SRT 作为允许存在错别字的语义与对齐证据；开发审阅使用保留粗剪原声的 480p 合成预览，最终透明动画使用 1080p ProRes 4444 MOV；AfterForge 不再生成、设计、混合、交付或回填音效与音乐；
- 已冻结 V2 作为第一镜试制输入，并在 `/Users/xiaobaimac/Movies/trumen/AfterForge/2026-08-25_V2-first-scene-review` 完成一次性真实交付：包含语义对齐后的 `animation-manifest.json`、六段 HyperFrames 动画、18 条独立 48 kHz/24-bit PCM WAV 和一条 854×480、24 fps、54.083333 秒的合成审阅 MP4；
- 上述 V2 交付副本已通过 HyperFrames 完整检查：lint、runtime、layout 和 motion 均为 0 问题，31/31 文本对比度检查通过；成片重新抽帧确认六段动画均实际进入输出，V2 的 FCPXML、参考视频和脚本文档哈希保持记录一致；
- V2 用户审阅确认了新的创意验收要求：每个视频先冻结自己的整体视觉包装与统一运动气质；逐条动画的文字方案和真实文案静态关键画面合并为一次验收；`STORYBOARD.md` 只作为草稿 `animation-manifest.json` 的 HyperFrames 审阅视图；
- 已确认项目级与 Vn 级资产边界：AfterForge 根层 `AGENTS.md`、`CLAUDE.md` 只初始化一次，`frame.md` 是项目级 canonical visual spec；每个 Vn 保存 manifest、storyboard、compositions、固定构建配置和 `frame.md` 校验快照；
- 已确认并落地跨项目视觉语法路由：每条候选动画先判断主次信息功能及其与原画的主次关系，再在项目视觉规范内选择主要及可选辅助参考语言；开放索引、混合关系和自主判断规则集中记录在 `references/visual-grammar.md`；
- 视觉语法路由不新增逐条用户确认，实际结果写入草稿 manifest 的 cue 级 `designRoute`，并在既有 A11 storyboard 联合验收中暴露；只有显著改变范围、违反已确认约束或产生难以逆转后果的分叉才单独请求确认；
- 已确认 A8、A11 使用可验收性门槛：优先尽快交付用户查看，低成本自动检查只作非阻塞自检；只有 storyboard 无法打开、关键资源缺失或页面明显报错等导致用户无法验收的问题才阻塞，Agent 不代替用户完成审美验收；
- 已确认 Vn 创建不使用通用 `hyperframes init`，改由仓库控制的确定性脚手架建立最小可重渲染工程，且不得触碰项目级 Agent 文件；
- 已在真实项目 `/Users/xiaobaimac/Movies/trumen` 创建项目级 canonical `AfterForge/frame.md`，并通过确定性脚手架创建 `/Users/xiaobaimac/Movies/trumen/AfterForge/2026-08-26_V1`；A8 与 A11 已通过，A12 已按确认方案制作第 1–5、8 镜完整动画，第 6、7 镜按用户确认保留原画且不生成动画占位，并输出 854×480、24 fps、54.083333 秒的合成审阅 MP4；A13 已确认整体观感方向，删除声音制作，完成第 8 镜纯文字交替与水平线修正，并将第 3 镜的全宽揭示遮罩与原始 27 px 内缩问号排版解耦，避免裁切和位移；
- 已实现面向长期交付的双分辨率单一布局源：canonical cue 的 CSS 终态固定为项目交付尺寸，A11 storyboard 与 A12 合成预览只从同一正式 cue 生成 854×480 审阅投影，正式渲染则从自动生成的 1920×1080 delivery composition 直接输出，不使用低分辨率放大；layout lock 同时冻结 canonical cue、motion、字体、媒体、review projection 与投影规格；
- 已实现 `sync_delivery.py`、`render_animations.py` 与 `validate_delivery.py`：可确定性生成逐 cue 正式渲染入口、执行原生分辨率透明 MOV 渲染并用 ffprobe 校验 ProRes 4444、alpha、尺寸、帧率和时长；已有交付文件默认不覆盖；
- 真实 `2026-08-26_V1` 已从 854×480 canonical cue 迁移为 1920×1080 delivery-native canonical cue，第 1、2、3、4、5、8 镜共用一套正式布局，第 6、7 镜继续为 source-only；旧内容保留在 canonical cue 内的兼容 stage 中，motion 文件未改动；迁移会清除旧 lock 但通过 `layoutRevision` 保留修订基线；
- V1 迁移后的 A11/A12 审阅投影、六个 delivery composition 和 854×480 全片等价审阅 MP4 已重新生成；旧审阅与新审阅的机械比较为 SSIM 0.992823、PSNR 35.489055 dB，仅用于发现明显工程漂移，不替代用户视觉验收；
- 用户已批准迁移后的 854×480 完整动画审阅；六条 animated cue 已使用批准 hero poster 建立并验证 revision 2 layout lock，项目级 A11 状态为 approved；
- 第 3 镜已完成原生 1920×1080 alpha 工程探针，六条正式动画随后全部在 composition 原生尺寸直接渲染到 `delivery/prores4444/`；逐条均通过 ProRes 4444、`yuva444p12le` alpha、1920×1080、24 fps 和时长校验，正式结果记录在 `delivery/render-ledger.json`；
- Terra 早期生成的 854×480 捕获后放大产物未删除，已从正式文件名隔离到 V1 的 `delivery/quarantine/terra-upscaled-20260830/`，对应 worktree 的 Git 状态未触碰；
- 已实现正式 FCPXML 交付后端：`register_delivery_assets.py` 只在重新探测实际 MOV 后向主 manifest 注册稳定 `deliveryAsset`；`fcpxml_timing.py`、`inject_fcpxml.py`、`build_delivery_package.py`、`validate_fcpxml_package.py` 与 `compare_fcpxml_roundtrip.py` 分别承担有理数时间/lane、Project 克隆与 connected clips 注入、唯一协议版本指纹与原子发布、完整工程验证和 FCP 再导出语义比较；render ledger 仍只作注册证据，不成为包构建输入；
- 真实 `2026-08-26_V1` 已将第 1、2、3、4、5、8 镜共六条已验证透明 MOV 注册进 manifest，第 6、7 镜保持 `source-only` 且无占位；已在项目级 `AfterForge/` 根层发布 `AfterForge__2026-08-26_V1__d-2c692941c719d02a48374ebc2ceaba53c973428e5376da465cd0567724e708f8.fcpxmld`，包内只有 `Info.fcpxml` 与六条 MOV，通过源哈希、A11 lock、媒体哈希、时间/lane、引用、源 sequence 不变性、FCPXML 1.14 DTD 和第二次同指纹完整复用验证；
- 用户已将上述正式包实际导入 Final Cut Pro，确认时间线与导出视频均无问题；FCP 再导出的 `round-trip-AfterForge__2026-08-26_V1__00-片头.fcpxmld` 已通过语义 round-trip，六条动画身份、connected clip 精确时长与粗略位置、纯视频属性、source-only 状态、主故事线和总时长均保持有效，`deliveryProtocolVersion = 1` 的首个真实 FCP 交付基线完整成立；
- 首次 round-trip 证实 FCP 会重排 resource ID、改写媒体路径前缀与等价有理数，并可能产生微秒以下 `timeMap` 规范化和不超过一帧的 MOV resource 物理尾差；比较器已在不放宽 connected clip 时长、语义位置、音频属性或主故事线约束的前提下规范化这些非语义差异；
- 已移除旧版 HyperFrames marketplace plugin，并在软件重启后确认源码安装的新版 HyperFrames 技能可用；
- Git 仓库已经初始化。

## 尚未开始

- 尚未实现参考视频内容理解或语音转写；
- 尚未把本次人工完成的旁白对齐和初始 `animation-manifest.json` 内容生成整理为仓库内可复用的确定性流水线；HyperFrames 单一布局源装配、review projection、layout lock、adapter 验证和旧 Vn 迁移已经脚本化；
- 已确认将审核拆为 Storyboard 静态样式、480p Demo 运动和原生渲染显式授权三个硬门，设计契约记录于 `docs/superpowers/plans/2026-09-02-review-gates-design.md`；统一 Storyboard 评论页、逐镜/逐静帧持久化 comment、Demo 时间码/时间段 comment、审核失效传播及 renderer 授权门尚未实现；
- 当前没有 build 或 lint 命令。

## 已知问题与阻塞

当前没有已知技术阻塞。V2 仍是未迁移的一次性旧结构，不代表正式资产布局。双分辨率单一布局源、审阅投影、delivery composition、单调递增布局锁、正式渲染驱动、媒体注册、FCPXML 注入、扁平包发布、自动交付验证和协议级 round-trip 已经具备确定性实现；真实 V1 已完成 revision 2 批准、六条原生透明交付渲染、正式 `.fcpxmld`、FCP 实际导入与再导出验证。参考视频理解和初始 manifest 内容生成仍待实现。新确认的三段审核契约尚未实现：当前 `render_animations.py` 仍只检查 adapter 与 layout lock，不能证明 480p Demo 已通过或用户已单独授权，因此在门禁补齐前不得据此自动进入新的原生渲染。

## 下一步

下一步由用户先审查并本地 commit 当前文档与既有 V/v 兼容改动。获得继续实现的授权后，按 TDD 依次补齐 Storyboard 持久化评论页、480p Demo 时间码评论与审批、失效传播和原生渲染授权硬门，再同步 `SKILL.md`、README、manifest schema、adapter reference 与验证命令。实现完成前，当前 invocation 停留在 480p Demo 审核范围，不启动原生通道视频渲染。
