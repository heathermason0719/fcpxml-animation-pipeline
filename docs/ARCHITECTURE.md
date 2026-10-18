# 架构

2.2 的概念图片是生产前的独立设计记录：`creativeObjects[].concept` 保存当前轮次、推荐／确认稿及决定引用，`concepts[]` 保存不可变图片、来源与内容快照。新稿追加，旧反馈按 conceptId、复制来源链和产品对象解析。推荐选择不建立确认；未确认当前轮用 propose，select 在需要改稿／历史重用时原子创建新轮候选，保留 `copiedFromConceptId`，不改旧图片或 round。已确认后换图需要有来源的明确用户改选；普通技术修改保留确认，图片缺失要求恢复原字节。概念模块准备 bytes，现有 update 事务负责发布／回滚；jobs snapshot 携带图片依据并在原 `_spec` 调用点复核。媒体缓存依赖实际制作源，不因浏览或单场审阅进度改变。
## 工作对象与权威

新版是 manifest 3.0 / work model 2.2.0 / delivery protocol 3。`references/work-model-contract.json` 定义操作和词汇；`animation-manifest.json` 是单个制作版本生产事实的唯一入口。系列 `工程/project.json` 只记录稳定系列/集/版本身份、路径注册和经验证的协议基线。

`brief` 保存本集理解与论证段落，`cues` 保存具体表达源、依赖及有理数摆放。Cue 的 `contentContext` 分别记录 narration/screenText 的 present、none 或 unknown；实际文本仍只在既有 Cue 或关联 brief 段落中，none 保存 text/reference 依据。`artifacts` 保存实际产物 SHA、生成输入、全局覆盖范围和完整性；`reviewSets` 绑定完整小样与必要的重叠 Cue 补审；`feedback` 保存原话、位置、来源、澄清及处理；`sceneReviews` 保存绑定实际 Storyboard／视频输入的单场审阅进度，不是批准或生产依据；`decisions` 单独保存有来源的用户决定；`deliveries` 绑定不可变包及快照。反馈冲突、非空最终说明、技术上的当前 board 与历史 `firstConfirmed` 是分别核验的事实，互不替代。执行任务不保存批准权威。

旧 schema 2.0 位于 `references/legacy/animation-manifest-v2.schema.json`；Stage Contract 1.0.0 与原阶段语义不变。旧生产实现的解释见 [legacy 架构](../references/legacy/architecture-v2.md)，仅在读取历史合同或显式旧工具维护时加载。新版不调用阶段 resolver。

## 布局与边界

```text
AfterForge/
  AGENTS.md, CLAUDE.md                缺失时创建，已有文件不覆盖
  交付/<集名>-DNNNN/                 同级普通 XML 与全部动画 MOV
  工程/
    project.json, 创作记忆.md, frame.md
    episodes/<episodeId>/<versionId>/
      animation-manifest.json
      frame.md, package.json, hyperframes.json
      compositions/
      assets/concepts/, assets/design-inputs/, assets/materials/
      .staging/creative-inputs/<round>/
      previews/, cache/, jobs/, releases/
```

生成／导入的全部候选及时经 `.staging/creative-inputs/<round>/` 中转，再由 concept/register 发布到 `assets/concepts/`；非推荐过程图也登记 `recommend: false`。设计参考、原片参考帧、提示词与来源记录经 edit.files 发布到 `assets/design-inputs/`，实际制作素材在 `assets/materials/`。来源字符串可保留工具原路径，实际输入须另有可读版本内引用，不能依赖 `.codex` 或临时目录唯一副本。中转与缓存仍合法，历史收纳按明确维护范围执行，不自动移动已登记资产。仓库开发／验收输出集中在已忽略的 `work/<轮次>/`，它与真实作品版本目录职责不同。

`work_model_store.layout` 从项目标记与注册路径解析归属，不猜父目录层数。`sourceVersion` 原样保存输入目录名，与制作版 ID 和交付号分离。包名只用可读显示名，完整指纹保存在记录中；改名不移动已发布包。每集交付编号跨制作版本协调。

