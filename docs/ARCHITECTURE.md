# 架构

## 工作对象与权威

新版是 manifest 3.0 / work model 2.0 / delivery protocol 2。`references/work-model-contract.json` 定义操作和词汇；`animation-manifest.json` 是单个制作版本生产事实的唯一入口。系列 `工程/project.json` 只记录稳定系列/集/版本身份、路径注册和经验证的协议基线。

`brief` 保存本集理解与论证段落，`cues` 保存具体表达源、依赖及有理数摆放。`artifacts` 保存实际产物 SHA、生成输入、全局覆盖范围和完整性；`reviewSets` 绑定完整小样与必要的重叠 Cue 补审；`feedback` 保存原话、位置、来源、澄清及处理；`decisions` 单独保存有来源的用户决定；`deliveries` 绑定不可变包及快照。执行任务不保存批准权威。

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

`open copyFrom` 只复制实际依赖、规范/runtime 和所需原剪输入，不复制批准、缓存或交付。原工程和 user-inbox 不变。重新绑定粗剪必须创建新版本，保留创意草案并把旧时间映射标为未完成。

## 应用层

| 组件 | 职责 |
|---|---|
| `afterforge.py` | open/status/update/preview/deliver/resume JSON 请求 CLI |
| `work_model.py` | 身份、文案起步、受控更新、反馈、用户决定、协议基线 |
| `work_model_store.py` | Schema、路径、原子写入、请求去重、共享锁 |
| `work_model_inputs.py` | Cue/时间线输入身份、本地依赖闭包、范围与帧对齐 |
| `work_model_runtime.py` | 初始化明确且本地可用的精确 runtime；不安装或查询 latest |
| `work_model_jobs.py` | 固定快照、可恢复执行、缓存验证、产物/交付发布 |
| `work_model_media.py` | 无阶段门禁的原生 HyperFrames 渲染、FFmpeg 合成与实际 Alpha |
| `work_model_delivery.py` | 协议 2 XML、包与复现快照、清单核验和不可覆盖发布 |
| `work_model_review.py` / `assets/review-v3` | 系列 Review、统一 API、媒体流、下载与冲突草稿 |

CLI 与 HTTP 调用同一应用层。短写入在已有 `manifest_transaction` 版本锁内重新读取、校验并发布，多文件失败回滚；跨系列操作先项目锁后版本锁。所有写入要求 requestId 和 expectedRevision，重复请求不能丢评论或重复交付。

长任务在锁内复制所需输入，释放锁运行，再复核内容身份与当前适用用户决定。说明/评论追加不作为渲染失效条件。任务 JSON 留下输入键、进度、已完成 Cue、失败原因和结果；恢复时拒绝已经变化的输入，但新任务复用未变缓存。日志流式写磁盘，媒体哈希流式计算。

同次操作按文件 stat 身份复用已核验哈希，发布边界清空该记忆并重新核验。状态显示使用有界进程缓存，由文件变化重建；批准与交付不读取显示缓存。Review 脚本导出读取选定版本的 brief、段落与最终 Cue 描述，按需生成 UTF-8 Markdown，不保存第二份策划权威。

## 依赖与媒体

同一 canonical composition/motion 用于静帧、讨论和原生交付。Cue 指纹涵盖字节依赖、精确 runtime、尺寸、帧率、时长、屏幕文字与透明性声明；摆放起点、layer、描述和用户决定不混入媒体身份。时间线指纹再包含源 XML/参考视频、范围及全部重叠 Cue 的摆放顺序。详细制作接口见 [单一制作源](../references/hyperframes-single-source.md)。

480p Cue 为透明 ProRes 缓存，FFmpeg 按源帧率合成原粗剪和所有重叠层，音频来自同一粗剪范围。局部默认段落加前后两秒；用帧索引/有理数计算，转 FFmpeg 参数时才确定性转换十进制。完整小样必须覆盖整个粗剪，不得悄悄省略未完成动画；讨论稿显式记录缺失 Cue，不生成可交付审阅集合。所有重叠 Cue 保守生成完整单 Cue 补充小样。

批准引用完整审阅集合，验证实际文件 SHA 与当前输入。只改描述保留批准，源或时间变化使相关产物过期；旧页面只能提交它实际持有的 revision 和 reviewSetId。Agent 标记反馈 addressed 不是用户接受。清楚的合并指令一次记录 approve-and-deliver；单纯批准不授权渲染。

## 发布与验收

全部 animated cues 原生 1920×1080 ProRes 4444 渲染或复用，核验精确帧率/时长、实际解码 Alpha 和媒体 SHA。序列、源故事线及有理数位置保持，FCPXMLD 内只含 Info.fcpxml 和 MOV。DTD、引用、清单、时间/lane 与源不变性验证通过后才发布。

包在 `交付/`，快照在本版 `releases/dNNNN/`。快照保存 manifest、原 XML、实际 MOV，以及 `files/` 下保持相对结构的复现源和已批准审阅文件；inventory 记录映射与 SHA。日志、探索和无关缓存排除；当前实现使用独立复制，尚不依赖可变硬链接。两个目录先完成后再原子 rename，正常异常清理已发布部分，manifest 保存失败撤回新包/快照；不覆盖既有发布。

发布前将准备好的发布记录写入任务日志。响应丢失后，恢复会核验包、快照、当前输入及授权，再接回完整发布；仅在目标精确匹配该任务清单时清理单边发布残留。

相同交付输入返回已验证旧包。当前草稿可继续修改；历史批准/验收只属于原包，修改无需旧阶段重开。FCP 导入接受绑定 deliveryId 与实际 Info SHA；首次协议 2 的真实 re-export 经比较器通过后建立系列 protocolBaselines。没有自动测试可以代替实际 FCP 操作。

## 创作记忆

系列只维护一份精炼记忆，初始内容为本线程确认观点与新版开场案例，明确适用范围。每集按需补充采用/放弃原因、成片反馈与来源，不加载所有历史聊天，不建立训练服务。视觉默认与理解经验分离，系列默认更新不静默修改旧制作源。
