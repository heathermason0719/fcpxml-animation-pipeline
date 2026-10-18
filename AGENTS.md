# Agent 工作说明

## 范围与阅读

本仓库开发 `fcpxml-animation-pipeline` Skill。只执行当前授权工作，不自动扩大到真实动画制作、输入修改、安装、发布或 FCP 导入。

非平凡任务先读 `docs/PROJECT.md` 和 `docs/CURRENT.md`。涉及 Skill 结构、数据流、渲染、FCPXML 或接口时读 `docs/ARCHITECTURE.md`；涉及架构、选型、产品边界或推翻既有决定时再读 `docs/DECISIONS.md`。

新版操作词汇以 `references/work-model-contract.json` 为准。只有解释 schema 2.0 历史、维护 legacy 工具或处理旧阶段合同时，才读 `references/workflow-stage-contract.md`；Stage ID 和正式名称以对应 JSON 为 canonical。新版生产不调用旧 resolver，不维护 currentStage/blockingStage/nextEligibleStage。

新 2.2 制作每条动画先有真实概念图；未确认可自由改图；采用候选只选择推荐图，明确确认概念后才发布代码及渲染。仅用户明确要求改概念时开启新确认轮次；普通制作反馈保留确认。

初始设计与反馈修改均遵循 `SKILL.md` 的创意澄清、概念图迭代、素材选择和运动默认；概念提示词与比较方法见 `references/visual-grammar.md` 第 4 节。Agent 负责看图、筛选和必要的多轮修改，不把每次生成都交回用户判断；不将某次审美取舍固化为通用风格或新增批准门。不让用户选择 static/motion 或办理阶段回退。

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
- 创作图片生成或导入后及时复制到本版 `.staging/creative-inputs/<round>/` 中转，并经 concept/register 登记全部候选到 `assets/concepts/`，非推荐稿用 recommend:false。参考图与提示词经 update 发布到 `assets/design-inputs/`，实际制作素材到 `assets/materials/`；引用使用版本内受控路径，原工具路径仅供来源追溯。`.codex` 输出及系统临时目录不能是创作唯一可依赖副本。合法中转、缓存和已有历史文件不因此自动迁移或清理。
- 开发、测试、构建与 UX 验收产物统一收纳到本仓库已忽略的 `work/<轮次>/`，跨轮沿用 `work/` 父目录；本轮为 `work/review-integration-20261018/`。测试源码留在 tests，不把运行生成物混入源码或分散到临时目录。
- 所有受控版本 writer 复用 manifest_transaction，读取、更新、发布/回滚在同一版本锁；项目与版本同锁时先项目后版本。长任务固定输入快照、释放锁执行，发布前复核实际内容与用户决定。
- .afterforge-manifest.lock 是稳定协调文件，不随 manifest 原子替换删除。仅给最终 save 加锁不能保护前面的旧读取。
- 保持源帧率与有理数时间。runtime 固定精确 pin，普通恢复不查询 latest；安装及实际迁移需明确授权。
- 静态 layout 仅限受控声明式内容，静态 host 不加载用户脚本或 vendor JS。所有可执行/时间驱动来源及依赖绑定变更按完整 closure 核验受影响 Cue；动态计算引用显式声明。runtime bootstrap 属于基础设施，普通 edit 不改 runtime 配置文件。
- schema 3.0 工作稿可继续修改，但已发布正式目录与 releases 证据不可覆盖。schema 2.0 原位保留，新工作模型只读；继续制作显式 copyFrom 创建新版本，不继承历史批准。
- `copyFrom` 必须有 commission 并明确 restart 或逐动画 Cue 的 new/continue continuity；continue 仅保留 qualification provenance。展示目标缺失默认拒绝，allowDraft 只是 unfinished 讨论；明确 exclusion 可完成受限委托但不能形成正式 full Review。历史过早完成以附加 correction evidence 处理，不改写历史。
- 正式交付遵循 JSON 合同的协议 3：浅层普通目录中同级 XML 与全部 AfterForge 动画 MOV（包含历史复用、嵌套资源），媒体哈希/inode 唯一；只允许硬链接复用，不退回复制。releases 仅保留轻量元数据/XML，不复制媒体或工程大资产。旧发布入口只读。
- 正式交付边界是受保护的仓库级基础设施。普通动画制作、修改、渲染、审核和正式交付任务可以按现有协议使用交付系统，但不得为完成这些任务修改、绕过、降级或替换交付合同、当前交付协议、正式发布校验器或其合同测试；这些文件不能被当作普通任务的实现手段。只有用户明确委托修改正式交付协议、交付目录规则或交付基础设施本身时，才可修改该边界。此保护仅限正式交付，不扩展到 Storyboard、Demo、创作流程或其他制作能力，也不引入通用权限或审批机制。
- 正式交付必须完整覆盖全部 animated cues 及源资源图内沿用动画，绑定当前完整审阅的批准与授权，允许明确合并指令。冻结或渲染成功不产生授权。
- 首次设计、反馈轮次、静帧、完整审阅和交付分别记录。新独立想法使用有来源的 `objectRelations`；普通继续编辑不产生新授权边界。完整 Demo 使用 taskId 并区分工作、时间和展示范围；完成后只可同 job 重试。
- 首次协议 3 的实际 FCP round-trip 建立基线；自动测试不能冒充实际导入/验收。
- 媒体、渲染、日志、临时文件、凭据与环境配置不进入版本控制。
- 临时 QA 环境异常只有在目标环境复现或有实际可用性受损证据时才修复，不单独当交付故障。