`open copyFrom` 要求明确 `commission`，并显式 `copyMode: restart` 或为每个动画目标 Cue 给出完整 `objectContinuity`。continue 只复制资格 provenance，不复制 review、批准或 Demo 授权；restart/new 不继承资格。writer 只升级已 enrolled 的产品对象身份，schema 2.0 不凭空获得 2.1 object facts。复制只带实际依赖（含静帧）、规范/runtime 和所需原剪输入，不复制批准、缓存或交付。原工程和 user-inbox 不变。重新绑定粗剪必须创建新版本，保留创意草案并把旧时间映射标为未完成。

复制 schema 2.0 视觉规范时，仅在新副本替换已知旧审核模板、追加视觉默认适用范围，保留 YAML 与创意内容，不按阶段关键词删改未知文案。旧 creativeDirection.visualSpec 的 canonical 路径与冻结哈希不继承；新版依据自己的 frame.md 字节计算输入。v3 到 v3 的规范原样复制。任何 frame 中的历史流程文字均不定义新版操作、批准或重开要求。

系列默认来自 `工程/frame.md`；存在默认时，open 必须明确 `useSeriesDefaults`，采用须有 `commission`，不由路径自动推导继承。既有项目入口与根层 frame 的衔接只能在用户明确授权时同步；尚未创建制作版本时可在项目锁下接纳已核对的默认，之后使用 visual-defaults 更新。普通 open 保持既有 AGENTS/CLAUDE 不变，不自动创建或迁移真实工程。

## 应用层

`update` 的创作交互包括 `concept`、`concept-handoff`、`scene-review`、`feedback`、`review-submit`、`review-progress`、`feedback-applicability`、`decision`/原子 `decisions`、`exploration` 与 `exploration-adopt`。`preview` 支持 `storyboard`、`exploration`、局部与 `full`；full 绑定已有或 inline `authorize-demo` 的 taskId 和范围。`work_model_policy.py` 管对象关系、生产依据和可执行来源发布，`work_model_feedback.py` 管反馈/轮次，`work_model_storyboard.py` 管静帧，`work_model_exploration.py` 管候选与采用。

| 组件 | 职责 |
|---|---|
| `afterforge.py` | open/status/update/preview/deliver/resume JSON 请求 CLI |
| `work_model.py` | 身份、文案起步、受控更新、反馈、用户决定、协议基线 |
| `work_model_store.py` | Schema、路径、原子写入、请求去重、共享锁 |
| `work_model_inputs.py` | Cue/时间线输入身份、本地依赖闭包、范围与帧对齐 |
| `work_model_runtime.py` | 初始化明确且本地可用的精确 runtime；以 runtimeIdentity 区分 bootstrap/enrollment/same-byte repair 与实际变更，不安装或查询 latest |
| `work_model_jobs.py` | 固定快照、可恢复执行、缓存验证、产物/交付发布 |
| `work_model_media.py` | 受应用层制作依据核验后的原生渲染、FFmpeg 合成与实际 Alpha |
| `work_model_concepts.py` | 概念图片校验、受控登记、推荐／原子改稿选择、历史图重用与来源链、批量确认、原子分镜交棒及生产依据 |
| `work_model_policy.py` | 产品创作对象、首次确认、限定探索、整版任务依据及资格核验 |
| `work_model_storyboard_production.py` | Storyboard 制作交棒的范围／快照校验、暂缓提示与委托状态投影 |
| `work_model_storyboard.py` | PNG 合同 5 输入、旧合同核验复用、完整 Storyboard 文字快照及局部说明引用 |
| `work_model_scene_review.py` | 实际 Storyboard／视频单场进度记录及局部输入／反馈状态投影，无生产权威 |
| `work_model_intent.py` | 本版非权威 focus/preserve 条目的定向更新，不调用生产策略 |
| `work_model_feedback.py` / `work_model_feedback_targets.py` / `work_model_exploration.py` | 固定反馈批次、处理与接受分离；统一目标解析用于确认、批准、交付；候选工作区及原子采用 |
| `work_model_delivery.py` | 协议 3 授权、XML/媒体闭包、唯一性与轻量证据的不可覆盖发布 |
| `delivery_contract.py` / `delivery_media.py` / `delivery_validation.py` | 读取 JSON 合同、解析资源图与登记来源、哈希/inode 及实际媒体规格核验 |
| `work_model_native_delivery.py` | 待发布媒体硬链接；发布后仅保留正式目录定位与输入键索引 |
| `work_model_review.py` / `assets/review-v3` | 系列 Review、统一 API、媒体流、下载与冲突草稿 |

