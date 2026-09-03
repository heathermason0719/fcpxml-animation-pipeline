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
- `scripts/scaffold_hyperframes.py` 已能在项目级 canonical `frame.md` 存在且目标 Vn 尚不存在时，原子创建隔离的 HyperFrames 版本工程：版本标记接受大写 `V` 或小写 `v` 并原样保留，发现仅大小写不同的既有版本时阻塞；创建时使用一次性隔离 npm cache 解析官方当前 HyperFrames 版本或接受显式精确版本，在临时目录通过兼容性检查后固定进 managed package scripts 并记录不可变创建来源；不依赖仓库硬编码默认值，不调用通用 `hyperframes init`，不生成或更新项目级 `AGENTS.md`、`CLAUDE.md`，目标已存在或前置条件缺失时阻塞且不修改既有内容；
- 已实现 HyperFrames 单一布局源 adapter：manifest v2 驱动 `compositions/cues/` 唯一正式布局、独立 `compositions/motion/`、自动生成的 `compositions/review/`、`STORYBOARD.md` 与正式合成 `index.html`；`layout_lock.py` 可冻结并验证 A11 布局依赖及产生审核帧的精确 runtime pin，adapter validator 可阻止路径/ID/依赖/布局运动或 runtime 分叉；
- 已实现 legacy Vn 迁移器：从既有最新 animation composition 提取 canonical cue 与 inline GSAP motion，迁移前完整预检，异常时恢复 manifest/storyboard/index，并保留旧 `compositions/frames/`、`compositions/animation/` 原文件用于对照；
- 项目入口步骤 A1、A2 保留独立编号和内部职责，但面向用户连续执行，中间不单独汇报或等待确认；
- `user-inbox/` 初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录保持为空且既有 `AfterForge/` 未改变；
- 已在 Sequoia 系统盘真实项目工作区 `/Users/xiaobaimac/Movies/trumen` 完成 `AfterForge/` 与 `user-inbox/` 初始化；首次运行返回 `created`，重复运行返回 `existing`，两个目录均未预建其他内容；
- 已在同一真实项目中执行一次性 AfterForge 项目初始化：既有 `AfterForge/` 与 `user-inbox/` 原样复用，只在 `AfterForge/` 根层创建缺失的项目级 `AGENTS.md` 和 `CLAUDE.md`，未创建 canonical `frame.md` 或 Vn；
- 用户工作目录初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录内未生成其他内容；
- 入口能以 `ready`/`blocked`、blocker、warning、ambiguity 和最小问题清单表达是否具备后续分析条件；
- 当前可靠行为已通过 149 个自动化测试（含使用 Node.js 执行实际 Review 页面脚本的行为回归），并完成 Skill 流程对照场景验证；
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
- 已实现版本化 Workflow Stage Contract：`references/workflow-stage-contract.json` 是 A1–A14 与 D1–D6 的唯一 machine canonical，Markdown 完整表由脚本确定性生成；旧 contract version 不因版本旧而自动失效，resolver 只使用当前语义兼容 evidence；
- 已实现不保存 `currentStage` 的 `workflow_status.py`：从 layout lock、Demo/输入哈希、comment、用户批准、A14 授权、render ledger、deliveryAsset、FCPXMLD、FCP 验收和 round-trip evidence 推导活动上下文、阻塞点、下一阶段与完成集合；
- 已实现绑定单个 Vn 的仓库级 Review：A11 cue 卡按对应旁白、锁定的主审帧/必要辅助帧、cue 级 `finalAnimationDescription`、逐帧 comment 与批准操作组织，不展示设计讨论历史；初始设计或后续 Review / 聊天反馈若仍有会实质改变最终呈现的合理解释分叉，Agent 必须在修改受影响 cue 前先用一个聚焦问题澄清，不能把已有批准、赶时间、低成本返工或后续审核当作自行选义的理由；明确结果内的实现细节不重复询问，澄清不新增批准门，过程不写入最终动画说明；comment 保存后明确提示成功，只撤销批准证据并保留被评论的静帧，实际受审文件变化才由哈希校验判定 layout lock 失效；缺少最终动画说明、任一审核帧哈希失效或仍有开放 comment 时拒绝批准，批量批准仍保存逐 cue evidence；A13 从播放器自动绑定时间与 cue，可选持续范围，一条 comment 由用户选择 `static`、`motion` 或二者影响范围；静态范围重开受影响 A11 并向下失效，motion-only 保留有效 A11，Demo 页面上下文不被强制切走；同时保留视频级批准、独立 A14 原生渲染授权、D5 FCP 导入验收和 manifest SHA 并发保护；
- 已确认 Review shell 与项目级 canonical `frame.md`、Vn `frame.md` 快照解耦：项目视觉规范只影响被审核的动画内容；当前 shell 暂时冻结为仓库级 Review UI 基线，后续 UI/UX 调整必须显式进行，不随项目视觉规范变化；
- 已修复 Demo 拖动与刷新：Review 媒体响应支持单段 byte Range、HEAD 与 416，并分块读取；状态和资源禁用旧缓存，刷新显示进行中、成功时间或失败原因，按 Demo 哈希识别同路径新视频，未变视频保留播放位置。当前真实 Vn 已在 Codex 内置浏览器验证正向/反向拖动、画面与 cue 同步、刷新反馈及播放位置保持；manifest 与 Demo 文件哈希未变，本次未提交 comment、批准或推进 workflow；
- 已修复 Demo 区间控件与提交模式不一致：未启用持续范围时真正隐藏端点控件，捕获端点同时启用区间模式，提交按钮明确区分时间点/区间，缺失或倒序端点不提交；评论列表标明区间及两个端点，刷新后仍保留。新增四项客户端回归均先在旧实现失败、修复后通过；当前真实页面已验证开关、端点捕获、刷新与显示，未向真实 Vn 添加测试评论。用户确认 `A13-C0004` 起点约 11 秒、终点 14.420 秒，已在同一 comment 恢复范围，A13 evidence 保留近似起点与修正来源，原正文、其他评论和 approval 不变；
- 已实现显式 legacy Vn 合同迁移：原样保留旧 `reviews`，不把旧 approval 升格为新合同批准；可核验且输入未变的旧 480p Demo 可作为 A12 artifact evidence 保留；
- 已实现 HyperFrames runtime 最小治理：`package.json` 统一精确 pin 是 Vn 当前运行版本唯一权威，`meta.json` 分离不可变创建版本和显式迁移历史；普通恢复不再探测或采用 latest，`migrate_hyperframes_runtime.py` 才能迁移既有 Vn，并逐项记录兼容性检查与审核 evidence 的 preserved、rebound、invalidated 结果；runtime pin 已进入 A11 lock、cue approval 与 A12 下游输入指纹；
- 已将原生 renderer、资产注册器、FCPXMLD builder 和 round-trip registrar 接入 D-stage 哈希链：A11/A13/A14 或输入不匹配时在启动 renderer 前阻断，后续 D2–D6 不以产物文件单独存在判断完成；
- 首次 round-trip 证实 FCP 会重排 resource ID、改写媒体路径前缀与等价有理数，并可能产生微秒以下 `timeMap` 规范化和不超过一帧的 MOV resource 物理尾差；比较器已在不放宽 connected clip 时长、语义位置、音频属性或主故事线约束的前提下规范化这些非语义差异；
- 已移除旧版 HyperFrames marketplace plugin，并在软件重启后确认源码安装的新版 HyperFrames 技能可用；
- 真实 `2026-09-01_v1` 已由用户在 Review 完成 A13 整片批准和独立 A14 授权，十条 A11 comment、八条 A13 comment 均为 `accepted`。随后在 pin `0.8.26` 下完成五条原生 1920×1080、24 fps、ProRes 4444 MOV，逐条通过 alpha、精确帧数、时长、无音轨和完整解码校验；第 4 镜长素材持续播放抽检通过，原生输出抽帧与获批单镜预览对照保存在 `qa/delivery-native-20260903/verification.json` 及同目录图片。D3 注册和 D4 构建后发布根层平铺包 `AfterForge__2026-09-01_v1__d-95d8b8d34ca7d8931f3087cf3fbe84d0e06973ab85c1c95239d2325a47e62acc.fcpxmld`，包内只有 `Info.fcpxml` 与五条 MOV；源 XML 不变、媒体哈希、时间/lane、引用、sequence 不变性、FCPXML 1.14 DTD 与第二次同指纹完整复用验证通过，`deliveryProtocolVersion = 1` 未变。149 项仓库回归再次通过，HyperFrames check 为 0 错误/警告、1 条已接受镜头重叠的信息级遮挡提示，15/15 对比度检查通过；用户随后完成 D5 实际导入验收，D6 本轮按用户明确决定不要求执行（未执行，不记为通过）；
- Git 仓库已经初始化。

