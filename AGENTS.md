# Agent 工作说明

## 工作范围

本仓库用于开发 `fcpxml-animation-pipeline` Codex Skill。只执行用户当前明确授权的任务，不自动扩展到动画制作、FCPXML 修改、素材转码、发布或安装。

## 开始任务前

处理任何非平凡任务前，必须先读取：

- `docs/PROJECT.md`：项目目标、范围和约束；
- `docs/CURRENT.md`：当前可靠状态、待验证事项和下一步。

任务涉及 Skill 结构、数据流、组件边界、渲染适配、FCPXML 回填或 V1 实现时，还必须读取 `docs/ARCHITECTURE.md`。

仅当任务涉及架构、技术选型、产品边界、数据策略，或可能推翻已有决定时，再读取 `docs/DECISIONS.md`。

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

## 命令与验证

当前没有 build 或 lint 命令。使用以下命令验证第一阶段能力：

```bash
python3 -m unittest discover -s tests -v
python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
```

只读检查项目工作区：

```bash
python3 scripts/init_user_workspace.py "/absolute/project/workspace"
python3 scripts/init_user_inbox.py "/absolute/project/workspace"
python3 scripts/intake_project.py --flat "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn"
```

引入新的验证命令时，必须同时更新本节和 `docs/CURRENT.md`。

## 文档同步规则

- 稳定能力或使用方式发生实质变化：更新 `README.md`；
- Agent 约束、目录职责或验证命令变化：更新 `AGENTS.md`；
- 项目目标、范围或核心约束变化：更新 `docs/PROJECT.md`；
- 可靠能力、进行中工作、阻塞、待验证项或下一步变化：更新 `docs/CURRENT.md`；
- 出现或推翻重要架构、技术路线或产品边界决定：更新 `docs/DECISIONS.md`。
- 系统分层、组件职责、数据流、接口或实现边界变化：更新 `docs/ARCHITECTURE.md`；涉及重要路线变更时同时更新 `docs/DECISIONS.md`。
