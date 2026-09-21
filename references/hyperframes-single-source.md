# 新版制作源与媒体合同

适用于 manifest 3.0 / work model 2.1.0。schema 2.0 按 [旧单一布局协议](legacy/hyperframes-single-source-v2.md) 解释。

## Canonical source

每个 animated cue 的 `renderAdapters.hyperframes` 指定：

- `compositionId`：本版唯一 HyperFrames composition ID；
- `compositionSrc`：`compositions/cues/<cue>.html`，承载真实文字、布局与样式；
- `motionSrc`（首次静态设计可缺省）：`compositions/motion/<cue>.js`，由 composition 自己引用并注册暂停时间线；
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

Storyboard 是 canonical composition 在固定静帧时间的真实 PNG 投影；每帧状态含稳定 `id`、角色、标签、输入身份与 SHA。它不是第二份布局源。`cue.storyboard.frames` 声明 `id`、`role: hero|auxiliary`、有理数 Cue 本地 `time`、`mode: layout|motion`、`background: none|timeline`、可选 `stillSrc` 与 `state: {id}`；恰有一张主审帧。layout 模式忽略声明的 Motion loader，`state.id` 作为静态宿主的 `data-storyboard-state` 供 canonical CSS 选择；Motion 模式仅用于已有实现的真实取帧。背景取源帧，不先制作完整视频。探索候选可有自己的隔离 composition/assets，但采用必须通过 scope 明确的事务回写 canonical source。有效 Cue 媒体按输入身份复用；缓存缺失只触发同一输入的技术渲染，不改变创意对象、确认或授权。

## Alpha 与交付

默认 `alphaExpectation.mode = transparent`；特意全屏不透明 Cue 显式用 `opaque`。可附 `samples: [{time, transparentPoints: [[x,y]], opaquePoints: [[x,y]]}]`，时间为 Cue 本地有理数秒、坐标为原生尺寸。验证实际解码像素与代表时刻，不以像素格式名代替透明性。

正式交付覆盖全部 animated cues；已验证且输入未变的 MOV 复用。源粗剪、引用、摆放、时长、DTD、媒体 SHA、包清单和批准来源在发布前核验。不可变 release 在包外保存可复现源树、审阅证据及交付事实，排除探索、日志与无关缓存。

### 局部说明与图片身份

`cue.storyboard.animationNotes` 可省略（等同空数组）。每条为 `{id, frameIds, text}`：Cue 内 ID 唯一、frameIds 非空且不重复、引用必须存在；多条说明可共享帧，无说明帧合法。帧重组与引用修订通过同一次 `edit` 提交。说明描述旁白触发、状态变化和停留，不新增 Animation Unit 或独立确认。

新 PNG 记录标记 `storyboardContract: 5`。`inputKey` 排除旁白、contentContext 和纯说明，仍覆盖制作源、资源闭包、状态、时间、背景、尺寸、role、屏幕文字和 runtime。Storyboard 的 `reviewInputKey` 覆盖有序完整帧集合、图片输入键、对象身份、旁白、contentContext、总体说明和 animationNotes。发布记录保存这些文字与对应 artifactIds；页面只读快照，不混入未发布草稿。

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