CLI 与 HTTP 调用同一应用层。短写入在已有 `manifest_transaction` 版本锁内重新读取、校验并发布，多文件失败回滚；跨系列操作先项目锁后版本锁。所有写入要求 requestId 和 expectedRevision，重复请求不能丢评论或重复交付。

长任务在锁内复制所需输入，释放锁运行，再复核内容身份与当前适用用户决定。评论和决定不污染媒体身份；静态审阅快照另行覆盖旁白与最终说明。旁白先取 Cue 直接文本，否则按显式 `segmentIds` 顺序读取 `brief.segments`；相关文本变化使旧 Storyboard 审阅依据失效；PNG 合同 5 排除纯说明、旁白与内容声明，核验输入和 SHA 后复用图片并追加新产物／快照，不改变未变的 Motion 媒体身份。生产核验在渲染、发布、缓存返回及已完成任务捷径之前执行。任务 JSON 留下输入键、进度、已完成 Cue、失败原因和结果；恢复时拒绝已经变化的输入，但新任务复用未变缓存。日志流式写磁盘，媒体哈希流式计算。

同次操作按文件 stat 身份复用已核验哈希，发布边界清空该记忆并重新核验。状态显示使用有界进程缓存，由文件变化重建；批准与交付不读取显示缓存。Review 脚本导出读取选定版本的 brief、段落与最终 Cue 描述，按需生成 UTF-8 Markdown，不保存第二份策划权威。

## 依赖与媒体

同一 canonical composition/motion 用于静帧、讨论和原生交付。Cue 指纹涵盖字节依赖、精确 runtime、尺寸、帧率、时长、屏幕文字与透明性声明；摆放起点、layer、描述和用户决定不混入媒体身份。时间线指纹再包含源 XML/参考视频、范围及全部重叠 Cue 的摆放顺序。详细制作接口见 [单一制作源](../references/hyperframes-single-source.md)。

独立静态路径从 canonical 布局、状态、字体及可选原片帧生成临时 host，调用本地精确 pin 的 PNG snapshot（关闭云端描述），不调用 Cue MOV、用户脚本或 vendor JS。静态 layout 是有限受限声明式源：单帧 raster、local SVG 与字体可用，animated GIF/APNG/WebP 及未知 capability 进入 Motion 或失败；`srcset`、`image-set`、SVG 资源与声明依赖共同形成 closure。host 只装载该 isolated closure 并施加 CSP，不能据此宣称任意 JS 可被静态证明。所有可执行/随时间推进的来源和改变的依赖绑定都经同一 production check，以完整 source closure 判定所有受影响 Cue。Storyboard 帧集合由生成任务登记；历史 2.1 首次确认分别核验当前完整主辅帧、非空最终说明、两渠道 contentContext（unknown 不完整）、相关未解决反馈及对象身份；历史 first-confirmed 不伪装成当前技术状态。反馈交棒固定帧与反馈集合，不自动批准；带用户来源的 feedback resolution 可与确认原子提交。

