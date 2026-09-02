# AfterForge Workflow Stage Contract

> 本文件由 `workflow-stage-contract.json` 确定性生成，请勿手工修改。

Contract version：`1.0.0`
Canonical SHA-256：`781e2fb6e56f2316674d616abd438cec26959559b473275d41389377c9bffaca`

## A-stage：分析、创意审核与授权

Analysis, Creative Review & Authorization；稳定性：`stable`。

| ID | Formal name | 中文名称 | 稳定职责 | 用户含义 | 用户动作 |
|---|---|---|---|---|---|
| A1 | Workspace Boundary Initialization | 工作区边界初始化 | 创建或识别 AfterForge 与 user-inbox 边界。 | 与 A2 连续执行，不形成单独停点。 | `none` |
| A2 | AfterForge Project Initialization | AfterForge 项目初始化 | 检查并按需初始化项目级 Agent 入口文件。 | 不触碰 Vn、用户输入或视觉规范。 | `none` |
| A3 | Invocation Target Selection | Invocation 目标选择 | 绑定本轮正式 invocation 使用的既有 user-inbox Vn。 | 用户明确指定版本，Agent 不猜最新版本。 | `selection` |
| A4 | Input Discovery | 输入发现 | 只读发现时间线、参考视频、旁白证据与可选创作材料。 | 复用已有材料，不要求重复提供。 | `none` |
| A5 | Intake Readiness | 入口就绪判断 | 判断必要输入是否存在且可以唯一确定。 | 只询问真正阻塞继续的问题。 | `conditional-input` |
| A6 | Timeline & Evidence Analysis | 时间线与证据分析 | 解析规格、时间线、素材引用、空缺和文字证据。 | 形成后续动画判断的事实基础。 | `none` |
| A7 | Animation Guidance & Cue Feasibility Audit | 动画指导与 Cue 可执行性审核 | 对齐口播与时间线，审核可选脚本、素材需求、逐镜风格覆盖及 cue 可执行性。 | 遇到会改变镜头含义或无法可靠执行的模糊项时由用户澄清。 | `conditional-clarification` |
| A8 | Visual Direction Review | 视觉方向审核 | 确认项目视觉包装与本视频统一运动气质。 | 用户批准本视频后续设计采用的整体方向。 | `review-approval` |
| A9 | Vn Production Scaffold | Vn 制作脚手架 | 创建隔离 Vn 并冻结当时的 frame.md 与字体快照。 | 建立可独立检查和重渲染的版本工程。 | `none` |
| A10 | Cue Design & Static Build | Cue 设计与静态构建 | 完成设计路由、素材落位和 canonical cue 静态终态。 | 准备进入正式 Storyboard 的真实静态设计。 | `none` |
| A11 | Storyboard Static Review | Storyboard 静态审核 | 逐 cue 收集静态 comment，并记录与当前布局证据绑定的用户批准。 | 用户审核排版、文字、素材、构图、比例、颜色和材质；可一次批准所有合格 cue。 | `review-approval` |
| A12 | Motion Build & Demo Generation | 运动构建与 Demo 生成 | 在已批准布局上实现 motion，并生成绑定输入的 480p Demo。 | 本阶段只形成动画小样，不代表用户已批准运动。 | `none` |
| A13 | Demo Motion Review | Demo 运动审核 | 收集按播放器时间点或可选时间段定位、可同时声明静态与运动影响范围的 comment，并记录当前完整 Demo 的视频级批准。 | 用户在同一 Review 上下文完整表达意见，并亲自选择静态、运动或二者影响范围。 | `review-approval` |
| A14 | Native Render Authorization | 原生渲染授权 | 记录与当前 A11、A13、layout lock 和输入哈希绑定的独立原生渲染授权。 | Demo 通过后，用户另行明确授权原生 ProRes 4444 渲染。 | `authorization` |

## D-stage：工程交付生命周期

Delivery Lifecycle；稳定性：`evidence-evolving`。

| ID | Formal name | 中文名称 | 稳定职责 | 用户含义 | 用户动作 |
|---|---|---|---|---|---|
| D1 | Delivery Readiness Verification | 交付就绪验证 | 验证 A11、A13、A14、layout lock、依赖与输入哈希均有效。 | 确认当前获批状态可以进入正式交付。 | `none` |
| D2 | Native Render & Validation | 原生渲染与验证 | 原生渲染 ProRes 4444，并在正式发布 MOV 前验证 codec、alpha、尺寸、帧率和时长。 | 生成通过工程校验的正式透明动画素材。 | `none` |
| D3 | Delivery Asset Registration | 交付资产注册 | 重新探测实际 MOV，并将稳定媒体事实注册为 deliveryAsset。 | 把已验证素材登记为 FCPXMLD 构建输入。 | `none` |
| D4 | FCPXMLD Build, Validation & Publication | FCPXMLD 构建、验证与发布 | 完成 fingerprint、Project 克隆、connected clip 注入、完整验证和非覆盖式原子发布。 | 形成可导入 Final Cut Pro 的新交付包。 | `none` |
| D5 | Final Cut Pro Import Acceptance | Final Cut Pro 导入验收 | 记录用户对实际 FCP 导入、媒体在线、alpha、可编辑性和时间线结果的验收。 | 用户亲自在 Final Cut Pro 中确认交付结果。 | `acceptance` |
| D6 | Round-trip Verification | Round-trip 回归验证 | 在首次 V1 或交付协议语义变化时比较 FCP 再导出结果。 | 必要时提供 FCP 再导出文件，验证交付语义可往返保持。 | `conditional-artifact` |

## 条件适用

- `D6`：`required-for-first-v1-or-delivery-protocol-change`

## 使用规则

- Stage ID 在同一 contract version 下不得改义或复用。
- Vn 保存自己的实例 evidence，不复制本合同定义。
- 旧 contract version 的合法 evidence 可以作为其原语义下的历史事实保留；只有未知、损坏或与当前所需 stage semantics 不兼容的 evidence 才不得用于当前判断。
- 当前阶段由实际 evidence 确定性推导，不在 manifest 中手工维护单值 `currentStage`。
