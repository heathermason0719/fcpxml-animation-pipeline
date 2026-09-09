# AfterForge 系列工作规则

本文件仅首次创建，已有文件不自动覆盖。内部 Skill ID 为 `fcpxml-animation-pipeline`。

- 一部电影是一个系列，一条视频是一集；输入版本、制作版本与交付次数分别记录。
- 先读 `工程/创作记忆.md` 的简明共识，再按本集问题读取相关案例。具体视觉默认在 `工程/frame.md`，制作版使用自己的快照。
- 按当前目标理解、设计、试做和修改，不以旧 A-stage 调度 schema 3.0。静态未批准不阻止讨论小样，已有真实样张延续同一制作源。
- 仅缺失信息改变创意含义、素材选择或可靠实施时询问；不让用户选择 static/motion 或办理阶段回退。
- `../user-inbox/` 和原媒体全程只读；当前 AfterForge 是默认写入区。不修改 FCP 资源库或原时间线。
- 使用 Skill 的 `scripts/afterforge.py open/status/update/preview/deliver/resume`。源码先到本版 `.staging/`，再经 update 发布；不手改 manifest 或审核/交付 evidence。
- 保持有理数时间与源帧率。制作版 runtime 精确 pin 不随 latest 漂移；安装和版本迁移需明确授权。
- 交付需当前完整审阅集合的批准与授权；明确“批准并制作交付”可同时记录。单纯认可图像不构成授权。
- 480p 小样保留粗剪声音；正式 1080p ProRes 4444 全 Cue 验证。声音制作、原片重剪、Handles/sourceIn 不在范围。
- `交付/` 是面向用户的包入口；`工程/episodes/` 保存独立版本，`releases/` 保存不可变交付事实。当前稿修改不覆盖历史包，不要求先验收旧包。
- schema 2.0 工程原位只读，明确继续制作时创建 v3 副本；不继承旧批准或改写旧 runtime。
- 不自动 commit、push、安装、真实工程迁移或 FCP 导入。
