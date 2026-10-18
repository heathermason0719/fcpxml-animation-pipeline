# 新版制作源与媒体合同

适用于 manifest 3.0 / work model 2.2.0；已有 2.1 版本按原首次确认语义读取。schema 2.0 按 [旧单一布局协议](legacy/hyperframes-single-source-v2.md) 解释。

## 概念图与确认接口

每条动画（含简单文字和标注）先登记真实概念图，再进入代码制作。图片与 artifact/Storyboard 分开；生成图和外部图都经本版 `.staging/creative-inputs/<round>/` 中转，再发布不可变副本到 `assets/concepts/`，保留 SHA、尺寸、Cue/object、轮次、原始来源、文字快照、创意和运动说明。原图只读，不依赖聊天链接。`origin.model` 仅在实际已知时填写。

```json
{"requestId":"concept-1","expectedRevision":2,"operation":"concept","action":"register","cueId":"A","imageSource":"<version-root>/.staging/creative-inputs/round-1/concept.png","origin":{"kind":"user-imported","reference":"实际原图路径或生成调用引用"},"idea":"主要构图及表达意图","motion":"出现顺序、运动与停留"}
```

默认 `recommend: true` 设为当前推荐，`false` 仅保存候选；`action: "propose", conceptId` 切换本轮推荐。未确认可连续改稿，每次图片更新都登记新稿；历史反馈仍绑定原 conceptId。页面“采用这版候选”仅切换当前推荐，不等于确认。`action: "select", conceptId, source` 用于有用户来源的改选：当前未确认同轮等同 propose；已确认后选择另一图，原子开启新轮并以原字节建立带 `copiedFromConceptId` 的当前轮记录，选择原确认图不重开。重用历史轮次也追加当前轮记录，不改旧 round、图片或反馈；反馈归属沿复制来源链保留。明确提供图片并确认视觉方向时仍可在 register 同时传 `adopt: true` 和真实 `source`，一笔事务登记及确认；不能用它实现仅选择的采用按钮。

```json
{"requestId":"confirm-1","expectedRevision":3,"operation":"decision","kind":"confirm-concept","conceptIds":["concept-A","concept-B"],"source":{"channel":"chat","text":"用户明确采用这些图的原话","reference":"实际消息引用"}}
```

确认针对各对象当前推荐稿，整批原子校验真实图片、两渠道内容及相关未解决反馈；支持有用户来源的 `feedbackResolutions`。普通实现修改保留确认。已确认图片丢失时恢复原受控字节，不抹除历史确认。只有用户明确要求修改已确认概念时，提交 `operation: "concept", action: "reopen", cueIds, source` 开始新轮；原确认作为历史保留，新轮确认前不继续制作。未确认对象无需 reopen。

概念页顶部交棒使用以下请求；待确认图片与本轮范围在同一事务保存，全部已确认也保存记录。cueIds/conceptIds 按索引对应当前推荐图，excludedCueIds 与选中项准确覆盖全部动画 Cue；source 必须来自实际用户动作。

```json
{"requestId":"concept-handoff-1","expectedRevision":12,"operation":"concept-handoff","cueIds":["A"],"conceptIds":["<A当前推荐图ID>"],"excludedCueIds":["B"],"source":{"channel":"review","text":"按所选概念交棒A的分镜制作，本轮排除B","reference":"实际页面动作引用"}}
```

追加 storyboardHandoffs，保存 selected/excluded 的 cueId/objectId/conceptId 快照、requestId、source 和 createdAt。status.conceptDesign.storyboardHandoff 供恢复读取并投影 current/problems，排除图片自身换图不使所选工作失效。此记录不产生 Motion／Demo／交付授权或新制作门；页面不唤醒 Agent 或渲染。

`update` 的源码发布和代码探索／采用复用已有 source closure 判断受影响对象；`_spec` 在既有预览、缓存、恢复及发布路径读取同一份 concept basis，并随任务复制图片快照。图片候选、文字策划、素材登记和 runtime bootstrap 不因此获得或要求代码制作资格。当前概念与决定 ID 进入 productionBasis，图片仍以各自真实制作源决定媒体缓存。

