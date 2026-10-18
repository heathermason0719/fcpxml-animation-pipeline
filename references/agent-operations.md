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

## 短查询与详情

status --summary 从同一完整 status 判断派生，不加新的状态权威。feedbackIndex 保留全部尚未处理的意见及原 applicability，body 超过 240 字符时标明 bodyTruncated；--feedback-id 返回完整原文与来源，包括历史／已处理记录。--cue-id 给出原 Cue、当前概念／Storyboard 详情及由共享反馈 resolver 判断适用的意见，同时保留完整待办索引供核对。不能只按 Cue ID 丢掉全片、对象、旧产物或时间意见。--summary／--cue-id／--feedback-id 只用于制作版本 status；项目列表仍使用 open。
