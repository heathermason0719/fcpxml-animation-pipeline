# 当前状态

## 已验证能力

- Storyboard 局部 `animationNotes` 已接入：单帧、多帧、共享帧及无说明帧；帧重组须同步引用。总说明、局部说明、旁白、内容事实与有序帧集合冻结为 `reviewInputKey`；首次确认仍覆盖完整 Storyboard／创意对象。
- PNG 合同 5 将纯说明与图片输入分开，文字修改可零渲染复用 SHA 一致的 PNG，同时追加不可变产物和审阅快照。合同 4 按原输入核验，无法证明一致或图片损坏时重渲；发布前复核输入及输出文件。旧快照不能确认新内容，旧反馈及已有首次资格保留。
- 本版 `workingIntent.items` 通过受控 `working-intent` upserts/removeIds 持久保存，支持定向覆盖、显式移除、失效定位和并发冲突。写入不升级生产事实、不影响渲染/审阅/首次资格/交付，新版本不继承；Agent 恢复规则与只读展示已同步。
- 正式 Review 已采用顶部版本/Cue 导航、桌面三列静帧（窄屏两列）、局部说明与关联高亮、图片放大、默认展开且逐版本/对象/帧记忆的留言框和 sticky 反馈栏。新快照清除旧依据勾选，旧草稿不自动转绑。长任务准备期可持续轮询，临时任务/失败按制作版隔离；切换空白版不残留上一版媒体。后台 hero 规则不变，未增加已保存反馈编辑。
- manifest 3.0 / work model 2.1.0 / 交付协议 2 已实现。`open/status/update/preview/deliver/resume` 与通用 Review 使用同一应用层；兼容读取旧 work model 2.0.0，读取不落盘、不补资格。schema 2.0 保持 legacy 原义，新生产不调用旧阶段 resolver。
- cold-start 从真实 canonical 布局独立生成主审／辅助 PNG，支持中文字体、静态状态及对应原片背景，无需完成 Motion。首次确认引用当前可验证完整帧集合；限定探索、整版 Demo、完整 Review 批准和正式交付授权分别保存事实。
- 首次资格绑定产品创作对象。字体、构图、摆放、运动、重做以及明确的技术改名保持 active；真正新增对象不继承资格。对象关系有实质歧义才询问，不建立阶段回退。
- 工作 Cue、预览时间与 Demo 呈现范围分离。未修改的有效实现默认呈现，缓存缺失可按原实现重建；明确排除和缺少实现单独记录，不能形成完整 Review。局部上下文不扩大创作范围。发布、恢复、缓存和已完成任务返回均核验当前依据。
- Storyboard 承接通用 Review 的旁白、主审／辅助帧、最终说明、就地反馈及批量确认。“提交本轮反馈”固定反馈批次，零评论不产生批准；处理与接受分别记录。草稿保护包括原帧更新、跨版本选择、迟到响应及刷新。
- 视觉探索是可选并列工作区，候选切换无采用副作用；范围明确的采用与 canonical 源更新原子提交，候选不进入正式 Cue 集合，不授予首次确认、Demo、Review 或交付资格。
- 输入候选不按排名自动决定；多 XML／多 Project 不静默取第一个。复制和系列默认使用明确委托，不自动推导跨版本关系。通用记忆初始化中性；完整 Review 不自动接受全部 addressed，明确暂缓事项不阻塞无关成果。
- 原有有理数时间、Cue 本地时间、重叠层、依赖缓存、版本锁、请求去重、失败恢复与不可变交付继续通过回归。正式包保持原生 1920×1080 ProRes 4444、源帧率、实际 Alpha、时间线不变性与协议 2 包核验。
- Motion 发布边界由 canonical 源结构及依赖闭包统一判定，覆盖 inline script、事件、CSS／SVG 时间行为、嵌套源、播放媒体及共享依赖；不是只查 `motionSrc` 或动画关键词。独立静态宿主不执行用户脚本或 vendor JS，不能通过移除声明把 Motion 改称静态。
- 当前静帧有效与可首次确认分别投影。旁白和屏幕文字各自区分 present／none／unknown；明确无内容须有依据，未知不能被另一通道掩盖。确认仍要求非空最终说明和无相关待处理反馈。事实来自现有真实文本或关联段落，不生成假占位文字。
- 确认、批准和交付使用同一反馈适用范围解析器。未采用探索意见不阻塞正式成果；采用关联绑定真实候选源／背景指纹与产品对象。同路径修改不会沿用旧候选事实；对象改名、摆放变化不自动解决旧意见。
- runtimeIdentity 区分 bootstrap、旧环境登记、同指纹修复与真实变更。静态 Cue 可以先于首次 runtime 建立；固定 vendor 由 runtime writer 独占，初始化不产生制作依据。
- 有限静态能力模型核验 HTML／CSS／SVG 和图像实际格式；srcset、image-set、嵌套图像和字体资源进入闭包。不可确定的自动播放须改用固定采样或 seekable 实现。隔离渲染宿主用 CSP 拒绝网络，资源拒绝与本地 404 会阻止产物发布。
- 完整 Demo 默认拒绝缺失授权呈现对象，不静默缩小范围；明确 `allowDraft` 的讨论稿仍可生成，但不完成原任务。只有实际履行委托目标才登记 production run；历史误登记通过有证据的追加纠正解除，不重写历史产物。
- 跨版本明确区分 `copyMode: restart` 与逐对象 `objectContinuity`，由 Agent 落实用户决定，backend 不解析原话或猜测关系。延续仅携带有出处的首次资格，不携带整版制作、Review 或交付授权。首次 writer 完整登记缺失对象身份，不补用户批准；`inputSelection` 为公开字段，兼容 `selections`，双字段冲突明确拒绝。

