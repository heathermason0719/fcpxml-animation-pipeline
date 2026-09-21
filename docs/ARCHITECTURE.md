# 架构

## 工作对象与权威

新版是 manifest 3.0 / work model 2.1.0 / delivery protocol 2。`references/work-model-contract.json` 定义操作和词汇；`animation-manifest.json` 是单个制作版本生产事实的唯一入口。系列 `工程/project.json` 只记录稳定系列/集/版本身份、路径注册和经验证的协议基线。

`brief` 保存本集理解与论证段落，`cues` 保存具体表达源、依赖及有理数摆放。Cue 的 `contentContext` 分别记录 narration/screenText 的 present、none 或 unknown；实际文本仍只在既有 Cue 或关联 brief 段落中，none 保存 text/reference 依据。`artifacts` 保存实际产物 SHA、生成输入、全局覆盖范围和完整性；`reviewSets` 绑定完整小样与必要的重叠 Cue 补审；`feedback` 保存原话、位置、来源、澄清及处理；`decisions` 单独保存有来源的用户决定；`deliveries` 绑定不可变包及快照。反馈冲突、非空最终说明、技术上的当前 board 与历史 `firstConfirmed` 是分别核验的事实，互不替代。执行任务不保存批准权威。

旧 schema 2.0 位于 `references/legacy/animation-manifest-v2.schema.json`；Stage Contract 1.0.0 与原阶段语义不变。旧生产实现的解释见 [legacy 架构](../references/legacy/architecture-v2.md)，仅在读取历史合同或显式旧工具维护时加载。新版不调用阶段 resolver。

## 布局与边界

```text
AfterForge/
  AGENTS.md, CLAUDE.md                缺失时创建，已有文件不覆盖
  交付/<集名--稳定ID>/交付NNNN/<集名>.fcpxmld
  工程/
    project.json, 创作记忆.md, frame.md
    episodes/<episodeId>/<versionId>/
      animation-manifest.json
      frame.md, package.json, hyperframes.json
      compositions/, assets/, .staging/
      previews/, cache/, jobs/, releases/
```

`work_model_store.layout` 从项目标记与注册路径解析归属，不猜父目录层数。`sourceVersion` 原样保存输入目录名，与制作版 ID 和交付号分离。包名只用可读显示名，完整指纹保存在记录中；改名不移动已发布包。每集交付编号跨制作版本协调。

`open copyFrom` 要求明确 `commission`，并显式 `copyMode: restart` 或为每个动画目标 Cue 给出完整 `objectContinuity`。continue 只复制资格 provenance，不复制 review、批准或 Demo 授权；restart/new 不继承资格。writer 只升级已 enrolled 的产品对象身份，schema 2.0 不凭空获得 2.1 object facts。复制只带实际依赖（含静帧）、规范/runtime 和所需原剪输入，不复制批准、缓存或交付。原工程和 user-inbox 不变。重新绑定粗剪必须创建新版本，保留创意草案并把旧时间映射标为未完成。

复制 schema 2.0 视觉规范时，仅在新副本替换已知旧审核模板、追加视觉默认适用范围，保留 YAML 与创意内容，不按阶段关键词删改未知文案。旧 creativeDirection.visualSpec 的 canonical 路径与冻结哈希不继承；新版依据自己的 frame.md 字节计算输入。v3 到 v3 的规范原样复制。任何 frame 中的历史流程文字均不定义新版操作、批准或重开要求。

系列默认来自 `工程/frame.md`；存在默认时，open 必须明确 `useSeriesDefaults`，采用须有 `commission`，不由路径自动推导继承。既有项目入口与根层 frame 的衔接只能在用户明确授权时同步；尚未创建制作版本时可在项目锁下接纳已核对的默认，之后使用 visual-defaults 更新。普通 open 保持既有 AGENTS/CLAUDE 不变，不自动创建或迁移真实工程。

## 应用层

`update` 的创作交互包括 `feedback`、`review-submit`、`review-progress`、`feedback-applicability`、`decision`/原子 `decisions`、`exploration` 与 `exploration-adopt`。`preview` 支持 `storyboard`、`exploration`、局部与 `full`；full 绑定已有或 inline `authorize-demo` 的 taskId 和范围。`work_model_policy.py` 管对象关系、生产依据和可执行来源发布，`work_model_feedback.py` 管反馈/轮次，`work_model_storyboard.py` 管静帧，`work_model_exploration.py` 管候选与采用。

