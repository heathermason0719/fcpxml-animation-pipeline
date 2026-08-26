# 当前状态

## 已可靠成立

- 仓库基础目录和权威文档结构已经按全局项目治理规则建立；
- 项目目标、当前范围、非目标、核心约束和初始架构决定已经记录；
- V1 架构基线已经正式记录在 `docs/ARCHITECTURE.md`，包括 Skill/scripts 分工、`animation-manifest.json` 中间层、可替换渲染后端、FCPXML 回填边界和 V1 工作流；
- 已建立 `SKILL.md`、`agents/openai.yaml` 和项目入口参考契约；
- `scripts/intake_project.py` 已能只读发现工作区材料、解析 FCPXML/FCPXMLD、识别显式/隐式空缺、提取 Marker，并按证据区分旁白字幕、设计文字与歧义文字；
- `scripts/init_user_workspace.py` 已能在项目根目录幂等创建或识别用户工作目录，默认显示名为 `AfterForge`，同时保持内部 ID `fcpxml-animation-pipeline`；
- `scripts/init_user_inbox.py` 已能幂等创建或识别用户维护、Skill 只读的 `user-inbox/`，且不会创建或修改任何版本目录；
- `user-inbox/` 初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录保持为空且既有 `AfterForge/` 未改变；
- 已在 Sequoia 系统盘真实项目工作区 `/Users/xiaobaimac/Movies/trumen` 完成 `AfterForge/` 与 `user-inbox/` 初始化；首次运行返回 `created`，重复运行返回 `existing`，两个目录均未预建其他内容；
- 用户工作目录初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录内未生成其他内容；
- 入口能以 `ready`/`blocked`、blocker、warning、ambiguity 和最小问题清单表达是否具备后续分析条件；
- 第一阶段行为已通过 22 个合成工作区自动化测试，并完成 Skill 流程对照场景验证；
- 已对真实投放版本 `/Users/xiaobaimac/Movies/trumen/user-inbox/2026-08-25_V2` 执行 `--flat` intake：唯一选择 `P1-sence-01-粗剪.fcpxmld` 和 `P1-sence-01 粗剪.m4v`，识别 `P1-sence-01 脚本.docx` 为旁白证据，结果为 `ready`，无 blocker、warning 或 ambiguity；
- intake 已新增 `materials.animation_guidance`，用于独立保留用户主动提供的动画脚本或逐镜要求；存在 SRT 时不再因旁白来源已经成立而丢弃动画脚本，脚本内时码仍不具备 FCPXML 时间权威；
- 已对真实投放版本 `/Users/xiaobaimac/Movies/trumen/user-inbox/2026-08-26_V1` 重新执行 `--flat` intake：唯一选择 `P1-sence-01.fcpxmld` 与 `P1-sence-01 粗剪.m4v`，同时把 `P1-sence-01 字幕.srt` 保留为旁白证据、`P1-sence-01 脚本.docx` 保留为动画指导，结果为 `ready`，无 blocker、warning 或 ambiguity；
- 已确认首个真实项目的生产规格：FCPXML 负责时间位置、帧率和时间基准；参考视频实际口播负责旁白措辞；用户脚本和 SRT 作为允许存在错别字的语义与对齐证据；开发审阅使用 480p 合成预览，最终透明动画使用 1080p ProRes 4444 MOV，音效和音乐使用逐条或独立的 48 kHz、24-bit PCM WAV；
- 已冻结 V2 作为第一镜试制输入，并在 `/Users/xiaobaimac/Movies/trumen/AfterForge/2026-08-25_V2-first-scene-review` 完成一次性真实交付：包含语义对齐后的 `animation-manifest.json`、六段 HyperFrames 动画、18 条独立 48 kHz/24-bit PCM WAV 和一条 854×480、24 fps、54.083333 秒的合成审阅 MP4；
- 上述 V2 交付副本已通过 HyperFrames 完整检查：lint、runtime、layout 和 motion 均为 0 问题，31/31 文本对比度检查通过；成片重新抽帧确认六段动画均实际进入输出，V2 的 FCPXML、参考视频和脚本文档哈希保持记录一致；
- V2 用户审阅确认了新的创意验收要求：每个视频先冻结自己的整体视觉包装与统一运动气质；逐条动画的文字方案和真实文案静态关键画面合并为一次验收；`STORYBOARD.md` 只作为草稿 `animation-manifest.json` 的 HyperFrames 审阅视图；
- 已确认项目级与 Vn 级资产边界：AfterForge 根层 `AGENTS.md`、`CLAUDE.md` 只初始化一次，`frame.md` 是项目级 canonical visual spec；每个 Vn 保存 manifest、storyboard、compositions、固定构建配置和 `frame.md` 校验快照；
- 已确认 Vn 创建不使用通用 `hyperframes init`，改由仓库控制的确定性脚手架建立最小可重渲染工程，且不得触碰项目级 Agent 文件；
- 已移除旧版 HyperFrames marketplace plugin，并在软件重启后确认源码安装的新版 HyperFrames 技能可用；
- Git 仓库已经初始化。

## 尚未开始

- 尚未实现参考视频内容理解或语音转写；
- 尚未把本次人工完成的旁白对齐、`animation-manifest.json` 生成、HyperFrames 工程生成和音频生成整理为仓库内可复用的确定性流水线；
- 尚未实现一次性 AfterForge 项目初始化器，以及不调用通用 `hyperframes init` 的 Vn `scaffold_hyperframes.py`；
- 尚未执行 1080p 透明 ProRes 4444 最终渲染、FCPXML 回填或 Final Cut Pro 导入验证；
- 当前没有 build 或 lint 命令。

## 已知问题与阻塞

当前没有已知技术阻塞。V2 的 480p 合成审阅证明一次性试制路径可行，也暴露了实施前缺少视觉包装、运动气质和静态关键画面合并验收的问题；其内容和观感不能作为已确认方向。现有 V2 工作目录仍是一次性旧结构：HyperFrames 通用 scaffold 在 V2 根层生成了内容相同的 `AGENTS.md` 和 `CLAUDE.md`，AfterForge 根层尚无项目级 canonical `frame.md`；该目录不代表后续正式资产布局，本轮未迁移或删除其中内容。当前结果不等于仓库已经具备自动化流水线；1080p 透明转码、FCPXML 回填和 Final Cut Pro 导入仍待实现与验证。

## 下一步

先实现并测试一次性 AfterForge 项目初始化与确定性 Vn HyperFrames 脚手架，证明创建多个 Vn 不会生成或更新根层 `AGENTS.md`、`CLAUDE.md` 和 canonical `frame.md`，且每版 frame 快照、固定配置、compositions 和本地素材可以独立检查与重渲染。随后以 `2026-08-25_V3` 作为下一轮正式测试输入，用 `--flat` 重跑 intake，验证 SRT 辅助对齐效率和新的三道确认门槛：整体视觉包装与运动气质、合并 storyboard 验收、480p 动画与声音预览。V2 不进入 1080p 最终渲染和 FCPXML 回填。