## 当前验收证据

- 2026-09-22 分支提交前复核：完整 unittest 运行 449 项，448 项通过；CLI 启动测试因工作树缺少固定 `.venv/bin/python` 路径未启动。临时链接已有环境后该项单独通过，链接已移除，无代码或依赖变更。日志分别为 `/private/tmp/afterforge-precommit-20260922.log`、`/private/tmp/afterforge-precommit-20260922-cli.log`。Skill 校验、旧合同一致性与 diff 检查通过。下述 09-20 临时日志及 PNG 复用证据目录已不在本机，保留其历史验收记录，本轮未重跑真实渲染和浏览器验收。
- 2026-09-20 审核页实现：449 项 unittest 通过（原 439 项及新增 10 项，客户端场景同时增加），日志 `/private/tmp/afterforge-review-unittest-final.log`。覆盖说明快照/引用、旧合同与损坏图片、图片输入失效、发布并发、意图对批准后交付依据无影响，以及反馈、批量确认、迟到响应和 hero 原有规则。Skill 校验、旧合同一致性与 diff 检查通过。
- 真实 PNG 复用与隔离页面：`/private/tmp/afterforge-review-content-20260920-r2/evidence.json`。只读 0917 制作源的隔离副本，2 Cue / 13 张实际 PNG；首次 13 次渲染，纯说明更新 0 次，13 个 SHA 一致，产生新 Storyboard，原制作源全文件哈希未变。第一次沙箱 Chromium 启动被 macOS MachPort 权限拒绝；在获准的隔离运行环境中通过，未为此改渲染实现。
- 浏览器实操：同目录 `browser-evidence.json` 与 `browser-desktop.png`。桌面 1440×1000 下六张完整帧可同时可见，反馈栏 top=12px；600px 下为两列且无横向溢出。验证默认展开/逐帧恢复、刷新/任务轮询、说明关联/全部展开、放大/Esc、保存反馈/轮次交棒/完整 Cue 确认、新快照清勾选/保留原依据草稿/显式重绑、旧反馈保留及版本切换。页面模拟决定仅在隔离副本，未安装或迁移真实工程。