创作范围、时间范围与呈现范围独立。上下文内已有有效实现默认呈现，缓存缺失可技术重建；未有实现的其他 Cue 不自动补做。缺失和明确排除单独记录。2.2 概念首次资格在普通制作修改中持续有效；明确用户概念改稿开启新轮。当前媒体、审阅资格与批准随实际变化核验。未采用探索候选的评论不阻塞 canonical 成果；采用记录冻结的 variant revision、content identity 和对象范围，之后才按同一反馈目标解析器参与相关核验。历史事故产物保留但无合法制作依据；合法新任务可核验并复用其媒体，以新事件登记当前审阅，不改历史标签。

480p Cue 为透明 ProRes 缓存，FFmpeg 按源帧率合成原粗剪和所有重叠层，音频来自同一粗剪范围。局部默认段落加前后两秒；用帧索引/有理数计算，转 FFmpeg 参数时才确定性转换十进制。完整小样必须覆盖整个粗剪，不得悄悄省略未完成动画；请求的展示目标缺失时默认拒绝，明确 `allowDraft` 只生成 unfinished 讨论稿且不能结束 commission 或生成可交付审阅集合。明确 exclusion 可以完成受限 commission，但绝不形成正式 full Review。`productionRuns` 只登记 `commission_fulfilled` 的结果；对旧 writer 过早完成的记录，追加 `productionCorrections` 证据而不改写历史 run/artifact。所有重叠 Cue 保守生成完整单 Cue 补充小样。

批准引用完整审阅集合，验证实际文件 SHA 与当前输入。只改描述保留批准，源或时间变化使相关产物过期；旧页面只能提交它实际持有的 revision 和 reviewSetId。Agent 标记反馈 addressed 不是用户接受。清楚的合并指令一次记录 approve-and-deliver；单纯批准不授权渲染。

## 发布与验收

全部 animated cues 原生 1920×1080 ProRes 4444 渲染或复用，并从所选 Project 的实际资源图追踪全部历史 AfterForge 动画。文件名仅用于发现待核实对象，来源由登记和实际 SHA 确认；未核实对象拒绝。沿用媒体身份进入交付输入指纹，不能因 XML 文本未变就复用变化的外部媒体。按内容去重，同名不同内容采用确定性不同文件名。继承资产仍是继承来源，不伪造当前 Cue。

当前合同及布局来自 `references/work-model-contract.json`。正式目录为 `AfterForge/交付/<集名>-DNNNN/`，仅一个 `<集名>-DNNNN.fcpxml` 与当前 XML 的全部动画 MOV；均是同级普通文件。动画 `media-rep` 统一为 `./文件名.mov`，清除旧 bookmark 和替代表示；源 XML 不写入。DTD、全部媒体的实际编码/Alpha 通道/帧率/时长、引用闭包、清单、时间/lane、源故事线和继承资源语义共同核验。生成器与验证器分别遍历源资源图。当前渲染还保留实际解码 Alpha 的资格验证。

同一正式 SHA 在整个 AfterForge 内只允许一个 `(device, inode)`，受保护历史路径不排除。所有复用使用硬链接，失败不复制；禁止符号链接或隐藏媒体目录。长任务先在任务区准备原生媒体，以硬链接记录待发布缓存；发布后删除缓存 MOV，仅保留输入键/SHA/正式目录定位索引。后续制作从正式交付复用。正式文件不可原地修改，新内容产生新 D 编号；不同正式版完整保留。

`releases/dNNNN/` 只包含冻结 manifest、必要源 XML、inventory（文件哈希、依赖哈希和批准关联），不保存媒体或大资产。发布先复核当前授权和正在执行的 job，再按项目锁→版本锁核对全量不变量及全工作区唯一性；完成原子 rename 后复验，失败回滚。发布记录先写 job journal，响应丢失后只收养经核验、匹配当前输入和授权的正式结果。协议 1/2 仅历史验证；`work_model_delivery_v2.py` 无 writer，旧 CLI 拒绝新建。旧任务协议指纹不同，不能从完成或恢复捷径返回旧路径作为当前正式交付。

