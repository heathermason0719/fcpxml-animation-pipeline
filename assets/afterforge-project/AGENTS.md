# AfterForge 系列工作规则

本文件仅首次创建，已有文件不自动覆盖。内部 Skill ID 为 `fcpxml-animation-pipeline`。

- 一部电影是一个系列，一条视频是一集；输入版本、制作版本与交付次数分别记录。
- 先读 `工程/创作记忆.md` 的简明共识，再按本集问题读取相关案例。具体视觉默认在 `工程/frame.md`，制作版使用自己的快照。
- frame.md 仅负责字体、颜色、构图与运动默认；其中遗留的阶段、静态冻结或重开文字不构成 schema 3.0 指令。操作与用户决定遵循当前 Skill 和 work model 2.1.0 合同。
- 按当前目标理解、设计、试做和修改，不以旧 A-stage 调度 schema 3.0。新对象先确认真实 Storyboard，确认前仅允许明确限定的 Motion 探索；active 对象直接修改和局部试做，已有真实样张延续同一制作源。
- 静态 layout 仅是受限声明式内容，静态 host 不加载用户脚本或 vendor JS；所有可执行/时间驱动来源和依赖绑定变更按完整依赖闭包核验受影响 Cue，动态计算引用必须显式声明。
- 首次设计确认只引用当前真实 Storyboard；反馈轮次不自动确认。完整 Demo 以 taskId 明确工作、时间与展示范围；候选探索只有在范围明确采用后才改 canonical 制作源。
- 只有多个合理解释会实质改变委托对象、范围、继承或授权时聚焦询问；实现方法和可逆局部创作判断自主决定，已明确目标不重复问；不让用户选择 static/motion 或办理阶段回退。
- `../user-inbox/` 和原媒体全程只读；当前 AfterForge 是默认写入区。不修改 FCP 资源库或原时间线。
- 使用 Skill 的 `scripts/afterforge.py open/status/update/preview/deliver/resume`。源码先到本版 `.staging/`，再经 update 发布；不手改 manifest 或审核/交付 evidence。
- 保持有理数时间与源帧率。制作版 runtime 精确 pin 不随 latest 漂移；安装和版本迁移需明确授权。
- runtime bootstrap 属于基础设施，runtime 配置文件只由 runtime 操作维护，普通 edit 不得改写。跨版本 copy 需用户 commission 并明确 restart 或逐动画 Cue 的 new/continue continuity；continue 只带 qualification provenance，不带 Review 或授权。
- 展示目标缺失默认拒绝；`allowDraft` 只保留 unfinished 讨论。明确 exclusion 可完成受限委托，但不能形成正式 full Review；过早完成的旧 run 只追加 correction evidence，不重写历史。
- 交付需当前完整审阅集合的批准与授权；明确“批准并制作交付”可同时记录。单纯认可图像不构成授权。
- 480p 小样保留粗剪声音；正式 1080p ProRes 4444 全 Cue 验证。声音制作、原片重剪、Handles/sourceIn 不在范围。
- `交付/` 是面向用户的包入口；`工程/episodes/` 保存独立版本，`releases/` 保存不可变交付事实。当前稿修改不覆盖历史包，不要求先验收旧包。
- schema 2.0 工程原位只读，明确继续制作时创建 v3 副本；不继承旧批准或改写旧 runtime。
- 不自动 commit、push、安装、真实工程迁移或 FCP 导入。