下列为既有能力的前轮证据；当前页面实现以上述 2026-09-20 记录为准：

- 第二轮 integration 修复：439 项 unittest 通过，较 383 项基线新增 56 项。日志 `/private/tmp/afterforge-integration2-fix/unittest-complete.log`；定向日志、失败复现与修正后的结果保留在同目录。Review shell、客户端代码及客户端 harness 的字节与修复前审计清单一致。
- 本轮真实 cold-start／active-loop：`/private/tmp/afterforge-integration2-real-r3/evidence.json`，本轮先发布静态 Cue 再初始化 runtime；4 个对象、5 张真实中文主辅帧，静态路径视频渲染／合成调用为 0，后续局部修改、重叠、排除、缓存重建与复用、改名和协议 2 包继续通过。
- 无旁白无文字及固定背景：`/private/tmp/afterforge-integration2-pure-visual-r2/evidence.json`，真实 PNG 可首次确认，未制造旁白或文案；GIF 背景明确记录第 0 秒及源 SHA。实际 renderer 的网络与本地缺失资源拒绝：`/private/tmp/afterforge-integration2-render-guard-r2/evidence.json`。
- 本轮成熟 Storyboard：`/private/tmp/afterforge-integration2-review-r2/evidence.json`，4 Cue／7 帧及 2 个候选；最终实际输入关联复验在同目录 `lineage-evidence.json`。
- 本轮事故恢复：`/private/tmp/afterforge-integration2-recovery/evidence.json`，160 个原文件前后 SHA 一致，历史预览与 reviewSet 原样保留且没有取得合法资格。副本从原 HTML 补齐真实屏幕文字记录后产生新输入键，18 条媒体据此重建；18 份 Storyboard 与新的合法 Review 单独建立，未批准或授权交付。未变输入的缓存复用由上述 active-loop 实测覆盖。
- 本轮 9 个 Agent 场景：`/private/tmp/afterforge-integration2-agent/evidence.json`，含明确无旁白／无文字的新场景。Demo 排除的一次参数纠正轨迹另存于对应 case 的 `trace-failed-attempt.jsonl`，保留原失败证据；结果不声称首次调用全成功。场景使用媒体 stub，不是自然语言模型通用成功率测试。

下列为前轮保留证据，不代替本轮结果：

- 383 项 unittest 通过，较复核基线净增 60 项；Skill 校验、旧 Stage Contract 一致性和 `git diff --check` 通过。日志：`/private/tmp/afterforge-21-repair-evidence/unittest-final.log`。新增定向覆盖结构发布旁路、任务履约／失败恢复、对象延续／writer 升级、反馈与确认、输入字段；原 active-loop、局部讨论、排除和客户端回归继续通过。
- 真正冷启动：`/private/tmp/afterforge-repair-real-20260919-r2/cold-start-evidence.json`。全新 open，4 个动画对象、5 张真实中文 PNG，初始无 Motion 实现；实际视频渲染／整版合成调用均为 0；交棒后确认数为 0。保留了此时 manifest，后续静态确认不倒写到这个快照。
- 创作循环：`/private/tmp/afterforge-repair-real-20260919-r2/evidence.json`。一分钟合成时间线，真实中文字体和原片背景；修改、重叠局部试做、同对象改名、新对象隔离、未修改层呈现、缓存重建、明确排除和最终协议 2 包均已运行。输入哈希未变。
- 成熟 Storyboard 基线：`/private/tmp/afterforge-repair-review-20260919/evidence.json`。从只读 `2026-09-09_v1` 显式建立隔离 fixture，4 个动画 Cue、7 张真实主辅帧及 2 个探索候选，历史源哈希不变。
- 浏览器定向操作：`/private/tmp/afterforge-21-repair-evidence/browser/evidence.json`。真实页面保存当前帧意见后仅相关 Cue 禁止确认；提交反馈只交棒，不批准；随后其他 Cue 独立确认成功，待处理意见仍保留。目录含截图、DOM 和最终 status。既有草稿、批量确认、探索切换及冲突保护由客户端回归继续验证；所有页面决定仅为隔离验收模拟。
- 事故恢复：`/private/tmp/afterforge-repair-recovery-20260919-r2/evidence.json`。同版字节复制，不使用 copyFrom 伪装冷启动；原有 3 个预览产物、2 个 reviewSet 原样保留但无当前资格，旧恢复被拒绝。补齐 18 份 Storyboard 和模拟明确决定后，18 条媒体经实际指纹／SHA／属性核验全部命中缓存，重新合成 620.96 秒 Demo 并建立新 Review。没有批准 Review 或授权交付。源目录 160 个文件前后 SHA 清单相同。
- 8 个实际 Agent 原话场景及调用轨迹：`/private/tmp/afterforge-repair-agent-20260919-r2/evidence.json`。覆盖继续、交棒后处理、批量通过、只改 A、排除 D、整版请求、技术改名及歧义澄清。语义 fixture 使用媒体 stub；它是一次可审计的 Agent 执行证据，不是自然语言路由器或通用成功率测试。

