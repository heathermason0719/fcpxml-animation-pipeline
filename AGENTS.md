# Agent 工作说明

## 工作范围

本仓库用于开发 `fcpxml-animation-pipeline` Codex Skill。只执行用户当前明确授权的任务，不自动扩展到动画制作、FCPXML 修改、素材转码、发布或安装。

## 开始任务前

处理任何非平凡任务前，必须先读取：

- `docs/PROJECT.md`：项目目标、范围和约束；
- `docs/CURRENT.md`：当前可靠状态、待验证事项和下一步。

任务涉及 Skill 结构、数据流、组件边界、渲染适配、FCPXML 回填或 V1 实现时，还必须读取 `docs/ARCHITECTURE.md`。

仅当任务涉及架构、技术选型、产品边界、数据策略，或可能推翻已有决定时，再读取 `docs/DECISIONS.md`。

开始、恢复、汇报正式 invocation，或判断 stage transition 时，读取生成视图 `references/workflow-stage-contract.md`。Stage ID、正式名称和稳定职责只以 `references/workflow-stage-contract.json` 为 machine canonical；不得根据旧文档、聊天历史或记忆重新发明阶段名称。

## 文件职责

- `README.md`：面向使用者的稳定项目入口；
- `AGENTS.md`：Agent 工作约束与文档导航；
- `docs/PROJECT.md`：稳定的项目目标和边界；
- `docs/CURRENT.md`：当前状态的权威摘要；
- `docs/DECISIONS.md`：长期有效的重要决策及理由；
- `docs/ARCHITECTURE.md`：系统分层、组件职责、数据流、V1 接口与实现边界；
- 后续的 `SKILL.md`、`scripts/`、`references/`、`assets/`：分别承载 Skill 指令、确定性工具、按需参考资料和输出模板或资源。

不要新建与上述职责重叠的状态、历史或任务报告文档。

## 风险与限制

- 永不覆盖用户提供的原始 FCPXML、FCPXMLD、旁白、字幕或媒体素材；默认生成新输出。
- 第一阶段允许创建的项目顶层目录只有 `AfterForge/` 和 `user-inbox/`。`AfterForge/` 是 Skill 唯一默认写入区；`user-inbox/` 由用户维护，Skill 不得在其中创建、修改、移动、重命名或删除版本目录及材料。
- 默认显示名 `AfterForge` 只是可替换门牌号，不得替代内部 ID `fcpxml-animation-pipeline`。目录已存在时不得修改其中已有内容。
- 不直接修改 Final Cut Pro 资源库，也不把普通开发任务解释为导入、发布或安装授权。
- 处理 FCPXML 时间值时必须保留项目帧率和有理数时间基准，不能使用未经校验的浮点近似回写。
- 媒体、渲染产物、临时文件、凭据和本地环境配置不得进入版本控制。
- 发现文档与代码、配置、Git 状态或验证结果冲突时，以可复现证据为准，并仅在任务授权范围内修正文档。

## Git 操作边界

- `commit` 和 `push` 默认由用户执行；普通开发、文档更新、修复、验证或交付完成都不构成授权。
- 只有用户在当前请求中明确要求相应 Git 操作时，Agent 才可以执行；不得沿用更早轮次的一次性授权。

## 命令与验证

当前没有 build 或 lint 命令。使用以下命令验证第一阶段能力：

```bash
python3 -m unittest discover -s tests -v
python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
```

初始化并检查项目工作区：

```bash
python3 scripts/init_user_workspace.py "/absolute/project/workspace"
python3 scripts/init_user_inbox.py "/absolute/project/workspace"
python3 scripts/init_afterforge_project.py "/absolute/project/workspace"
python3 scripts/intake_project.py --flat "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn"
python3 scripts/scaffold_hyperframes.py "/absolute/project/workspace" "YYYY-MM-DD_Vn"
python3 scripts/sync_storyboard.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/layout_lock.py approve "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/layout_lock.py verify "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/assemble_hyperframes.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/sync_delivery.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/validate_hyperframes_adapter.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/migrate_delivery_layout.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/migrate_workflow_stage_contract.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/workflow_status.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/serve_workflow_review.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/render_animations.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/register_delivery_assets.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/build_delivery_package.py "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/validate_fcpxml_package.py "/absolute/project/workspace/AfterForge/AfterForge__YYYY-MM-DD_Vn__d-<fingerprint>.fcpxmld" "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn/source.fcpxml" "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn/animation-manifest.json" --dtd "/Applications/Final Cut Pro.app/Contents/Frameworks/Interchange.framework/Versions/A/Resources/FCPXMLv1_14.dtd"
python3 scripts/compare_fcpxml_roundtrip.py "/absolute/project/workspace/AfterForge/AfterForge__YYYY-MM-DD_Vn__d-<fingerprint>.fcpxmld/Info.fcpxml" "/absolute/reexported.fcpxml" "/absolute/project/workspace/AfterForge/YYYY-MM-DD_Vn/animation-manifest.json"
python3 scripts/sync_workflow_stage_contract.py --check
```

前三条初始化命令会在各自严格边界内创建缺失目录或文件；`intake_project.py` 是只读检查。命令示例中的版本名使用大写 `V`，但 `scaffold_hyperframes.py` 同时接受小写 `v`，并原样保留用户选定的拼写；若发现仅大小写不同的既有版本则阻塞。脚手架只在 canonical `frame.md` 已存在且目标 Vn 不存在时创建隔离版本工程，阻塞时不得留下半成品或修改项目级文件。Stage Contract 迁移显式作用于单个 legacy Vn，保留旧审核记录但不继承用户批准；resolver 从证据推导上下文、阻塞点、下一可执行阶段和完成集合，不维护 `currentStage`。单 Vn Review 负责 A11/A13 comment、批准和 A14 授权。原生渲染、注册、包发布、FCP 验收与 round-trip 依次形成 D2–D6 证据链；详细布局协议见 `references/hyperframes-single-source.md`，FCPXML 交付协议见 `docs/ARCHITECTURE.md`。

引入新的验证命令时，必须同时更新本节和 `docs/CURRENT.md`。

## 文档同步规则

- 稳定能力或使用方式发生实质变化：更新 `README.md`；
- Agent 约束、目录职责或验证命令变化：更新 `AGENTS.md`；
- 项目目标、范围或核心约束变化：更新 `docs/PROJECT.md`；
- 可靠能力、进行中工作、阻塞、待验证项或下一步变化：更新 `docs/CURRENT.md`；
- 出现或推翻重要架构、技术路线或产品边界决定：更新 `docs/DECISIONS.md`。
- 系统分层、组件职责、数据流、接口或实现边界变化：更新 `docs/ARCHITECTURE.md`；涉及重要路线变更时同时更新 `docs/DECISIONS.md`。