已发布协议 3 的完整性验证只依赖该正式目录、轻量证据和必要校验环境；旧包和工程素材不再是验证依赖。FCP 导入接受绑定 deliveryId 与 XML SHA；真实 re-export 必须覆盖全部正式媒体哈希（含历史沿用）及源/嵌套时间线，再按协议记录 baseline。实际操作仍由用户先导入整批 MOV、再导入 XML；自动测试不能代替该验收。

往返比较对 XML 1.14 的 Apple Basic Title 使用 `fcpxml_text_style.py` 中的有限规范化：macOS ColorSync Generic RGB/sRGB 往返后精确匹配六位有效数字，或在实际 rich-text 字体/字形/字号、文字和 LTR 左对齐均不变时省略已知默认选择器。结果记录逐项规则和前后值；无系统颜色校验环境、未知参数或实质变化仍拒绝。此规则仅供回导比较，正式交付与源 XML 的验证不使用它。登记在同一事务中重查两份 XML 的 SHA 与正式交付完整性，失败不记决定或协议基线。

本次历史迁移是固定清单的维护作业，旧记录/XML/manifest/清单保存在既有 release 证据位置。历史只读 job 不改写，旧交付移出日常可发布集合。没有通用 storage、retention、自动淘汰或预览清理状态机。

## 创作记忆

系列只维护一份精炼记忆，通用初始化使用中性空结构，不植入《楚门》或本线程的已确认历史，也不改写已有真实记忆。每集按需补充采用/放弃原因、成片反馈与来源，不加载所有历史聊天，不建立训练服务。视觉默认与理解经验分离，系列默认更新不静默修改旧制作源。

## 局部说明与本版工作上下文

`animationNotes` 是 Storyboard 的描述数据，不是独立生产／审批对象。Cue 仍为连续制作容器，`finalAnimationDescription` 为唯一总说明。每张帧可用 `cue.storyboard.frames[].narration` 冻结其对应原句（可用 `原声：` 标明真实原声；同句可对应多帧）；缺失映射明确投影为“尚未标注对应旁白”，不会按时间、Cue 旁白或说明推断。新 Storyboard 冻结有序帧集合、逐帧映射、总体/局部说明、旁白与内容事实，以 `reviewInputKey` 核验当前审阅依据；PNG 单独以合同 5 的 inputKey 核验，文字映射变更复用已验证图片。合同 4 的历史记录按原键核验，不能证明一致的旧 PNG 重新生成。帧重组不消除旧反馈或产生完整 Motion 权限。

`workingIntent.items` 与生产数据并列存于版本 manifest，包含稳定 ID、focus/preserve、文字、定位、用户来源与 writer 时间。独立 writer 分支在版本锁内去重/校验/保存，不运行 upgrade 或生产历史纠正；仅更新意图及必要 revision/request 记录。定位失效非阻塞；Agent 更新定位与被替代条目。它不进入任何媒体、Review、资格或交付输入，不继承到新制作版，不写入系列记忆。

正式 Review 在现有 shell 和真实 API 上读取版本数据，保留单集／制作版／历史版选择及可选探索，取消独立交付标签页。整片 Demo 保留绑定准确 reviewSet 的明确交付确认；后台交付生成、检查、历史与下载能力不变。交付完成后由 Agent 在线程提供真实交付目录、XML 和全部带 Alpha 通道的动画 MOV 及导入顺序，不增加审批。三个核心标签页使用连续纵向场景组织，取代旧桌面三列帧／概念卡布局；场景数量来自真实版本，每场左图右文，目录每场一个状态标记。“画面方案”浏览全部候选，查看、选择当前推荐和概念确认独立；“分镜与动画”在同卡切换实际 Storyboard／本场视频，以紧凑帧选择显示关联旁白与说明；“整片 Demo”专注全片节奏和时长。深蓝灰底、蓝紫粉点缀、3px 渐变边框微光及回顶部属于仓库主题，作品 frame.md 不驱动 shell。

