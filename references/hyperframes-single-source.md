# HyperFrames 单一布局源协议

## 目标

A11 与 A12 不再分别维护静态 storyboard frame 和正式 animation composition。每条需要动画的 cue 只有一份正式 HTML composition，CSS 终态就是布局 ground truth；A11 review projection 和 A12 合成入口都引用它。

## 目录与职责

```text
compositions/
├── cues/<cue>.html       # 唯一正式布局、真实文案和终态 CSS
├── motion/<cue>.js       # 只描述时间、变换和显隐，不重写布局
├── review/<cue>.html     # 自动生成；854×480 原画 still + 正式 cue projection
└── delivery/<cue>.html   # 自动生成；1920×1080 单 cue 透明渲染 host
approvals/a11/            # 用户审核的主审帧与必要辅助帧
animation-manifest.json   # cue 最终动画说明、路径、heroTime、依赖和 layout lock
STORYBOARD.md             # 自动生成审阅索引
index.html                # 自动生成正式合成预览入口
```

`source-only` cue 只生成 review projection，不创建 cue composition、motion 文件或正式渲染槽位。

animated cue 的 canonical root 尺寸必须与 `project.delivery` 完全一致。A11 与 A12 的 854×480 host 使用 manifest 尺寸计算的确定性轴向比例挂载该 1920×1080 cue；review 和 delivery 都不得复制或重写 cue DOM/CSS。

## A11 → A12

1. 在 `compositions/cues/` 完成真实文案、比例、排版、颜色和终态 CSS。若用户措辞或已确认约束仍支持会实质改变最终构图、必要内容、运动方式或特殊约束的多种合理解释，先提出一个聚焦问题，澄清后再选方案和生成 A11 审核帧；不要因为易于返工或之后可 comment 就自行选义。结果明确而只剩实现细节时直接完成，不新增确认。
2. 在 manifest 设置 `workflowState: layout-built`、`heroTime` 和 cue 级 `finalAnimationDescription`，运行 `sync_storyboard.py`。该说明只写澄清后的最终呈现，不写澄清或讨论历史，也不拆成固定字段。
3. 用候选主审帧逐 cue 运行 `layout_lock.py freeze`；主审帧无法表达的其他重要静态状态以可重复的 `--auxiliary-frame ID=LABEL=PATH` 加入。lock 冻结 composition、样式、字体、生成的 review projection、投影尺寸规格及全部审核帧 SHA-256；随后由用户在单 Vn Review 中批准，形成与锁绑定的 canonical A11 evidence。lock 存在或 legacy `reviews.a11` 都不能单独完成 A11。
4. 在独立 `compositions/motion/` 中实现运动。允许 `transform`、`opacity`、clip/mask 进度等不会重新排版的属性；禁止通过 motion 改写 `left/top/width/height/font/gap/display` 等布局属性。
5. `assemble_hyperframes.py` 把相同的 canonical cue compositions 按 FCPXML 有理数时间装入 `index.html`。不得复制 A11 DOM/CSS 来制作另一套 A12 布局。

`sync_storyboard.py` 只覆盖带 generated marker 的 review 文件；手写 review 文件会阻塞，避免误删人工内容。

## 确定性命令

```bash
python3 scripts/sync_storyboard.py "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/layout_lock.py freeze "/absolute/AfterForge/YYYY-MM-DD_Vn" "cue_id" "/absolute/approved-hero.png"
python3 scripts/layout_lock.py freeze "/absolute/AfterForge/YYYY-MM-DD_Vn" "cue_id" "/absolute/approved-hero.png" --hero-id final --hero-label "最终状态" --auxiliary-frame earlier="较早状态"=/absolute/auxiliary.png
python3 scripts/layout_lock.py approve "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/layout_lock.py verify "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/assemble_hyperframes.py "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/sync_delivery.py "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/validate_hyperframes_adapter.py "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/render_animations.py "/absolute/AfterForge/YYYY-MM-DD_Vn"
```

旧版迁移：

```bash
python3 scripts/migrate_single_source.py "/absolute/AfterForge/YYYY-MM-DD_Vn" \
  --hero-time cue_1=1.2 --hero-time cue_2=2.0
python3 scripts/migrate_delivery_layout.py "/absolute/AfterForge/YYYY-MM-DD_Vn"
```

迁移从既有 `compositions/animation/` 提取最新正式布局和 inline timeline，分别写入 `cues/` 与 `motion/`，但保留旧 `frames/`、`animation/` 原文件作为迁移对照。迁移完成仍需用户确认新 review projection 与已通过 A11 的视觉结果一致，之后才能建立正式 layout lock。

`migrate_delivery_layout.py` 处理仍以 854×480 为 canonical root 的单一布局源 Vn：它先全量预检，再把既有布局包装在 1920×1080 canonical root 内，并清除旧 lock，但在 `layoutRevision` 保留旧修订基线。迁移后的 854×480 hero 与完整动画审阅必须由用户重新确认；再次冻结时从保留基线递增，因此旧 revision 1 会生成 revision 2，而不是重新从 1 开始。最终 MOV 直接由 1920×1080 delivery host 渲染，禁止 `--resolution` 和任何放大滤镜。

## 检查边界

`validate_hyperframes_adapter.py` 负责阻止路径缺失、ID/时间线不一致、canonical 尺寸不等于 delivery、review 未引用 canonical cue、motion 改布局、依赖漏记和 layout lock 漂移。`workflow_status.py` 负责验证 A11、A12 artifact、A13、A14 与 D-stage evidence 的当前有效性；文件存在不等于 stage completed。`validate_delivery.py` 负责阻止错误尺寸、非 ProRes 4444、无 alpha、错误帧率和超出一帧的时长。HyperFrames 自身 lint/check 继续负责运行时与框架契约。任何机器检查都不能替代用户的 A11/A13 视觉与运动验收。