| 组件 | 职责 |
|---|---|
| `afterforge.py` | open/status/update/preview/deliver/resume JSON 请求 CLI |
| `work_model.py` | 身份、文案起步、受控更新、反馈、用户决定、协议基线 |
| `work_model_store.py` | Schema、路径、原子写入、请求去重、共享锁 |
| `work_model_inputs.py` | Cue/时间线输入身份、本地依赖闭包、范围与帧对齐 |
| `work_model_runtime.py` | 初始化明确且本地可用的精确 runtime；以 runtimeIdentity 区分 bootstrap/enrollment/same-byte repair 与实际变更，不安装或查询 latest |
| `work_model_jobs.py` | 固定快照、可恢复执行、缓存验证、产物/交付发布 |
| `work_model_media.py` | 受应用层制作依据核验后的原生渲染、FFmpeg 合成与实际 Alpha |
| `work_model_policy.py` | 产品创作对象、首次确认、限定探索、整版任务依据及资格核验 |
| `work_model_storyboard.py` | PNG 合同 5 输入、旧合同核验复用、完整 Storyboard 文字快照及局部说明引用 |
| `work_model_intent.py` | 本版非权威 focus/preserve 条目的定向更新，不调用生产策略 |
| `work_model_feedback.py` / `work_model_feedback_targets.py` / `work_model_exploration.py` | 固定反馈批次、处理与接受分离；统一目标解析用于确认、批准、交付；候选工作区及原子采用 |
| `work_model_delivery.py` | 协议 2 XML、包与复现快照、清单核验和不可覆盖发布 |
| `work_model_review.py` / `assets/review-v3` | 系列 Review、统一 API、媒体流、下载与冲突草稿 |

CLI 与 HTTP 调用同一应用层。短写入在已有 `manifest_transaction` 版本锁内重新读取、校验并发布，多文件失败回滚；跨系列操作先项目锁后版本锁。所有写入要求 requestId 和 expectedRevision，重复请求不能丢评论或重复交付。

长任务在锁内复制所需输入，释放锁运行，再复核内容身份与当前适用用户决定。评论和决定不污染媒体身份；静态审阅快照另行覆盖旁白与最终说明。旁白先取 Cue 直接文本，否则按显式 `segmentIds` 顺序读取 `brief.segments`；相关文本变化使旧 Storyboard 审阅依据失效；PNG 合同 5 排除纯说明、旁白与内容声明，核验输入和 SHA 后复用图片并追加新产物／快照，不改变未变的 Motion 媒体身份。生产核验在渲染、发布、缓存返回及已完成任务捷径之前执行。任务 JSON 留下输入键、进度、已完成 Cue、失败原因和结果；恢复时拒绝已经变化的输入，但新任务复用未变缓存。日志流式写磁盘，媒体哈希流式计算。

同次操作按文件 stat 身份复用已核验哈希，发布边界清空该记忆并重新核验。状态显示使用有界进程缓存，由文件变化重建；批准与交付不读取显示缓存。Review 脚本导出读取选定版本的 brief、段落与最终 Cue 描述，按需生成 UTF-8 Markdown，不保存第二份策划权威。

## 依赖与媒体

同一 canonical composition/motion 用于静帧、讨论和原生交付。Cue 指纹涵盖字节依赖、精确 runtime、尺寸、帧率、时长、屏幕文字与透明性声明；摆放起点、layer、描述和用户决定不混入媒体身份。时间线指纹再包含源 XML/参考视频、范围及全部重叠 Cue 的摆放顺序。详细制作接口见 [单一制作源](../references/hyperframes-single-source.md)。

独立静态路径从 canonical 布局、状态、字体及可选原片帧生成临时 host，调用本地精确 pin 的 PNG snapshot（关闭云端描述），不调用 Cue MOV、用户脚本或 vendor JS。静态 layout 是有限受限声明式源：单帧 raster、local SVG 与字体可用，animated GIF/APNG/WebP 及未知 capability 进入 Motion 或失败；`srcset`、`image-set`、SVG 资源与声明依赖共同形成 closure。host 只装载该 isolated closure 并施加 CSP，不能据此宣称任意 JS 可被静态证明。所有可执行/随时间推进的来源和改变的依赖绑定都经同一 production check，以完整 source closure 判定所有受影响 Cue。Storyboard 帧集合由生成任务登记，首次确认分别核验当前完整主辅帧、非空最终说明、两渠道 contentContext（unknown 不完整）、相关未解决反馈及对象身份；历史 first-confirmed 不伪装成当前技术状态。反馈交棒固定帧与反馈集合，不自动批准；带用户来源的 feedback resolution 可与确认原子提交。

创作范围、时间范围与呈现范围独立。上下文内已有有效实现默认呈现，缓存缺失可技术重建；未有实现的其他 Cue 不自动补做。缺失和明确排除单独记录。首次资格持续有效，当前媒体、审阅资格与批准随实际变化核验。未采用探索候选的评论不阻塞 canonical 成果；采用记录冻结的 variant revision、content identity 和对象范围，之后才按同一反馈目标解析器参与相关核验。历史事故产物保留但无合法制作依据；合法新任务可核验并复用其媒体，以新事件登记当前审阅，不改历史标签。

