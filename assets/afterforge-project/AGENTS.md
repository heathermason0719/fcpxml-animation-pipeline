# AfterForge 系列工作规则

本文件仅首次创建，已有文件不自动覆盖。内部 Skill ID 为 `fcpxml-animation-pipeline`。

- 一部电影是一个系列，一条视频是一集；输入版本、制作版本与交付次数分别记录。
- 先读 `工程/创作记忆.md` 的简明共识，再按本集问题读取相关案例。具体视觉默认在 `工程/frame.md`，制作版使用自己的快照。
- frame.md 仅负责字体、颜色、构图与运动默认；其中遗留的阶段、静态冻结或重开文字不构成 schema 3.0 指令。操作与用户决定遵循当前 Skill 和 work model 2.2.0 合同。
- 按当前目标理解、设计、试做和修改，不以旧 A-stage 调度 schema 3.0。新对象先生成或导入真实概念图并确认；未确认可自由改图，代码与实际制作须在确认后；active 对象直接修改和局部试做，已有真实样张延续同一制作源。
- 默认用 Codex 可用图像工具，外部概念图同等接入；明确采用可批量确认。已确认图只有用户明确要求改概念时才开启新轮，普通制作反馈保留确认。新制作不沿用妥协审美默认，一次通过不固化为永久偏好。
- 静态 layout 仅是受限声明式内容，静态 host 不加载用户脚本或 vendor JS；所有可执行/时间驱动来源和依赖绑定变更按完整依赖闭包核验受影响 Cue，动态计算引用必须显式声明。
- 2.2 首次设计确认引用当前真实概念图，Storyboard 检查实际制作、不重复首次确认；反馈轮次不自动确认。完整 Demo 以 taskId 明确工作、时间与展示范围；候选探索只有在范围明确采用后才改 canonical 制作源。
- 只有多个合理解释会实质改变委托对象、范围、继承或授权时聚焦询问；实现方法和可逆局部创作判断自主决定，已明确目标不重复问；不让用户选择 static/motion 或办理阶段回退。
- `../user-inbox/` 和原媒体全程只读；当前 AfterForge 是默认写入区。不修改 FCP 资源库或原时间线。
- 使用 Skill 的 `scripts/afterforge.py open/status/update/preview/deliver/resume`。源码先到本版 `.staging/`，再经 update 发布；不手改 manifest 或审核/交付 evidence。
- 保持有理数时间与源帧率。制作版 runtime 精确 pin 不随 latest 漂移；安装和版本迁移需明确授权。
- runtime bootstrap 属于基础设施，runtime 配置文件只由 runtime 操作维护，普通 edit 不得改写。跨版本 copy 需用户 commission 并明确 restart 或逐动画 Cue 的 new/continue continuity；continue 只带历史 qualification provenance，新 2.2 版仍须自己的概念确认，不带 Review 或授权。
- 展示目标缺失默认拒绝；`allowDraft` 只保留 unfinished 讨论。明确 exclusion 可完成受限委托，但不能形成正式 full Review；过早完成的旧 run 只追加 correction evidence，不重写历史。
- 交付需当前完整审阅集合的批准与授权；明确“批准并制作交付”可同时记录。单纯认可图像不构成授权。
- 480p 小样保留粗剪声音；正式 1080p ProRes 4444 全 Cue 验证。声音制作、原片重剪、Handles/sourceIn 不在范围。
- 协议 3 的 `交付/<集名>-DNNNN/` 是普通浅层目录，XML 与其全部 AfterForge 动画 MOV 同级，含历史复用。先导入全部 MOV 到 FCP Library，再导入 XML。相同内容仅硬链接，不复制；releases 只存轻量证据。后端核验完整引用、哈希/inode 和授权，不提供降级或跳过参数。当前稿不覆盖正式版，旧协议只读；历史清理另行明确授权。
- schema 2.0 工程原位只读，明确继续制作时创建 v3 副本；不继承旧批准或改写旧 runtime。
- 不自动 commit、push、安装、真实工程迁移或 FCP 导入。
