# 当前状态

## 已可靠成立

- 仓库基础目录和权威文档结构已经按全局项目治理规则建立；
- 项目目标、当前范围、非目标、核心约束和初始架构决定已经记录；
- V1 架构基线已经正式记录在 `docs/ARCHITECTURE.md`，包括 Skill/scripts 分工、`animation-manifest.json` 中间层、可替换渲染后端、FCPXML 回填边界和 V1 工作流；
- 已建立 `SKILL.md`、`agents/openai.yaml` 和项目入口参考契约；
- `scripts/intake_project.py` 已能只读发现工作区材料、解析 FCPXML/FCPXMLD、识别显式/隐式空缺、提取 Marker，并按证据区分旁白字幕、设计文字与歧义文字；
- `scripts/init_user_workspace.py` 已能在项目根目录幂等创建或识别用户工作目录，默认显示名为 `AfterForge`，同时保持内部 ID `fcpxml-animation-pipeline`；
- `scripts/init_user_inbox.py` 已能幂等创建或识别用户维护、Skill 只读的 `user-inbox/`，且不会创建或修改任何版本目录；
- `user-inbox/` 初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录保持为空且既有 `AfterForge/` 未改变；
- 用户工作目录初始化已在一个真实项目根目录完成验证：首次返回 `created`，重复运行返回 `existing`，目录内未生成其他内容；
- 入口能以 `ready`/`blocked`、blocker、warning、ambiguity 和最小问题清单表达是否具备后续分析条件；
- 第一阶段行为已通过 20 个合成工作区自动化测试，并完成 Skill 流程对照场景验证；
- Git 仓库已经初始化。

## 尚未开始

- 尚未对真实用户项目工作区执行兼容性验证；当前自动化验证使用合成 FCPXML 和占位参考视频；
- 尚未实现参考视频内容理解或语音转写；
- 尚未实现完整旁白时间对齐和 `animation-manifest.json` 生成；
- 尚未实现 HyperFrames 调用、动画渲染、转码、FCPXML 回填或 Final Cut Pro 导入验证；
- 当前没有 build 或 lint 命令。

## 已知问题与阻塞

当前没有已知技术阻塞。真实 FCPXML 版本、复杂嵌套时间线和媒体文件的兼容性仍待实际项目验证。

## 下一步

在用户提供真实项目工作区后，先运行项目入口并核对诊断结果；后续能力仍需另行授权，不得自动扩展到 HyperFrames 动画生成或 FCPXML 回填。