480p Cue 为透明 ProRes 缓存，FFmpeg 按源帧率合成原粗剪和所有重叠层，音频来自同一粗剪范围。局部默认段落加前后两秒；用帧索引/有理数计算，转 FFmpeg 参数时才确定性转换十进制。完整小样必须覆盖整个粗剪，不得悄悄省略未完成动画；请求的展示目标缺失时默认拒绝，明确 `allowDraft` 只生成 unfinished 讨论稿且不能结束 commission 或生成可交付审阅集合。明确 exclusion 可以完成受限 commission，但绝不形成正式 full Review。`productionRuns` 只登记 `commission_fulfilled` 的结果；对旧 writer 过早完成的记录，追加 `productionCorrections` 证据而不改写历史 run/artifact。所有重叠 Cue 保守生成完整单 Cue 补充小样。

批准引用完整审阅集合，验证实际文件 SHA 与当前输入。只改描述保留批准，源或时间变化使相关产物过期；旧页面只能提交它实际持有的 revision 和 reviewSetId。Agent 标记反馈 addressed 不是用户接受。清楚的合并指令一次记录 approve-and-deliver；单纯批准不授权渲染。

## 发布与验收

全部 animated cues 原生 1920×1080 ProRes 4444 渲染或复用，核验精确帧率/时长、实际解码 Alpha 和媒体 SHA。序列、源故事线及有理数位置保持，FCPXMLD 内只含 Info.fcpxml 和 MOV。DTD、引用、清单、时间/lane 与源不变性验证通过后才发布。

包在 `交付/`，快照在本版 `releases/dNNNN/`。快照保存 manifest、原 XML、实际 MOV，以及 `files/` 下保持相对结构的复现源和已批准审阅文件；inventory 记录映射与 SHA。日志、探索和无关缓存排除；当前实现使用独立复制，尚不依赖可变硬链接。两个目录先完成后再原子 rename，正常异常清理已发布部分，manifest 保存失败撤回新包/快照；不覆盖既有发布。

发布前将准备好的发布记录写入任务日志。响应丢失后，恢复会核验包、快照、当前输入及授权，再接回完整发布；仅在目标精确匹配该任务清单时清理单边发布残留。

相同交付输入返回已验证旧包。当前草稿可继续修改；历史批准/验收只属于原包，修改无需旧阶段重开。FCP 导入接受绑定 deliveryId 与实际 Info SHA；首次协议 2 的真实 re-export 经比较器通过后建立系列 protocolBaselines。没有自动测试可以代替实际 FCP 操作。

## 创作记忆

系列只维护一份精炼记忆，通用初始化使用中性空结构，不植入《楚门》或本线程的已确认历史，也不改写已有真实记忆。每集按需补充采用/放弃原因、成片反馈与来源，不加载所有历史聊天，不建立训练服务。视觉默认与理解经验分离，系列默认更新不静默修改旧制作源。

## 局部说明与本版工作上下文

`animationNotes` 是 Storyboard 的描述数据，不是独立生产／审批对象。Cue 仍为连续制作容器，`finalAnimationDescription` 为唯一总说明。新 Storyboard 冻结有序帧集合、总体/局部说明、旁白与内容事实，以 `reviewInputKey` 核验当前审阅依据；PNG 单独以合同 5 的 inputKey 核验，role 等原图片依赖继续有效。合同 4 的历史记录按原键核验，不能证明一致的旧 PNG 重新生成。帧重组不消除旧反馈或产生完整 Motion 权限。

`workingIntent.items` 与生产数据并列存于版本 manifest，包含稳定 ID、focus/preserve、文字、定位、用户来源与 writer 时间。独立 writer 分支在版本锁内去重/校验/保存，不运行 upgrade 或生产历史纠正；仅更新意图及必要 revision/request 记录。定位失效非阻塞；Agent 更新定位与被替代条目。它不进入任何媒体、Review、资格或交付输入，不继承到新制作版，不写入系列记忆。

正式 Review 在现有 API 上读取这两份数据。顶部显示单集/制作版/历史版与 Cue 跳转；桌面三列等尺寸帧，窄屏两列。说明按当前快照帧序挂在最后关联帧下，关系按钮只负责阅读高亮。图片弹窗、桌面 sticky 反馈栏、逐版本/对象/帧的留言开合偏好属于浏览器状态，不改变批准。保存反馈、交棒、完整 Cue 确认仍使用原接口；新 Storyboard 清除旧依据勾选，草稿不自动转绑。后台 hero 约束与抽帧用途不变。