## 创作输入归属

每次生成或导入后及时复制并登记全部候选，包括未推荐过程图（`recommend: false`）；`.staging/creative-inputs/<round>/` 是稳定命名的版本内中转，`assets/concepts/` 才是不可变候选归属。`.codex/generated_images` 可以是图像工具的输出位置，但不能是未来改稿唯一可依赖副本。

参考图、原片参考帧与提示词／来源记录先经 `edit.files` 发布到本版 `assets/design-inputs/`，再以版本内受控路径引用；实际制作素材用 `assets/materials/`。来源字符串可以保留原工具路径、生成调用或导入出处，另保留可读的受控副本引用，不能依赖会消失的临时绝对路径重做。登记和发布沿用 update 的文件校验、版本锁、revision 与回滚，不新增存储权威。合法 `.staging`、工具缓存及历史未登记文件不自动搬迁、清理或改写。`previews/`、`cache/`、`jobs/` 与 `releases/` 保持各自 writer 职责。

## 单场审阅进度接口

`update operation: "scene-review"` 记录用户对实际呈现的审阅进度，`kind` 为 `storyboard` 或 `animation`，并提供 `cueId`、真实用户 `source` 及对应 `storyboardId` 或 `artifactId`：

```json
{"requestId":"scene-review-1","expectedRevision":12,"operation":"scene-review","kind":"storyboard","cueId":"A","storyboardId":"<当前快照ID>","source":{"channel":"review","text":"确认此场分镜","reference":"实际页面动作引用"}}
```

后端重新核验对象、Storyboard 的 `reviewInputKey` 或覆盖本场完整时长的视频 artifact 的实际输入身份及文件，追加版本内 `sceneReviews`。动画记录另存 `sceneInputKey`，绑定本场区间、重叠层、背景与审阅文字；整片其他场景变化不会单独清空本场进度。status 为记录投影 `current`／`problems`，并在 `storyboard.cues[].sceneReview` 返回 `{storyboard, animation}` 最新记录或 null。实际相关内容变化只使受影响记录失效，不改旧记录。审阅进度不进入媒体指纹、不改变概念首次资格，不授予制作、完整 Review 批准或交付，也不成为普通继续制作的新硬门。新留言仍按真实未解决反馈显示，历史单场确认不代表无条件通过。

“确认本轮，生成整片 Demo”单独使用现有 `authorize-demo`、`taskId` 与准确 Storyboard、工作／呈现／排除范围；单场确认不触发渲染。`review-submit` 只冻结已保存反馈与快照，不自动授权已完成任务的下一轮整版 Demo。整片批准与合并交付沿用当前完整 `reviewSetId` 和已有 `approve`／`authorize`／`approve-and-deliver` 语义。

## Canonical source

每个 animated cue 的 `renderAdapters.hyperframes` 指定：

- `compositionId`：本版唯一 HyperFrames composition ID；
- `compositionSrc`：`compositions/cues/<cue>.html`，承载真实文字、布局与样式；
- `motionSrc`（仅制作静帧时可缺省）：`compositions/motion/<cue>.js`，由 composition 自己引用并注册暂停时间线；
- `layoutDependencies`：其他静态/动态依赖的版本内相对路径，包括使用的字体、CSS 与影像；动态计算的引用必须显式声明。

遵循 HyperFrames `data-composition-id`、`data-duration`、`data-width`、`data-height` 及 `window.__timelines` 约定。HTML 默认原生 1920×1080；透明画面保持 HTML/body/根容器透明，不依赖播放器底色。Motion 选择器限定在本 composition 内，避免同名对象串用。

生产媒体引擎生成临时 host，挂本地 `assets/vendor/gsap.min.js`，逐 Cue 挂载 canonical composition；480p 仅在 host 缩放原生布局，交付按原生尺寸渲染。静态 Storyboard host 不加载用户脚本或 vendor JS：layout 是受限声明式内容，所有可执行或时间驱动来源属于 Motion。临时 host 只携带已登记的本地 closure，并施加 restrictive CSP；这是资源边界，不是对任意 JavaScript 行为的静态证明。临时 host 不是第二份创作源，也不记录批准。

