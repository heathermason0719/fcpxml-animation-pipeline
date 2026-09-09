# 新版制作源与媒体合同

适用于 manifest 3.0 / work model 2.0。schema 2.0 按 [旧单一布局协议](legacy/hyperframes-single-source-v2.md) 解释。

## Canonical source

每个 animated cue 的 `renderAdapters.hyperframes` 指定：

- `compositionId`：本版唯一 HyperFrames composition ID；
- `compositionSrc`：`compositions/cues/<cue>.html`，承载真实文字、布局与样式；
- `motionSrc`：`compositions/motion/<cue>.js`，由 composition 自己引用并注册暂停时间线；
- `layoutDependencies`：其他静态/动态依赖的版本内相对路径，包括使用的字体、CSS、影像与 vendor。

遵循 HyperFrames `data-composition-id`、`data-duration`、`data-width`、`data-height` 及 `window.__timelines` 约定。HTML 默认原生 1920×1080；透明画面保持 HTML/body/根容器透明，不依赖播放器底色。Motion 选择器限定在本 composition 内，避免同名对象串用。

媒体引擎生成临时 host，挂本地 `assets/vendor/gsap.min.js`，逐 Cue 挂载 canonical composition；480p 仅在 host 缩放原生布局，交付按原生尺寸渲染。临时 host 不是第二份创作源，也不记录批准。

## 输入身份

`work_model_inputs.py` 扫描显式依赖及 HTML src/href、CSS url、JS import 的递归本地引用。动态拼接依赖必须声明，远程或缺失资源拒绝。源字节变化保守视为渲染变化，不用字符串规则证明代码等价。

Cue 媒体身份绑定精确 runtime pin、构建配置、规范快照、依赖字节、屏幕文字、尺寸、源帧率、时长与 alpha 声明；不包括说明、反馈、批准或全局摆放起点。预览与原生分别缓存。

时间线身份额外绑定原 FCPXML/参考视频哈希、完整/局部范围、全部重叠 Cue 的媒体身份、起点、时长与 layer。局部预览保持 Cue 本地时间与音频偏移。相同 layer 按稳定 Cue ID 排序，正式 lane 保持同样可见顺序。

## 写入与预览

在本版 `.staging/` 准备素材/源码，通过 `afterforge update` 一次校验并发布；不直接修改 manifest、缓存、artifact、decisions 或 releases。普通制作不调用旧 freeze / resolver / register 脚本。

`preview` 固定输入快照、释放版本锁，再逐 Cue 渲染和 FFmpeg 合成；发布前复核真实输入。日志在 jobs，缓存无批准权威。无关 metadata 并发写入保留。未完成 Cue 只能在明确 `allowDraft` 讨论稿中省略，产物标记缺失 Cue，不能构成正式审阅集合。

完整原粗剪小样与所有重叠动画的完整单 Cue 补充小样组成 `reviewSets`。产物保存 SHA、输入键、全局范围和覆盖 Cue；重新命名旧视频或手填产物字段不能获得新输入 evidence。

## Alpha 与交付

默认 `alphaExpectation.mode = transparent`；特意全屏不透明 Cue 显式用 `opaque`。可附 `samples: [{time, transparentPoints: [[x,y]], opaquePoints: [[x,y]]}]`，时间为 Cue 本地有理数秒、坐标为原生尺寸。验证实际解码像素与代表时刻，不以像素格式名代替透明性。

正式交付覆盖全部 animated cues；已验证且输入未变的 MOV 复用。源粗剪、引用、摆放、时长、DTD、媒体 SHA、包清单和批准来源在发布前核验。不可变 release 在包外保存可复现源树、审阅证据及交付事实，排除探索、日志与无关缓存。
