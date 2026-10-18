# AfterForge

先遵循同目录 `AGENTS.md`。这是电影系列的动画工作区：围绕当前作品与反馈工作，用 `fcpxml-animation-pipeline` 的统一 CLI，保留原素材、精确时间、制作版 runtime 和不可变交付。

默认读取 `工程/创作记忆.md` 的简明共识及选中版本的视觉规范；不加载全部历史阶段文档。旧 schema 2.0 只读，继续制作显式创建新副本。

新 2.2 制作的每条动画先有真实概念图，未确认可自由改图；采用候选只选择推荐图，独立确认概念后才发布代码和渲染。用户明确要求改概念才开启新确认轮次，普通实现反馈不撤销确认。

首次设计、反馈 handoff、完整审阅与交付分别记录；首次确认后的对象可以直接按明确目标修改和局部试做，不回退首次入口。完整 Demo 必须有当前 taskId、工作与展示范围的明确授权；探索候选未采用前不改变制作源。

静态 layout 只承载受限声明式内容，静态 host 不加载用户脚本或 vendor JS；可执行/时间驱动来源及其依赖绑定变更必须通过完整依赖闭包的 production check。runtime 配置只由 runtime 操作维护。跨版本继续需要 commission 和明确的 restart 或 Cue 级 new/continue continuity；继续只带历史 qualification provenance，新 2.2 版仍须自己的概念确认，不带审阅或授权。缺失展示目标默认拒绝；allowDraft 是未完成讨论，明确 exclusion 不能成为正式 full Review。

全部生成／导入候选及时经本版 `.staging/creative-inputs/<round>/` 登记到 `assets/concepts/`，非推荐稿用 recommend:false；参考与提示词持久保存到 `assets/design-inputs/` 后引用，制作素材在 `assets/materials/`。工具输出与临时路径仅作来源，不能是唯一可依赖副本。既有历史文件不自动搬迁清理。

已确认后主动换图用有来源的 concept/select 原子改稿选择，原图与反馈保留；Storyboard／本场动画确认只记当前内容的审阅进度，不产生新生产硬门。部分推进明确列出包含与排除，提交 Demo 反馈不自动授权下一轮整版任务。

概念页分镜交棒使用 concept-handoff 原子保存待确认图与包含／排除对象范围；恢复读取 status.conceptDesign.storyboardHandoff，不新增制作门或 Motion／Demo／交付授权，不自动启动 Agent 或渲染。写入成功后刷新失败保留回执并只重试读取。
