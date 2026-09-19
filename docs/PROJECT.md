# 项目定义

`fcpxml-animation-pipeline` 是可复用的 Codex Skill：帮助使用 Final Cut Pro 的创作者理解脚本、设计动画、在真实粗剪中试做和修改，并交付可继续编辑的透明动画与 FCPXMLD。

## 工作模型

一部电影对应一个系列，一条视频对应一集；每集可有多个独立制作版本及多次不可变交付。以作品、反馈和当前目标组织工作，理解、设计、试做、修改与交付是可往返的活动，不使用 A1–A14 调度新版生产。

支持文案或已有粗剪起步。文案策划不要求媒体；涉及真实时间线的预览和交付才要求 FCPXML/FCPXMLD、匹配参考视频及足够旁白依据。先理解全篇论证，再划分段落；一段可以没有动画，也可以有多条动画。

创意判断由当前 Agent 完成；Python、HyperFrames 与 FFmpeg 负责确定性时间运算、依赖和媒体核验、预览、注册及 XML 回填。Review 与 CLI 调用同一应用层，不引入模型服务、数据库或云平台。

## 核心约束

- 首次设计由当前真实 Storyboard 帧的明确确认建立；反馈 handoff、静帧、小样与交付不互相代替。完整 Demo 的工作、时间与展示范围独立，并由一次 taskId 授权绑定。
- 创意对象是产品身份，不是技术 Cue ID。技术重组以已知关系记录 `objectRelations`，真正新增独立对象不继承他人资格；多个合理解释会改变对象、范围、继承或授权时才聚焦询问。实现方法和可逆局部创作判断由 Agent 自主决定。探索候选不等于采用。

- 默认目录 `AfterForge` 只是可替换的显示名称，内部 ID 保持 `fcpxml-animation-pipeline`。
- `user-inbox/` 中目录和材料由用户选择并维护，Agent 全程只读。原 FCPXML、视频、字幕和资源库不覆盖。
- FCPXML 的帧率、有理数时间和原故事线是时间权威；字幕与文案提供语义依据。
- `工程/创作记忆.md` 保存理解、已确认偏好与适用条件；`工程/frame.md` 保存系列视觉默认；每版源与规范快照不随系列默认漂移。
- 静帧与动画共享制作源。首次确认前仅允许明确限定的 Motion 探索；active 对象可直接修改和局部试做，不机械回退；交付需当前完整审阅集合的用户批准与授权，允许明确的一句指令同时记录两者。
- 静态 layout 是受限声明式内容，不承载可执行或时间驱动来源；静态 host 不加载用户脚本或 vendor JS。有限静态能力只接受单帧 raster、local SVG 与字体，animated GIF/APNG/WebP 属于 Motion；未知能力、远程或未登记资源失败。`srcset`、`image-set` 与 SVG 资源加入完整闭包，isolated host 的 CSP 防止闭包外加载，但不声称静态分析任意 JS。
- 每个 Cue 分别声明 narration/screenText 的 `contentContext`（`present`、`none`、`unknown`）。实际文本仍来自 Cue、显式关联段落或屏幕文字；`none` 有 text/reference 依据，`unknown` 阻止首次确认，不能用另一渠道文字伪造完整内容。
- runtimeIdentity 区分 fresh bootstrap、enrollment、same-byte repair 与实际变更；精确 pin 不漂移。
- `copyFrom` 需用户 commission，并明确 restart 或逐动画 Cue 的 new/continue 连续性；continue 仅带首次资格 provenance，绝不带 Review、批准或 Demo 授权。历史 schema 2.0 不补写 2.1 对象事实。
- 请求的展示目标缺失默认拒绝；`allowDraft` 仅生成未完成讨论稿，明确 exclusion 可完成受限委托但不能形成正式 full Review。只有 commission 实际 fulfilled 才登记 production run；历史过早完成以附加更正证据保留原历史。
- 只改说明不重渲；只改摆放复用媒体。失效由真实依赖决定，不能靠 Agent 修改分类绕过。
- 每份交付保持输入、媒体、批准与实际验收绑定；工作稿可继续修改，不要求先验收或办理重开。
- 新交付使用协议 2，首次实际 FCP 导入与 round-trip 建立协议基线。旧合同、包与历史事实不改义。

## 交付范围

首要场景为 16:9 横屏口播/电影分析视频。动画可以是文字、图形、遮罩或必要视觉演示；默认 480p 讨论预览，正式动画为源帧率 1920×1080 ProRes 4444。FCPXMLD 包内平铺 `Info.fcpxml` 与动画 MOV，保留原剪辑，用户在 FCP 继续工作。

不承担原片重剪、调色混音、音乐音效制作、Handles/sourceIn 扩展；不自动安装、迁移真实工程、导入 FCP、提交或发布代码。电影素材和本地产物不进入仓库。隔离媒体与包测试不替代协议 2 的实际 FCP 导入和往返验证。