页面渲染、状态读写和共享组件分工，生产状态只从服务端恢复；浏览器仅持有草稿、阅读偏好和临时选择，不复制三个 localStorage 生产状态。评论开始输入时冻结版本、对象、快照／artifact 与时间锚点，切版本、切帧或播放跳转不改绑。逐帧反馈按版本串行写入，保存回执立即推进 revision；刷新独立进行，低 revision 迟到响应不覆盖新状态。冲突保留原草稿与定位，不自动重发；草稿、已保存反馈与已提交轮次分别显示。新增相关未解决反馈仍提示待处理，历史确认不投影为无条件通过。图片放大、阅读高亮不改变目标。顶部操作原位回执并防重复；静帧生成按本次 requestId 跟踪 tasks，不采用无关历史成功／失败，后台 hero 与抽帧规则不变。

`concept-handoff` 复用 update 的同一版本事务：验证选中／排除是全部动画 Cue 的准确分区、所选当前推荐概念 ID 和真实用户来源；批量确认尚未确认的所选概念，并追加 `storyboardHandoffs[]`。全部已确认也保存范围。记录含稳定 requestId、source、createdAt 及 selected/excluded 的 cueId/objectId/conceptId 快照，排除项概念可为空。status.conceptDesign.storyboardHandoff 返回最新记录与 current/problems；所选依据、对象或分区变化会提示失效，排除图片自身更新不使所选工作失效。它不进入媒体身份、不新增制作门或 Motion/Demo/交付授权，也不唤醒 Agent；恢复时按记录范围继续。浏览器保存回执与随后状态读取分开处理，读取失败不把成功写入显示为失败，保留请求身份并只重试读取。

`scene-review` 的单场确认是最小版本内进度记录：kind 为 storyboard／animation，cueId 定位对象，分别提交 storyboardId／artifactId 与真实 source。后端重新核验当前 reviewInputKey／视频输入与实际文件；动画记录的 sceneInputKey 绑定本场时间区间、重叠层、背景和审阅文字，不因整片其他场景变化一并重置；status.sceneReviews 投影 current／problems，storyboard.cues[].sceneReview 给出两类最新记录。实际内容变化仅使相关记录失效，旧记录保留；它不进入媒体指纹、不改变首次概念资格、不授予生产或交付，也不成为普通继续制作的新硬门。历史 2.1 原确认接口及事实保持原义。

## Demo 审阅交互

Demo 是 Review shell 内独立标签页，定位条紧邻视频，反馈表单锚定开始输入时的原视频／场景／时间；场景导览只改变播放位置。总时长反馈仍是绑定视频与场景的意见，不改音频时间线。初次选择优先当前完整视频；静帧与探索帧不进入 Demo 素材列表。取时间暂停同一个播放器并显式绑定所看 artifact 与全局有理数时间；导航和意见回看只移动播放位置，历史意见优先回到原视频。文本输入与输入法组合以外的空格在 Demo 控制播放／暂停，并拦截按钮默认激活。

单条反馈与 Storyboard 写入共用版本写队列及 revision 回执，保存中防重复，失败保留草稿；成功后刷新失败不声称保存失败。本轮列表从所审 Demo 的 artifactId 与已持久化 reviewRounds 投影，排除 Storyboard／探索反馈。handoff 复用 `review-submit`，`storyboardIds: []` 加明确 feedbackIds；刷新恢复已提交状态，不把新意见补入已提交轮次。效果通过复用 `decision: approve` 与当前完整 reviewSetId，不生成交付授权；明确“确认整片，生成交付文件”可沿现有 deliver 入口传 approve-and-deliver，绑定准确当前完整集合。提交反馈不隐含已完成任务的下一轮 full Demo 委托，明确返修另以 review-submit 的 inline decision 原子登记新制作任务。制作与历史任务收在次级区域，旧失败不覆盖当前操作回执。

