# Agent 工作说明

## 范围与阅读

本仓库开发 `fcpxml-animation-pipeline` Skill。只执行当前授权工作，不自动扩大到真实动画制作、输入修改、安装、发布或 FCP 导入。

非平凡任务先读 `docs/PROJECT.md` 和 `docs/CURRENT.md`。涉及 Skill 结构、数据流、渲染、FCPXML 或接口时读 `docs/ARCHITECTURE.md`；涉及架构、选型、产品边界或推翻既有决定时再读 `docs/DECISIONS.md`。

新版操作词汇以 `references/work-model-contract.json` 为准。只有解释 schema 2.0 历史、维护 legacy 工具或处理旧阶段合同时，才读 `references/workflow-stage-contract.md`；Stage ID 和正式名称以对应 JSON 为 canonical。新版生产不调用旧 resolver，不维护 currentStage/blockingStage/nextEligibleStage。

初始设计与反馈修改均遵循 `SKILL.md` 的创意澄清、素材选择和运动默认；澄清不新增批准门。不让用户选择 static/motion 或办理阶段回退。

## 文件职责

- README 是使用入口；AGENTS 是开发约束和导航。
- PROJECT 保存稳定目标/边界；CURRENT 只保留已验证能力、待验证项与下一步。
- ARCHITECTURE 保存系统职责、数据流和接口；DECISIONS 保存长期决定及适用范围。
- SKILL 是日常工作指令；scripts 是确定性工具；references 是按需合同；assets 是可复用资源。
- schema 2.0、旧生产/架构与单一布局协议位于 references/legacy，仅解释历史，不作为新版默认读取。
- 不新建任务报告、平行状态文档或重复历史汇总。

## 写入与风险

- 原 FCPXML/FCPXMLD、旁白、字幕及媒体只读，不直接改 FCP 资源库。默认写入区仅 AfterForge，user-inbox 及版本目录由用户维护。
- AfterForge 是可替换的门牌，内部 ID 不变；既有 AGENTS/CLAUDE 不自动覆盖。
- 系列、单集、制作版与交付分别有稳定身份；路径由布局解析器和注册信息取得，不猜父目录层级。
- 新生产使用统一 afterforge.py。源码先放本版 .staging，再经 update 校验发布；不手工更改批准、产物或交付事实。
- 所有受控版本 writer 复用 manifest_transaction，读取、更新、发布/回滚在同一版本锁；项目与版本同锁时先项目后版本。长任务固定输入快照、释放锁执行，发布前复核实际内容与用户决定。
- .afterforge-manifest.lock 是稳定协调文件，不随 manifest 原子替换删除。仅给最终 save 加锁不能保护前面的旧读取。
- 保持源帧率与有理数时间。runtime 固定精确 pin，普通恢复不查询 latest；安装及实际迁移需明确授权。
- schema 3.0 工作稿可继续修改，但已发布包与 releases 快照不可覆盖。schema 2.0 原位保留，新工作模型只读；继续制作显式 copyFrom 创建新版本，不继承历史批准。
- 正式交付必须完整覆盖全部 animated cues，绑定当前完整审阅的批准与授权，允许明确合并指令。冻结或渲染成功不产生授权。
- 首次协议 2 的实际 FCP round-trip 建立基线；自动测试不能冒充实际导入/验收。
- 媒体、渲染、日志、临时文件、凭据与环境配置不进入版本控制。
- 临时 QA 环境异常只有在目标环境复现或有实际可用性受损证据时才修复，不单独当交付故障。

## Git

commit、push、merge、rebase、tag、release、deploy 均需当前请求明确授权；不沿用之前的一次性授权。保持已有用户修改，不顺手清理范围外文件。

## 命令与验证

首次设置且经授权才执行 `python3 -m venv .venv`、`.venv/bin/python -m pip install -r requirements.txt`。正常写入必须通过 JSON Schema，不允许缺 jsonschema 时跳过。

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
.venv/bin/python scripts/sync_workflow_stage_contract.py --check
```

日常操作：

```bash
.venv/bin/python scripts/afterforge.py open "/workspace/AfterForge" --request-file /tmp/open.json
.venv/bin/python scripts/afterforge.py status "<version-root>"
.venv/bin/python scripts/afterforge.py update "<version-root>" --request-file /tmp/update.json
.venv/bin/python scripts/afterforge.py preview "<version-root>" --request-file /tmp/preview.json
.venv/bin/python scripts/afterforge.py deliver "<version-root>" --request-file /tmp/deliver.json
.venv/bin/python scripts/afterforge.py resume "<version-root>" --request-file /tmp/resume.json
.venv/bin/python scripts/serve_workflow_review.py "/workspace/AfterForge" --port 8765
```

显式隔离真实渲染回归（输出目录必须不存在，本地 runtime 与 vendor 预先可用）：

```bash
.venv/bin/python -B tests/work_model_real_smoke.py --run --root /private/tmp/afterforge-real-check --runtime 0.8.33 --gsap-source /absolute/local/gsap.min.js
```

旧命令只按 [legacy 生产说明](references/legacy/production-v2.md) 和旧合同维护，不用于新版普通制作。新增验证命令必须同步本节与 CURRENT。

## 同步规则

稳定使用方式变更更新 README；Agent 约束/命令更新 AGENTS；目标/边界更新 PROJECT；可靠状态/待验证项更新 CURRENT；架构/接口更新 ARCHITECTURE；重要决定新增或推翻同时更新 DECISIONS。只在当前授权范围内修正文档，以代码、Git 和可复现验证为准。