2026-09-03 本轮复盘的两项规则收尾已落入 `SKILL.md` 及现有文档：歧义澄清覆盖后续反馈修改；新运动默认强调可感知缓动、剪辑空间和有目的的持续运动，不固定秒数或禁止所有漂浮。真实项目 canonical `AfterForge/frame.md` 更新为 v3，仅修订运动与反馈澄清规则；已交付 `2026-09-01_v1` 的 v2 快照、manifest、批准和媒体保持不变。未改 Review/runtime/schema，也未实施第三项 Handles / 初始使用子区间改造。

## 尚未开始

- 尚未实现参考视频内容理解或语音转写；
- 尚未把本次人工完成的旁白对齐和初始 `animation-manifest.json` 内容生成整理为仓库内可复用的确定性流水线；HyperFrames 单一布局源装配、review projection、layout lock、adapter 验证和旧 Vn 迁移已经脚本化；
- 当前真实 `2026-09-01_v1` 已完成 A1–A14、D1–D5；D6 按用户明确决定为本轮不适用，新 D6 evidence 登记链尚未在本轮执行真实 round-trip。runtime 保持精确 pin `0.8.26`，创建版本仍为 `0.8.16`，既有 `HF-M0001` 记录不变。当前五镜 lock revision 为 4/5/5/6/5，七张审核帧有效；正式渲染未改动已批准 cue、motion、时间位置或 Demo。A12 仍为 `previews/2026-09-01_v1-A12-feedback-v2.mp4`，SHA-256 `783e9926a6e39d111f556d354f6d49b10088708f4bebb76d860a31afe26c4583`；第 2 镜补充完整预览与第 4 镜已确认替换版的单镜审核证据继续保留。静态备份位于 `qa/a13-feedback-20260903-v1/`，此前运动、渲染、音画核验及注册证据位于 `qa/a12-feedback-20260903-v2/`，不把历史 `awaiting-user` 实现记录当作当前批准状态。
- 当前没有 build 或 lint 命令。

