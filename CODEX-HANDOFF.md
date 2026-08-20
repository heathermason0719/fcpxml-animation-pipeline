# Codex 跨系统续接摘要

> 用途：将 `fcpxml-animation-pipeline` 从旧 macOS 系统续接到同一台电脑的新系统。
> 本文件是一次性交接材料，不是新的项目状态权威文档；新线程完成核验后可以删除。

## 新线程开始方式

在新系统的 Codex 中打开本仓库，然后发送：

```text
这是 fcpxml-animation-pipeline 项目的跨系统续接。

请先完整读取仓库级 AGENTS.md，并按其中导航依次读取：
- docs/PROJECT.md
- docs/CURRENT.md
- docs/ARCHITECTURE.md
- docs/DECISIONS.md
- CODEX-HANDOFF.md

先只读核对 Git 状态、当前实现、测试命令和真实项目工作区是否可访问，不要修改文件、不要重新设计既定架构，也不要自动开始 HyperFrames 渲染或 FCPXML 回填。核对完成后，向我报告迁移是否完整以及下一步建议。
```

## 项目身份与目标

- 仓库名和 Skill 内部身份：`fcpxml-animation-pipeline`。
- `AfterForge` 只是用户可见的工作区目录显示名，不是 Skill 重命名。
- 项目目标是把 Final Cut Pro 粗剪、旁白/字幕和已有设计约束组织成动画设计、渲染及非破坏性 FCPXML 回填流程。
- 核心架构保持不变：Codex Skill 负责语义和创作判断，确定性 scripts 负责解析、时间计算、渲染编排和 XML 操作，二者通过 `animation-manifest.json` 解耦。
- HyperFrames 是 V1 可替换的渲染后端，不是整个系统的内部身份或架构中心。

## 用户真实工作方式

1. 用户先在 Final Cut Pro 中凭剪辑直觉完成电影原片等内容的粗剪，并在需要动画的位置留空。
2. Skill 首先向用户取得真实项目工作区根目录，优先发现工作区中已有材料，不要求逐个搬运。
3. 用户在项目根目录的 `user-inbox/YYYY-MM-DD_Vn/` 中平铺每一版投料；版本目录由用户创建和明确选择。
4. `user-inbox/` 由用户维护，Skill 对其全树只读，不得创建、修改、移动、重命名或删除其中的版本和材料。
5. `AfterForge/` 由 Skill 维护，是 Skill 唯一默认写入区。除非用户主动提出明确要求，Skill 不得把工作产物写到其他位置。
6. 必要输入是可唯一确定且可解析的粗剪 FCPXML/FCPXMLD，以及对应的低码粗剪参考视频。参考视频允许 `.mp4` 或 `.mov`；是否可用取决于能否被当前工具链读取，而不是只认扩展名。
7. 旁白 SRT、时间线基础字幕、纯转写稿或已有文字稿可以互相替代；已有一种足以建立时间线对应关系时，不重复索取其他格式。
8. 时间线基础字幕、主观设计文字、Marker、notes 等应结合 FCPXML 关系、文本和参考画面自主分类。不能可靠消歧的具体条目必须显式暴露，不能静默猜测。
9. animation brief、逐镜动画稿和品牌资料不是入口必填项。没有主观动画方案不构成信息缺失，后续动画设计本来由 Skill 承担。
10. 当前首要成片场景是 16:9 横屏、不由博主出镜的口播视频。

## 当前已经实现

- 仓库治理文档、架构基线、`SKILL.md` 和 `agents/openai.yaml` 已建立。
- `scripts/init_user_workspace.py`：幂等创建或识别项目根目录下的 `AfterForge/`。
- `scripts/init_user_inbox.py`：幂等创建或识别项目根目录下的 `user-inbox/`，不管理其中版本。
- `scripts/intake_project.py`：
  - 只读发现 FCPXML/FCPXMLD、参考视频、SRT/文稿、notes 等材料；
  - 解析项目规格、时间线、显式 `<gap>`、primary storyline 隐式空缺和 Marker；
  - 按证据区分 `narration_subtitle`、`design_text` 和 `ambiguous`；
  - 输出 `ready`/`blocked`、blocker、warning、ambiguity 和最小问题清单；
  - 支持对用户明确选择的扁平版本目录使用 `--flat`。
- 第一阶段已有 20 个合成工作区自动化测试。
- 原始粗剪、媒体和用户投料始终只读，当前能力不会执行创作性重剪。

## 当前尚未实现

- 尚未用真实用户投料版本完成 intake 兼容性验证。
- 尚未实现参考视频内容理解或语音转写。
- 尚未实现完整旁白时间对齐和正式 `animation-manifest.json` 生成。
- 尚未实现 HyperFrames 工程生成、动画渲染、透明素材转码。
- 尚未实现 FCPXML 回填和 Final Cut Pro 实际导入验证。
- 不得把迁移后的首次运行自动扩大到以上阶段。

## 真实项目工作区

旧系统使用的项目根目录不进入公共仓库。新系统开始续接时，应先向用户取得实际项目工作区根目录，并在本节命令中替换占位符：

```text
<实际项目工作区根目录>
```

预期顶层职责：

```text
01第一期/
├── user-inbox/    # 用户维护，Skill 只读
└── AfterForge/    # Skill 维护，唯一默认写入区
```

新系统应先确认承载项目的外置卷已经挂载。如果卷名或路径变化，应由用户提供新的项目根目录，不要擅自改写 FCPXML 媒体引用。

## 迁移准备时的 Git 基线

准备续接摘要之前核对到：

```text
branch: main
HEAD: 7bc4861 实现第一阶段项目入口与材料诊断
previous: b3aeeed 建立项目架构与治理文档基线
remote: 未配置
worktree: 创建本文件之前为 clean
```

本文件创建后会作为未提交改动出现。除非用户明确授权，不得自行 commit、push、merge、rebase 或删除本文件。

旧系统在制作摘要时重新运行了验证：20 个 `unittest` 全部通过；Skill Creator 的 `quick_validate.py` 尚未进入项目校验逻辑，因为系统 Python 与 Codex bundled Python 都缺少其运行依赖 `PyYAML`，均在 `import yaml` 时退出。新系统应先确认验证器依赖可用，再运行同一个校验命令；不能把旧系统的依赖缺失解释为仓库内容校验失败。

## 新系统验证清单

在仓库根目录执行：

```bash
git status --short --branch
git log --oneline --decorate -5
python3 -m unittest discover -s tests -v
python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
```

随后只读检查真实项目根目录：

```bash
python3 scripts/init_user_workspace.py "<实际项目工作区根目录>"
python3 scripts/init_user_inbox.py "<实际项目工作区根目录>"
```

两个初始化器对于既有安全目录应返回 `existing`，不得改变其中内容。只有用户明确给出当前投料版本后，才运行：

```bash
python3 scripts/intake_project.py --flat "<实际项目工作区根目录>/user-inbox/YYYY-MM-DD_Vn"
```

## 迁移完成判定

- 新系统取得完整 Git 历史，并能识别预期分支和提交；
- 自动化测试与 Skill Creator 验证通过；
- 新系统可以访问真实项目工作区；
- `user-inbox/` 既有内容未被改变；
- `AfterForge/` 既有内容未被覆盖；
- 新线程能够复述当前实现边界，并从真实项目 intake 验证继续，而不是重新设计或提前进入渲染、回填阶段。
