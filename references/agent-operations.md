# Agent 常用操作细节

日常入口见 [SKILL](../SKILL.md)。本页只解释参数与例子；词汇与身份以 work-model-contract.json 为准，写入仍走原 update 事务。

## 创建、工作意图与预览参数

When resuming a version, read `status.workingIntent.items` as well as current feedback. These mutable focus/preserve reminders are user requirements, but never approval, qualification or a production gate. Update them through `update operation: "working-intent"` with explicit `upserts` / `removeIds`; each upsert supplies stable `id`, `kind`, `text`, `locator` (readable `description`, optional object/Cue/frame/note IDs) and the actual user `source`. The writer supplies `updatedAt`. Replace only requirements superseded by the user's words, keep unrelated preserve items, and never clear them on a generic “continue”. After regrouping frames, repair locators where known; a stale locator does not block work or erase its text/source. Do not store this temporary intent in series memory or copy it into a new version automatically.

The first command lists existing episodes/versions. Creation supplies `requestId`, project `expectedRevision`, and `episodeTitle`, or an existing `episodeId`. Explicit `commission: {channel, text, reference}` records cross-version copying or adoption of series defaults. A `copyFrom` request must also choose `copyMode: "restart"`, or provide `objectContinuity` for every animated target Cue as `{kind:"new"}` or `{kind:"continue",sourceObjectId:"..."}`. Continuation retains only prior qualification provenance; a fresh 2.2 version still needs its own confirmed concept image. It never transfers a Review, approval, or Demo authorization. When defaults exist, state `useSeriesDefaults: true|false`; do not infer adoption from paths. Multiple plausible input candidates require canonical `inputSelection: {fcpxml, reference_video}`. `selections` remains a compatible alias, but if both fields are supplied their normalized complete maps must match; no field wins a conflict. Ranking is descriptive only, and delivery currently requires one Project sequence. Optional `brief` allows text-only planning; `inputDirectory` explicitly binds a user's existing input version; `copyFrom` creates a new working copy. IDs and paths are returned by the API. Input folder names, production versions and delivery numbers are different identities.

Preview accepts `scope: "storyboard"`, `"exploration"`, `"full"`, or local `cueIds`/`segmentIds` or an explicit rational `range: {start,duration}`. Static frame states and Cue-local times live in `cue.storyboard.frames`; `scope: "still"` selects one Cue's registered static frames. Optional global `time` instead captures an individual sample at that exact Cue-local offset; it does not replace the required Storyboard collection. Local Motion ranges include the affected segment plus two seconds of context, clamped and snapped to source frames. Motion preview requires bound FCPXML/reference video and enough narration context. A requested presentation with missing animated layers is rejected by default. `allowDraft: true` explicitly creates only a discussion draft and cannot finish the task or create a complete review set until the target is covered. An explicit exclusion can satisfy the current commission, but never produces formal full Review coverage.

## 有限局部 Cue 更新

```json
{"requestId":"edit-a-1","expectedRevision":12,"operation":"edit","cueUpdates":[{"cueId":"a","changes":{"finalAnimationDescription":"先出现标题，收尾停住。","resolvedTimeline":{"start":"7s"}}}]}
```

允许 title、purpose、visualPlan、narrationAnchor、finalAnimationDescription、screenText、segmentIds、contentContext、storyboard、resolvedTimeline、layer、status。未提供的字段保留；字典递归合并，数组整体替换，不用 null 作为删除指令。同请求不能同时有 patch.cues；不支持 Cue 删除、改名、objectId／productionMode／adapter 改绑或 JSON Patch。需要技术重组时继续用既有完整 edit 和 objectRelations，并尊重用户范围。

files、work、requestId、expectedRevision、Schema、概念依据和真实依赖范围校验不变；一个 cueId 不能掩盖共享 CSS/JS 对其他场景的影响。

## 批量候选登记

```json
{"requestId":"candidates-1","expectedRevision":13,"operation":"concept","action":"register-batch","items":[{"cueId":"a","imageSource":"<version-root>/.staging/creative-inputs/round-1/a.png","origin":{"kind":"user-imported","reference":"实际来源"},"idea":"简明画面想法","motion":"简明运动想法","recommend":false}]}
```

每项沿用单张图的 imageSource、origin、idea、motion 和 cueId 校验，并必须明确 recommend。每个对象每批最多一张 true；全 false 合法，已有推荐保持不变。批内任一项失败整批不发布；重试原请求去重。adopt 不属于批量登记参数；登记、推荐与确认仍是不同动作。

## 创作讨论与生图记录

先用普通 edit 保存 cues 中当前方案；creativePlanning 只追加讨论快照及调用记录，不另存可编辑方案。所有请求仍需真实的 requestId 和最新 expectedRevision，以下省略通用字段。先 present 后等待用户明确回复，不能把示例原话当成真实收口：