## 输入身份

`work_model_inputs.py` 扫描显式依赖及 HTML src/href、`srcset`、CSS `url`/`image-set`、SVG 资源和 JS import 的递归本地引用。动态拼接或计算依赖必须声明，远程、缺失或未知 capability 的资源拒绝。静态 profile 只接受单帧 raster、local SVG 与字体；animated GIF、APNG 与 WebP 是 Motion 依赖。源字节变化保守视为渲染变化，不用字符串规则证明代码等价。发布时，所有可执行/时间驱动来源与改变的依赖绑定使用同一完整 source closure；任一受影响 Cue 都必须在 production scope 内。

Cue 媒体身份绑定精确 runtime pin、构建配置、规范快照、依赖字节、屏幕文字、尺寸、源帧率、时长与 alpha 声明；不包括说明、反馈、批准或全局摆放起点。预览与原生分别缓存。

时间线身份额外绑定原 FCPXML/参考视频哈希、完整/局部范围、全部重叠 Cue 的媒体身份、起点、时长与 layer。局部预览保持 Cue 本地时间与音频偏移。相同 layer 按稳定 Cue ID 排序，正式 lane 保持同样可见顺序。

## 写入与预览

静态字体使用登记的本地文件；`@font-face src: local(...)` 不在支持范围内。多帧图片、浏览器自动播放和自动跳转需要固定采样或受支持的 seekable 实现，取得制作依据本身不会使自动播放变得可确定。

固定背景的 `backgroundSample` 保存原文件 SHA 和采样时间：timeline 取指定全局时刻，`stillSrc` 取第 0 秒；最终帧另有输出 SHA。探索候选内容身份包含实际静态／Motion 闭包及背景输入。同路径替换字节也会产生新内容身份，历史反馈不会自动改绑。

在本版 `.staging/` 准备素材/源码，通过 `afterforge update` 一次校验并发布；不直接修改 manifest、缓存、artifact、decisions 或 releases。runtime bootstrap 是基础设施，runtime 配置文件由 runtime 操作拥有，普通 edit 不得改写。`runtimeIdentity` 将新 bootstrap、首次 enrollment 和与既有字节相同的 repair 同实际变更区分；精确 pin 保持不变。普通制作不调用旧 freeze / resolver / register 脚本。

`preview` 固定输入快照、释放版本锁，再逐 Cue 渲染和 FFmpeg 合成；发布前复核真实输入。日志在 jobs，缓存无批准权威。无关 metadata 并发写入保留。未纳入本轮创作的 Cue 若无可用实现则标记缺失，不自动补做，也不阻止已授权的局部讨论。工作范围内的未完成输入需明确 `allowDraft` 才能省略；任何缺失或明确排除都不能构成完整正式审阅。

完整原粗剪小样与所有重叠动画的完整单 Cue 补充小样组成 `reviewSets`。产物保存 SHA、输入键、全局范围和覆盖 Cue；重新命名旧视频或手填产物字段不能获得新输入 evidence。

## Storyboard、探索与媒体复用

Storyboard 是 canonical composition 在固定静帧时间的真实 PNG 投影；每帧状态含稳定 `id`、角色、标签、输入身份与 SHA。它不是第二份布局源。`cue.storyboard.frames` 声明 `id`、`role: hero|auxiliary`、有理数 Cue 本地 `time`、`mode: layout|motion`、`background: none|timeline`、可选 `stillSrc`、`state: {id}` 与逐帧原句 `narration`；恰有一张主审帧。`narration` 可重复，真实原声可前缀 `原声：`；未声明时审阅页明确显示“尚未标注对应旁白”，不得按时间、Cue 旁白或局部说明推断。layout 模式忽略声明的 Motion loader，`state.id` 作为静态宿主的 `data-storyboard-state` 供 canonical CSS 选择；Motion 模式仅用于已有实现的真实取帧。背景取源帧，不先制作完整视频。探索候选可有自己的隔离 composition/assets，但采用必须通过 scope 明确的事务回写 canonical source。有效 Cue 媒体按输入身份复用；缓存缺失只触发同一输入的技术渲染，不改变创意对象、确认或授权。

