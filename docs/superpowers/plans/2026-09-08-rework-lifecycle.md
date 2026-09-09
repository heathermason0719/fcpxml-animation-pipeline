# 闭环后返工实施计划

**Goal:** 为所有按当前规则闭环的 Vn 提供可重复、线性的重开—审核—交付—验收流程，并使用已交付 Vn 验证真实入口。

**Architecture:** 同一 Vn 保持一个活动制作区；每次重开先封存上一轮闭环快照，再递增 `workflow.rework.revision`。新轮次的 Demo、原生 MOV、ledger 和阶段 evidence 绑定修订；未受影响的 A11 批准继续有效。旧文件与批准只读保留，新交付指纹包含返工修订身份。

**Tech Stack:** Python、现有 JSON Schema、现有 Vn 事务锁、精确 pin 的 HyperFrames、FCPXML delivery protocol 1。

**Spec:** 用户本任务确认的五项验收；稳定接口与使用约束同步入 `docs/ARCHITECTURE.md`，不另建平行权威规范。

## 全局约束

- 不统一时间模型，不增加增量渲染、版本树或回滚 UI。
- 不修改 user-inbox、原 FCPXML 或 FCP 资源库，不升级 runtime。
- 所有 Vn 受控写入复用 manifest_transaction；新 Review 写入保持全量 Schema 校验。
- 原始闭环 manifest 字节进入归档；活动 A13 使用新轮次评论记录，旧历史格式不静默修正或提升批准。
- 用户执行真实 A11/A13 审批、A14 授权及 D5 验收；自动化模拟不声称真实通过。
- 不 commit、push 或安装；当前开发分支 `codex/rework-lifecycle`。

## 1. 通用重开与归档

- [x] 在 `tests/test_rework_lifecycle.py` 写失败用例：非闭环拒绝、motion 保留 A11、static 只失效选中 cue、原 manifest/审核媒体可追溯、失败回滚、重复重开拒绝。
- [x] 实现 `scripts/rework_lifecycle.py`：`begin_rework(root, changes, reason)`；changes 是 cue ID 到 `static`/`motion` 影响集合的映射。只接受闭环的 Vn 和已存在动画 cue。
- [x] 实现 `scripts/rework_state.py`：修订身份、当前交付目录、阶段 evidence 修订校验。缺省为旧轮次 0，第一次返工为 1。
- [x] 归档目录为 `rework/history/rNNNN/`，保存文件哈希清单和原始 manifest、配置、布局、媒体及状态；不递归复制历史归档、依赖缓存和非当前交付修订。封存失败不发布活动新状态。
- [x] 归档后建立当前轮次，保留 A1–A10 与无关 A11，重建 A12–A14、D-stage 工作 evidence；更新 Schema 并验证。

## 2. Demo 生成证据

- [x] 写失败回归：运动变化后旧视频不能重新登记为新输入；渲染期间输入漂移不能登记；新 Demo 能进入 A13。
- [x] 新增 `scripts/render_demo.py` 负责完整 Demo 生成，生成前记录输入，结束时复核并保存视频哈希与生成 evidence。
- [x] `workflow_review.register_demo` 要求匹配的生成 evidence；历史闭环 evidence 只读兼容，不因新要求自动失效。
- [x] 现有测试采用明确的测试生成夹具，不能在生产登记入口保留无 evidence 的后门。

## 3. 修订交付与再次闭环

- [x] 写失败用例：旧 MOV 不阻断新修订渲染、旧 A14/D2/D5 不能用于新轮次、相同媒体也可区分修订、再次闭环后可重开下一轮。
- [x] renderer、资产登记、包构建和 resolver 共用当前修订交付目录；0 轮路径兼容，新轮为 `delivery/revisions/rNNNN/`。
- [x] 新 A12–D6 evidence 绑定修订，包指纹对返工轮次包含修订号；不改变 XML 时间语义或旧包身份。
- [x] Review 展示当前返工修订及归档索引，不增加回滚操作或版本树。

## 4. 集成、文档和真实样本

- [x] 更新 README、SKILL、AGENTS、ARCHITECTURE、DECISIONS、CURRENT，说明通用重开命令、Demo 生成、历史与新审批边界。
- [x] 执行全套 unittest、Skill 校验、Stage Contract 检查、git diff --check；独立审查稳定 diff。
- [ ] 真实 Vn 先只读预检并记录原文件哈希；用户给出具体镜头修改后，用正式入口重开，验证归档和无关批准保持。
- [ ] 完成指定局部修改并生成新审核材料；由用户执行必要审批后，再按当前授权生成全套新交付并等待 FCP 验收。
- [x] 按实际证据报告自动化和真实验收进度，不把等待用户动作写为完成。

真实样本入口已在隔离副本核验：重开至 r0001/A12，五镜 A11 保持、归档校验有效。原始 Vn manifest 哈希不变。真实局部改动及新轮用户审核/交付验收仍待具体修改要求；不得以自动化模拟替代。