Demo 视频反馈的撤回复用 `feedback-applicability`：`not-applicable` 配合 `review-feedback-withdraw:` 来源标识显示已撤回，恢复写回 `current`。原文、身份与已提交轮次不删除；非 current 意见不进入 Demo 待提交列表。撤回／恢复与提交共用就地忙状态，并沿用按版本串行写入和 revision 冲突保护。

审核视频由 `build_composite_command` 统一编码为 H.264 CRF 23 / medium、VBV maxrate 3M / bufsize 6M、约两秒 GOP、yuv420p、MP4 faststart 与 AAC 128k。全片、局部及补充 Cue 共用默认；源有理数帧率与精确帧数保持不变。此策略只用于已合成的审核视频，不改变透明预览缓存及 ProRes 4444 交付路径。Demo 本轮列表严格读取正在看的 artifactId；旧片意见仍在原片及历史中，不挪到新视频。

Review `/media` 使用 `media_status` 读取当前 manifest 的已登记素材及交付媒体索引，保留版本白名单、路径及符号链接检查，逐请求读取登记变化；不调用完整 `status` 的资格、指纹与文件哈希计算。历史素材本来就可读，因此此路径不产生 current 或批准判断。`/api/state` 和所有 writer 仍执行原核验。

Storyboard 顶部的「确认本轮，生成整片 Demo」复用 `update decision: authorize-demo`，附带所选 `storyboardIds`，在原版本事务内核验当前快照、内容、概念依据及适用反馈，所选／排除范围必须覆盖全部动画 Cue。该可选入口不改变普通制作委托语义，不建立第二次概念批准；页面只保存委托，Agent 以同 taskId 继续制作。`status.storyboard.productionRequest` 从决定和完成记录派生 pending/completed，刷新保留。暂缓勾选建议复用产品对象的反馈目标解析，用户提交时明确记录最终范围。

新 full/local Demo 在产物 `reviewCues` 中只冻结所呈现场景的 id/objectId/title 与有理数 start/duration；既有 productionBasis、previewRequest 和原 authorize-demo 决定继续提供执行与范围依据。反馈 writer 用冻结时序核验场景及对象，不用当前时序解释旧片；无映射历史视频允许时间正文意见。明确返修的 review-submit 校验 artifact SHA 与准确反馈集合，按原委托复制展示、排除、时间边界并登记新 taskId，已有 roundId 可精确引用。普通提交无新委托；任务、事务和去重仍复用原机制。

CLI 的 work_model_review_entry 为本次结果整理 reviewEntry；服务查找／启动仅在 CLI 层，媒体结果与 job 回执不写 URL。项目运行区 工程/review-service.json 只保留单个定位线索；/api/identity 返回进程启动时项目、模式、代码目录与内容身份。匹配才复用，不杀未知或旧进程；服务失败保留媒体成功。页面以 versionId/tab/artifactId 精确定位，明确缺失不降级。可见 Demo 空闲时每 15 秒读取已有 state，任务运行时沿用 4 秒；隐藏时停止定时读取，回前台／进入 Demo／手动刷新均可发现新片。防重叠与既有 revision 保护并用；同视频不重建播放器，切换须用户点击。

Agent 的 status --summary／--cue-id／--feedback-id 由现有完整 status 派生，完整 HTTP／Python／CLI 默认接口保留。work_model_summary 只投影当前目标、意图、Cue 索引、原反馈及委托／预览定位；Cue 相关性复用 feedback_applies，所有 open 意见仍在索引中，不能以摘要代替执行核验。edit 的 cueUpdates 在原事务中展开为完整内存 Cue 列表，再走原对象绑定、Schema、依赖与发布校验；字典合并、数组替换。concept/register-batch 同一外层事务逐项调用原 register 图片准备器，先核对显式推荐每对象至多一个，再统一发布或回滚；没有额外资产或任务引擎。参数细节集中于 references/agent-operations.md，SKILL 和新项目模板默认使用短查询，不自动覆盖已有入口。
