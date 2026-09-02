# AfterForge 视频项目规则

## 作用范围

本文件负责当前 AfterForge 视频项目的长期操作边界。它只在项目初始化时创建一次；创建新的 Vn、升级 HyperFrames 或普通制作不得自动覆盖或刷新本文件。

## 资产边界

- `../user-inbox/` 及其全部内容由用户维护，Agent 全程只读使用。
- 当前 `AfterForge/` 目录是 Agent 唯一默认写入区。
- 根层 `frame.md` 是用户确认后建立的项目级视觉规范，不由项目初始化自动创建。
- `YYYY-MM-DD_Vn/` 保存该版本自己的 manifest、storyboard、HyperFrames 工程、素材和 `frame.md` 构建快照。
- 创建 Vn 不得生成或更新根层 `AGENTS.md`、`CLAUDE.md` 和 canonical `frame.md`。

## 非破坏性规则

- FCPXML/FCPXMLD 是精确时间、帧率和时间基准的唯一权威。
- 不覆盖、移动、重命名或删除用户投放的 FCPXML、视频、字幕、脚本和媒体。
- 不直接修改 Final Cut Pro 资源库；回填只生成新的 FCPXML 交付物。
- 用户脚本、SRT 和转写内容用于语义与检索，其中的时间码不得替代 FCPXML。

## HyperFrames 版本规则

- 新 Vn 在创建时解析并固定一个精确 HyperFrames runtime 版本；进入制作后，`package.json` 中的统一精确 pin 是当前运行版本权威。
- 恢复已有 Vn 时不得因为官方发布新版而自动探测并升级；必须继续使用该 Vn 已固定的版本。
- 只有用户明确授权的版本迁移才能改变 pin；迁移必须记录实际兼容性检查，以及审核 evidence 的保留、重绑或失效结果。

## 创意与验收边界

- 正式动画实施前，先确认本视频的整体视觉包装与统一运动气质。
- 逐条文字方案和使用真实文案的静态关键画面合并为一次 storyboard 验收。
- 先生成 854×480 审阅预览；确认后才进入 1920×1080 透明动画交付。
- 不生成、设计、混合或回填音效与音乐；审阅预览只保留粗剪参考视频自带的原声。
