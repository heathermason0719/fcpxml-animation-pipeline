# Project Intake Phase One Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一个只读项目入口，使 Skill 能从用户给定工作区发现粗剪材料、解析 FCPXML 时间线、识别待动画空缺、区分文字用途，并准确判断是否已具备进入后续分析的最低信息。

**Architecture:** `SKILL.md` 负责工作区优先、最少询问和歧义升级策略；`scripts/intake_project.py` 使用 Python 标准库完成确定性发现、FCPXML 解析、时间计算、文字分类和 JSON 诊断。工具只读取工作区并向 stdout 或显式输出文件写报告，不修改任何源项目文件。

**Tech Stack:** Python 3.11 标准库、`unittest`、XML ElementTree、Codex Skill 目录规范。

## Global Constraints

- 本阶段不生成 HyperFrames 动画，不回填 FCPXML，不修改 Final Cut Pro 资源库。
- FCPXML/FCPXMLD 和低码粗剪参考视频是最低必要输入；已有旁白 SRT、转写稿、时间线字幕或参考视频音频证据应被复用。
- 动画 brief 不是必填项；现有 Marker、设计文字和 notes 是约束材料，没有时不构成阻塞。
- 所有时间使用精确有理数解析；原始输入始终只读。
- 无法可靠区分的文字必须进入 `ambiguities`，不得静默猜测。
- 本轮不 commit。

---

### Task 1: 工作区发现与最低输入判断

**Files:**
- Create: `tests/test_intake_project.py`
- Create: `scripts/intake_project.py`

**Interfaces:**
- Consumes: `scan_workspace(workspace: Path) -> Discovery`
- Produces: `analyze_workspace(workspace: Path) -> dict[str, Any]` 和 CLI `python3 scripts/intake_project.py WORKSPACE`

- [x] **Step 1: 写入失败测试**

测试至少覆盖：自动发现单一 FCPXML、参考视频、SRT/文字稿和 notes；缺少 FCPXML 或参考视频时返回带原因的 blocker；已有足够信息时不生成多余问题；扫描不修改输入文件。

- [x] **Step 2: 运行测试并确认因入口模块缺失而失败**

Run: `python3 -m unittest tests.test_intake_project -v`

Expected: FAIL，原因是 `scripts.intake_project` 尚不存在。

- [x] **Step 3: 实现最小发现与诊断模型**

实现文件分类、候选排序、歧义暴露、`blocked`/`ready` 状态和 JSON CLI；只在必要输入缺失或多个同级必要候选无法选择时生成问题。

- [x] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_intake_project -v`

Expected: PASS。

### Task 2: FCPXML 时间线空缺与文字证据分析

**Files:**
- Modify: `tests/test_intake_project.py`
- Modify: `scripts/intake_project.py`

**Interfaces:**
- Consumes: `parse_fcpxml(path: Path, transcript_sources: list[Path]) -> TimelineAnalysis`
- Produces: `timeline.gaps`、`timeline.text_items`、`timeline.markers`、`ambiguities`

- [x] **Step 1: 写入失败测试**

使用最小真实结构的合成 FCPXML，断言显式 `<gap>` 和 spine 子项之间的隐式空缺都被报告；时间以有理数字符串保存；原 spine 顺序与源文件摘要不变。

- [x] **Step 2: 运行新增测试并确认因功能缺失而失败**

Run: `python3 -m unittest tests.test_intake_project.IntakeTimelineTests -v`

Expected: FAIL，缺少 gap 和 timeline text 分析结果。

- [x] **Step 3: 实现最小 FCPXML 分析**

解析 `.fcpxml` 及 `.fcpxmld` 内 XML；读取 sequence/spine；按 `offset`、`start`、`duration` 计算显式与隐式空缺；提取 caption、title、marker 及文本内容，不写回 XML。

- [x] **Step 4: 实现可验证的文字分类**

按证据输出 `narration_subtitle`、`design_text` 或 `ambiguous`：caption 元素、角色/名称关键词、与外部 SRT/文本的规范化匹配属于可解释证据；证据冲突或不足时进入 `ambiguities` 并列出原因。

- [x] **Step 5: 运行测试确认通过**

Run: `python3 -m unittest tests.test_intake_project -v`

Expected: PASS。

### Task 3: Skill 入口与渐进披露资料

**Files:**
- Create: `SKILL.md`
- Create: `agents/openai.yaml`
- Create: `references/project-intake.md`
- Modify: `tests/test_intake_project.py`

**Interfaces:**
- Consumes: 用户提供的实际工作区路径。
- Produces: Skill 的第一条动作是运行 intake CLI，并根据 `status`、`blockers`、`ambiguities` 和已发现材料决定继续或提问。

- [x] **Step 1: 写入 CLI 行为测试**

通过 subprocess 运行真实 CLI，断言 JSON 可解析、退出码区分 ready 与 blocked，且报告含来源路径、证据和问题原因。

- [x] **Step 2: 运行测试并确认 CLI 契约尚未满足**

Run: `python3 -m unittest tests.test_intake_project.IntakeCliTests -v`

Expected: FAIL，缺少完整 CLI 契约。

- [x] **Step 3: 初始化并编写 Skill 文件**

使用 `skill-creator` 初始化模板，精简 `SKILL.md`；把输入语义、报告字段和提问门槛写入 `references/project-intake.md`；生成与 Skill 一致的 `agents/openai.yaml`。

- [x] **Step 4: 完成 CLI 契约并运行测试**

Run: `python3 -m unittest tests.test_intake_project -v`

Expected: PASS。

### Task 4: 文档同步与最终验证

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/PROJECT.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CURRENT.md`

**Interfaces:**
- Consumes: 已验证的第一阶段真实能力和命令。
- Produces: 与代码、测试和当前边界一致的权威文档。

- [x] **Step 1: 更新稳定能力、命令和阶段边界**

记录工作区入口、可选输入发现、必要输入规则、测试命令、已验证能力和仍未实现的 HyperFrames/回填边界。

- [x] **Step 2: 运行完整验证**

Run: `python3 -m unittest discover -s tests -v`

Expected: 全部 PASS，无 warning 或 error。

- [x] **Step 3: 验证 Skill 结构**

Run: `python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .`

Expected: Skill validation passed。

- [x] **Step 4: 检查源码和文档一致性及未提交 diff**

Run: `git diff --check && git status --short && git diff --stat`

Expected: 无空白错误；仅出现本阶段新增/修改文件；没有 commit。