恢复工作时读取 `status.workingIntent.items`；按用户原话定向维护 focus/preserve，泛泛继续不清空，失效定位由 Agent 修订且不形成阻塞。意图不进入资格或渲染/审阅/交付指纹，不存入系列创作记忆。局部 animationNotes 随帧重组维护引用，2.2 首次确认针对概念图，Storyboard 只检查实际制作；纯说明通过预览发布新快照并复用已验证 PNG。

审核页的单场 Storyboard／动画确认仅保存绑定当前内容的审阅进度，不授予制作或交付、不改变概念首次资格，也不是普通继续制作的新硬门。部分推进必须列明包含与排除场景；提交反馈只交棒，不隐含下一轮完整 Demo 委托。

固定 runtime 配置与 vendor 由 runtime writer 维护身份；bootstrap 和同指纹修复不产生 Motion 授权。反馈随产品对象与实际采用的候选输入关联，技术改名或摆放变化不自动解决旧反馈。

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

2.2 概念优先真实验收分 prepare / render；prepare 输出目录必须不存在，生成图须实际来自图像工具，外部图须有真实来源。浏览器确认仅在隔离工程模拟，render 读取持久化确认图并产出 PNG/MOV。旧 real/review harness 明确使用 2.1 历史 fixture；事故恢复保持历史源合同，不代替新版验收。

```bash
.venv/bin/python -B tests/work_model_concept_smoke.py prepare --run --root work/concept-check --generated-concept /absolute/generated.png --external-concept /absolute/external.png --annotation-concept /absolute/annotation.png --source-frame /absolute/source.png --poster-frame /absolute/poster.png --font-source /absolute/chinese.woff2 --gsap-source /absolute/gsap.min.js --runtime 0.8.146
.venv/bin/python scripts/serve_workflow_review.py work/concept-check/AfterForge --port 8788
# 在隔离 Review 查看并确认三图，刷新、重启服务、重新 open 后执行：
.venv/bin/python -B tests/work_model_concept_smoke.py render --run --root work/concept-check
```

显式隔离真实渲染回归（输出目录必须不存在，本地 runtime 与 vendor 预先可用）：

```bash
.venv/bin/python -B tests/work_model_real_smoke.py --run --root work/real-check --runtime 0.8.33 --gsap-source /absolute/local/gsap.min.js --font-source /absolute/local/chinese.woff2
```

上一个命令加 `--cold-only` 可在交棒后、首次确认与 Motion 编写前保留冷启动快照及视频调用计数。

正式 Storyboard 与真实事故恢复使用只读历史源的隔离副本；模拟用户决定只留在副本中。输出目录必须不存在：

```bash
.venv/bin/python -B tests/work_model_review_smoke.py --run --root work/review-check
.venv/bin/python -B tests/work_model_review_smoke.py --run --review-content --root work/review-content-check
.venv/bin/python -B tests/work_model_production_recovery.py --run --root work/recovery-check
.venv/bin/python -B tests/work_model_agent_scenarios.py prepare --root work/agent-check
.venv/bin/python -B tests/work_model_agent_scenarios.py observe --root work/agent-check --case cold-continue
.venv/bin/python -B tests/work_model_agent_scenarios.py act --root work/agent-check --case cold-continue --action preview --request-file /tmp/agent-request.json
.venv/bin/python -B tests/work_model_agent_scenarios.py verify --root work/agent-check
```

Agent 场景要求实际 Agent 根据原话选择请求，对每个 case 执行 observe/act；没有自动语义路由器。prepare 使用媒体 stub，实际渲染另由真实 harness 证明。

仅验证审核 UI 时，可从显式只读 schema 3.0 制作版生成独立字节副本；输出目录必须不存在，副本移除交付及整片批准／交付决定，只在副本模拟反馈和确认，不执行渲染或实际交付：

```bash
.venv/bin/python -B tests/review_ui_fixture.py --source-version /absolute/read-only-version --root work/review-ui-check
.venv/bin/python scripts/serve_workflow_review.py work/review-ui-check/AfterForge --port 8796
```

旧命令只按 [legacy 生产说明](references/legacy/production-v2.md) 和旧合同维护，不用于新版普通制作。新增验证命令必须同步本节与 CURRENT。

## 同步规则

稳定使用方式变更更新 README；Agent 约束/命令更新 AGENTS；目标/边界更新 PROJECT；可靠状态/待验证项更新 CURRENT；架构/接口更新 ARCHITECTURE；重要决定新增或推翻同时更新 DECISIONS。只在当前授权范围内修正文档，以代码、Git 和可复现验证为准。

概念页分镜交棒使用 concept-handoff 原子保存待确认图与包含／排除对象范围；恢复读取 status.conceptDesign.storyboardHandoff，不新增制作门或 Motion／Demo／交付授权，不自动启动 Agent 或渲染。写入成功后刷新失败保留回执并只重试读取。

第一轮审核闭环合成验收（已缓存本地 runtime/vendor；prepare 输出目录须不存在）：

```bash
.venv/bin/python -B tests/work_model_review_loop_smoke.py prepare --run --root work/review-integration-20261018/round1-loop --vendor /absolute/local/gsap.min.js --runtime 0.8.146
# 打开 first-stdout.json 的 reviewEntry.url，保存意见并点击明确返修，再执行：
.venv/bin/python -B tests/work_model_review_loop_smoke.py revise --run --root work/review-integration-20261018/round1-loop
```

同一浏览器页等待新版提示，继续审旧片保存意见后手动查看新版；产物绑定及异常边界由自动测试补足。此合成验收不修改用户作品、不执行正式交付或 FCP 操作。