## Alpha 与交付

默认 `alphaExpectation.mode = transparent`；特意全屏不透明 Cue 显式用 `opaque`。可附 `samples: [{time, transparentPoints: [[x,y]], opaquePoints: [[x,y]]}]`，时间为 Cue 本地有理数秒、坐标为原生尺寸。验证实际解码像素与代表时刻，不以像素格式名代替透明性。

正式交付覆盖全部 animated cues；已验证且输入未变的 MOV 复用。源粗剪、引用、摆放、时长、DTD、媒体 SHA、包清单和批准来源在发布前核验。不可变 release 在包外保存可复现源树、审阅证据及交付事实，排除探索、日志与无关缓存。

### 局部说明与图片身份

`cue.storyboard.animationNotes` 可省略（等同空数组）。每条为 `{id, frameIds, text}`：Cue 内 ID 唯一、frameIds 非空且不重复、引用必须存在；多条说明可共享帧，无说明帧合法。帧重组与引用修订通过同一次 `edit` 提交。说明描述旁白触发、状态变化和停留，不新增 Animation Unit 或独立确认。逐帧 `narration` 由 Storyboard 快照以 `frameNarrations` 冻结，因而映射变化会使 `reviewInputKey` 失效；它不属于图片输入。

新 PNG 记录标记 `storyboardContract: 5`。`inputKey` 排除旁白、contentContext、逐帧映射和纯说明，仍覆盖制作源、资源闭包、状态、时间、背景、尺寸、role、屏幕文字和 runtime。Storyboard 的 `reviewInputKey` 覆盖有序完整帧集合、图片输入键、对象身份、旁白、逐帧映射、contentContext、总体说明和 animationNotes。发布记录保存这些文字与对应 artifactIds；页面只读快照，不混入未发布草稿。

说明变化后调用 `preview scope: "storyboard"`：固定输入副本中核验可复用 PNG 的输入键和文件 SHA，复制到新产物路径并追加 artifact/Storyboard，不覆盖旧事实。发布前复核当前输入及审阅内容。旧记录无合同标记时按合同 4 计算；复用时只用旧记录的三个审阅字段还原旧键，其他图片依赖全部重新计算，SHA 必须相符。无法证明一致则重渲。读取不迁移；旧快照不能确认改变后的审阅内容。首次资格与旧反馈继续绑定创意对象。

### 本版工作意图接口

manifest 可选 `workingIntent: {items: [...]}`。`update` 请求示例（来源须替换为实际用户原话）：

```json
{
  "requestId": "intent-1",
  "expectedRevision": 12,
  "operation": "working-intent",
  "upserts": [{
    "id": "travel",
    "kind": "focus",
    "text": "只修改穿越段",
    "locator": {"description": "自我介绍的穿越部分", "cueId": "intro", "noteId": "travel"},
    "source": {"channel": "chat", "text": "前面暂时没问题，只改穿越", "reference": "实际消息引用"}
  }],
  "removeIds": []
}
```

`upserts`、`removeIds` 可省略，默认空数组；同批 ID 不重复、不同时更新及移除。upsert 完整替换对应条目，其他条目保持；writer 生成 `updatedAt`。locator 必含可读 `description`，可选 `objectId/cueId/frameId/noteId`，引用失效不拒绝写入。接口不解析语义、不自动匹配替代条目。事务使用版本锁、requestId 和 expectedRevision，Schema 校验后原子保存；只写意图、revision、请求去重记录，不升级生产事实。工作意图不进入任何渲染／审阅指纹、确认、批准或交付计算；status 原样返回，copyFrom 不继承。