## 验证命令

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
.venv/bin/python scripts/sync_workflow_stage_contract.py --check
```

真实渲染仅使用预先可用的本地精确 runtime、vendor 和中文字体，不安装或升级依赖。所有输出目录必须不存在；本地 Chromium 需具有正常启动权限：

```bash
.venv/bin/python -B tests/work_model_real_smoke.py --run --root /private/tmp/afterforge-real-check --runtime 0.8.33 --gsap-source /absolute/local/gsap.min.js --font-source /absolute/local/chinese.woff2
.venv/bin/python -B tests/work_model_real_smoke.py --run --cold-only --root /private/tmp/afterforge-cold-check --runtime 0.8.33 --gsap-source /absolute/local/gsap.min.js --font-source /absolute/local/chinese.woff2
.venv/bin/python -B tests/work_model_review_smoke.py --run --root /private/tmp/afterforge-review-check
.venv/bin/python -B tests/work_model_review_smoke.py --run --review-content --root /private/tmp/afterforge-review-content-check
.venv/bin/python -B tests/work_model_production_recovery.py --run --root /private/tmp/afterforge-recovery-check
```

Review 与恢复项读取 harness 中明确列出的《楚门》历史源，只写隔离副本；其他机器需先具备相同只读 fixture，不能用原工程代替输出目录。Review fixture 建成后按返回的 AfterForge 路径运行通用 server，浏览器仅操作副本。

Agent 场景先准备独立状态，再由实际 Agent 根据原话选择请求；每个 case 均需 observe/act，不能仅运行 verify 冒充一次 Agent 交互：

```bash
.venv/bin/python -B tests/work_model_agent_scenarios.py prepare --root /private/tmp/afterforge-agent-check
.venv/bin/python -B tests/work_model_agent_scenarios.py observe --root /private/tmp/afterforge-agent-check --case cold-continue
.venv/bin/python -B tests/work_model_agent_scenarios.py act --root /private/tmp/afterforge-agent-check --case cold-continue --action preview --request-file /tmp/agent-request.json
.venv/bin/python -B tests/work_model_agent_scenarios.py verify --root /private/tmp/afterforge-agent-check
```

## 边界与后续

- 协议 2 尚未在 Final Cut Pro 做实际导入及 re-export round-trip；媒体、包和比较器通过不代替真实 FCP 验收。
- 当前交付仍要求单 Project sequence；多 Project 输入明确报出歧义，不扩展多 Project 交付。
- 真实工程、素材和历史交付未迁移或改写。本轮实现位于 `codex/rework-lifecycle-smoke` 工作树，以 `c60d78c` 为基础。2026-09-22 用户授权仅提交并推送当前分支；invocation 闭环前不 merge。未安装或发布。
- 动态拼接资源仍须声明依赖。没有引入后台 Agent、自动跨版本继承、数据库、云分析、转写或媒体硬链接去重。