```json
{"operation":"creative-planning","action":"present","summary":"本轮完整待制作清单及表达关系","question":"还有需要新增的动画吗？"}
```

返回的 planId 和对象快照绑定本次清单；省略 cueIds 覆盖全部当前动画，提供 cueIds 只讨论受影响对象。close 传 `planId` 与实际 `source: {channel,text,reference}`。新方案或范围变化不能套用旧回复；同方案无关写入不失效。技术 Cue 名称不进入内容键。当前状态为 unrecorded、waiting-response、needs-discussion 或 ready；history 保存旧内容及 currentObjectIds/supersededObjectIds，不把旧想法当作当前要求。

生图之前预登记一次实际调用的全部对象。directionId/direction 是稳定风格标识及含义，同风格保留标识；问题修正用 kind: correction 并提供稳定 problemId/problem：

```json
{"operation":"creative-planning","action":"begin-image","targets":[{"cueId":"a","kind":"direction","directionId":"spatial-map","direction":"用空间关系图解释人物处境"}]}
```

返回 attempt 的 id。调用工具后将全部图复制到本版中转目录，再通过 concept/register 或 register-batch 的每项添加 `planningAttemptId` 登记（origin.kind 为 codex-generated）。先保存图片，再记录调用结果；若讨论内容已变或结果已过时，登记仍可保存图片，但推荐自动改为 false。与调用关联的登记不能用 adopt 同时确认。

```json
{"operation":"creative-planning","action":"finish-image","attemptId":"<实际id>","outcome":"generated","toolReference":"<实际工具调用引用>","note":"实际结果说明","evaluations":[{"objectId":"<实际objectId>","conceptIds":["<本次已登记图id>"],"disposition":"continue","note":"看图后的具体判断"}]}
```

disposition 可为 continue、satisfied、stop；修正需补 problemResolved 布尔值。实际工具失败使用 outcome: failed，仍提供实际 toolReference/note，计入 9 次；确证根本没有调用才用 not-called/note，不提供 toolReference。未决调用留为 pending，占用额度且阻止盲目重试／新轮，先核对工具结果。每次真正重试新建 attempt；仅写入重试使用原请求不重复计数。同一个 toolReference 不得登记为两次工具调用。一次多图计一次，多对象各计一次；直接导入的用户图不登记自主调用。

每对象每轮的 3 个方向、同问题连续 3 次未解决修正、9 次实际调用是并行停止上限；失败工具调用计总次数但不伪造看图结论。满意或明显无效可提前结束。`action: "stop", cueIds, reason` 保存提前停止；明确用户要求继续时用 `action: "continue", cueIds, source` 新开轮，保留 previousRoundId 和用户原话。换会话、改技术名字、更改方案均不自动重置额度。轮次独立于 concept.round，不改变任何制作资格或媒体指纹，也不负责调用／拦截图像工具。

## 正式 Review 目标与恢复

CLI 概念 update 和完成的 preview/resume 返回 reviewEntry。targets 保留本次所有目标；首目标兼容放在顶层。每项使用 versionId/tab 及 conceptId、storyboardId+cueId（可带 frameId）或 artifactId。概念 tab=overview，分镜 tab=storyboard，所有视频 tab=preview；local/cue 的类型和时间来自原产物。批量 URL 的 targets 为 JSON 编码数组，页面逐个精确定位；明确目标缺失不会改看其他结果。status.storyboard.snapshots 提供不可变历史快照。

内部生成可用 `--no-review-entry` 暂不启动服务，仍保留 query、targets 和 reopen。面向用户交棒必须得到可用的正式 URL；内部暂不交棒不等于可以用媒体直发代替。服务失败时复用回执中的 reopen 命令及 query 重开已有服务，或用原请求重试入口；不能生成新 requestId 重做已完成工作。媒体／登记成功与入口在线分别判断。

## 短查询与详情

status --summary 从同一完整 status 判断派生，不加新的状态权威。creativePlanning 包含当前方案依据、待回复事项及各对象实际／未决调用、方向数和停止原因；摘要不搬运整段历史，--cue-id 和完整 status 保留相关 history。feedbackIndex 保留全部尚未处理的意见及原 applicability，body 超过 240 字符时标明 bodyTruncated；--feedback-id 返回完整原文与来源，包括历史／已处理记录。--cue-id 给出原 Cue、当前概念／Storyboard 详情及由共享反馈 resolver 判断适用的意见，同时保留完整待办索引供核对。不能只按 Cue ID 丢掉全片、对象、旧产物或时间意见。--summary／--cue-id／--feedback-id 只用于制作版本 status；项目列表仍使用 open。