## 已知问题与阻塞

第 4 镜 CAM05 遗漏已按用户确认接入：`previews/2026-09-01_v1-cue04-cam05-fixed-480p-v3.mp4`（854×480、24 fps、12.5 秒，SHA-256 `d35380248de7631cbbab1dd584bd3b4ef1d35306efab44a9843ee03a026c61f6`）已获用户单镜确认，正式 cue 与该获批候选逐字节一致，大 PGM 从长素材本地 6.56 秒原速接续播放；第 5 镜、全部运动和时间位置未改。第 4 镜媒体依赖已加入 lock，主审帧直接取获批 MP4 的本地 7.5 秒第 180 帧；A11 revision 更新为 6，并保存聊天确认与单镜哈希的明确来源，其他四镜 lock/approval 和全部 comment 原样保留。当前输入指纹为 `d95628f66631b6c246bb24b188e37f83c1bb55ca2c2c60ec4a9f236f2dd09af1`。按用户要求未重渲整片：A12 的 `reviewBasis` 保留整片实际生成时的旧输入指纹、原始生成 evidence 和单镜替换确认，当前审核绑定以该已核验局部差异接续；不能称旧整片已包含修复画面。这是本轮人工核验的局部替换记录，不是新 artifact-set validator，通用自动补审/集合指纹架构仍未实施。接入前备份、四项接入校验及隔离的失效/硬门负向校验保存在 `qa/cue04-cam05-replacement-v3/`；之后用户已亲自在 Review 完成 A13 总批准与 A14 独立授权，Agent 未代点批准。

当前真实 Vn 的 resolver 为 `blockingStage=null`、`nextEligibleStage=null`；A1–A14、D1–D5 已完成且 evidence 有效，D6 为 `not-applicable`，不进入 `completedStages`。用户确认本轮临时采用完整时长一致摆放：第 2 镜 10.5 秒、第 4 镜 12.5 秒，原时间线起点不动，允许 Demo 与 FCPXML 全长放置产生重叠；整片中被后镜遮住的完整动作通过单镜小样补审，不将已接受重叠冒充新的阻塞。原参考区间及调整依据保留在 cue notes，源 XML 未改。不实现 Handles、sourceIn、初始使用子区间或新 artifact-set 门禁；该架构改造推迟到本轮闭环、合并后另开分支。2026-09-03 用户明确决定本轮不回导：实际导入的可见时间线无问题，既有 `deliveryProtocolVersion = 1` 已有真实往返基线，本轮输出协议未变。因此仅将当前 Vn 的 `roundTripRequired` 从 `true` 改为 `false`，不生成 D6 通过 evidence，其他 manifest 内容原样保留。本轮按已确认适用范围完成交付验收；不能据此宣称新 D6 登记链经过本轮真实验证。后续实施初始使用子区间、改变 XML 时间表达时，需要重新执行 round-trip。迁移器目前仍无条件写入 `roundTripRequired=true`，条件适用规则与默认值的差异留待复盘，不在本次状态收尾中修改生产代码。

## 下一步

本轮交付复盘及已确认的两项规则修订已完成；下一步在用户要求时检查合并范围并完成合并前回归，D6 本轮未执行和条件默认值差异继续如实保留。当前 `codex/workflow-stage-contract` feature branch/worktree 保持不变，commit、push、merge 需用户当轮明确授权。待用户确认合并且 main 核验妥当后，再从 main 新建分支实施已放到桌面 INBOX 的 Handles / 完整素材与初始使用窗口解耦计划及冒烟，不提前在当前分支施工。
