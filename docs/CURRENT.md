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
- `scripts/scaffold_hyperframes.py` 已能在项目级 canonical `frame.md` 存在且目标 Vn 尚不存在时，原子创建隔离的 HyperFrames 版本工程：复制 `frame.md` 与项目字体快照，固定 HyperFrames CLI 版本，生成最小可检查结构；不调用通用 `hyperframes init`，不生成或更新项目级 `AGENTS.md`、`CLAUDE.md`，目标已存在或前置条件缺失时阻塞且不修改既有内容；
- 已实现 HyperFrames 单一布局源 adapter：manifest v2 驱动 `compositions/cues/` 唯一正式布局、独立 `compositions/motion/`、自动生成的 `compositions/review/`、`STORYBOARD.md` 与正式合成 `index.html`；`layout_lock.py` 可冻结并验证 A11 布局依赖，adapter validator 可阻止路径/ID/依赖/布局运动分叉；
- 已实现 legacy Vn 迁移器：从既有最新 animation composition 提取 canonical cue 与 inline GSAP motion，迁移前完整预检，异常时恢复 manifest/storyboard/index，并保留旧 `compositions/frames/`、`compositions/animation/` 原文件用于对照；
- 项目入口步骤 A1、A2 保留独立编号和内部职责，但面向用户连续执行，中间不单独汇报或等待确认；
- `user-inbox/` 初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录保持为空且既有 `AfterForge/` 未改变；
- 已在 Sequoia 系统盘真实项目工作区 `/Users/xiaobaimac/Movies/trumen` 完成 `AfterForge/` 与 `user-inbox/` 初始化；首次运行返回 `created`，重复运行返回 `existing`，两个目录均未预建其他内容；
- 已在同一真实项目中执行一次性 AfterForge 项目初始化：既有 `AfterForge/` 与 `user-inbox/` 原样复用，只在 `AfterForge/` 根层创建缺失的项目级 `AGENTS.md` 和 `CLAUDE.md`，未创建 canonical `frame.md` 或 Vn；
- 用户工作目录初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录内未生成其他内容；
- 入口能以 `ready`/`blocked`、blocker、warning、ambiguity 和最小问题清单表达是否具备后续分析条件；
- 当前可靠行为已通过 38 个合成工作区自动化测试，并完成 Skill 流程对照场景验证；
- 已对真实投放版本 `/Users/xiaobaimac/Movies/trumen/user-inbox/2026-08-25_V2` 执行 `--flat` intake：唯一选择 `P1-sence-01-粗剪.fcpxmld` 和 `P1-sence-01 粗剪.m4v`，识别 `P1-sence-01 脚本.docx` 为旁白证据，结果为 `ready`，无 blocker、warning 或 ambiguity；
- intake 已新增 `materials.animation_guidance`，用于独立保留用户主动提供的动画脚本或逐镜要求；存在 SRT 时不再因旁白来源已经成立而丢弃动画脚本，脚本内时码仍不具备 FCPXML 时间权威；
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
- 真实 `2026-08-26_V1` 已完成单一布局源迁移等价性验收：第 1、2、3、4、5、8 镜的批准 hero 截图保存在 `approvals/a11/`，六个 animated cue 均建立 revision 1 SHA-256 layout lock 并通过验证，第 6、7 镜继续为 source-only；
- 已移除旧版 HyperFrames marketplace plugin，并在软件重启后确认源码安装的新版 HyperFrames 技能可用；
- Git 仓库已经初始化。

## 尚未开始

- 尚未实现参考视频内容理解或语音转写；
- 尚未把本次人工完成的旁白对齐和初始 `animation-manifest.json` 内容生成整理为仓库内可复用的确定性流水线；HyperFrames 单一布局源装配、review projection、layout lock、adapter 验证和旧 Vn 迁移已经脚本化；
- 尚未执行 1080p 透明 ProRes 4444 最终渲染、FCPXML 回填或 Final Cut Pro 导入验证；
- 当前没有 build 或 lint 命令。

## 已知问题与阻塞

当前没有已知技术阻塞。V2 仍是未迁移的一次性旧结构，不代表正式资产布局。新单一布局源结构已经具备确定性生成和验证能力，真实 V1 的 A11 ground truth 与六个 layout lock 已成立。参考视频理解、初始 manifest 内容生成、1080p 透明转码、FCPXML 回填和 Final Cut Pro 导入仍待实现与验证。

## 下一步

下一项是为六条已锁定 animated cue 执行 1080p 透明渲染和 ProRes 4444 转换，随后实现并验证 FCPXML 回填与 Final Cut Pro 导入。
