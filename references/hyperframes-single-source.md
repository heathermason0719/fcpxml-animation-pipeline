# HyperFrames 单一布局源协议

## 目标

A11 与 A12 不再分别维护静态 storyboard frame 和正式 animation composition。每条需要动画的 cue 只有一份正式 HTML composition，CSS 终态就是布局 ground truth；A11 review projection 和 A12 合成入口都引用它。

## 目录与职责

```text
compositions/
├── cues/<cue>.html       # 唯一正式布局、真实文案和终态 CSS
├── motion/<cue>.js       # 只描述时间、变换和显隐，不重写布局
└── review/<cue>.html     # 自动生成；原画 still + 正式 cue projection
approvals/a11/            # 用户批准的 hero poster
animation-manifest.json   # cue 状态、路径、heroTime、依赖和 layout lock
STORYBOARD.md             # 自动生成审阅索引
index.html                # 自动生成正式合成预览入口
```

`source-only` cue 只生成 review projection，不创建 cue composition、motion 文件或正式渲染槽位。

## A11 → A12

1. 在 `compositions/cues/` 完成真实文案、比例、排版、颜色和终态 CSS。
2. 在 manifest 设置 `workflowState: layout-built` 和 `heroTime`，运行 `sync_storyboard.py`。
3. 用户通过 A11 后，用批准截图逐 cue 运行 `layout_lock.py freeze`；它冻结 composition、样式和字体依赖的 SHA-256。最后一个 animated cue 锁定后，脚本自动把项目级 A11 标记为 approved；迁移后已有锁可用 `layout_lock.py approve` 补齐该状态。
4. 在独立 `compositions/motion/` 中实现运动。允许 `transform`、`opacity`、clip/mask 进度等不会重新排版的属性；禁止通过 motion 改写 `left/top/width/height/font/gap/display` 等布局属性。
5. `assemble_hyperframes.py` 把相同的 canonical cue compositions 按 FCPXML 有理数时间装入 `index.html`。不得复制 A11 DOM/CSS 来制作另一套 A12 布局。

`sync_storyboard.py` 只覆盖带 generated marker 的 review 文件；手写 review 文件会阻塞，避免误删人工内容。

## 确定性命令

```bash
python3 scripts/sync_storyboard.py "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/layout_lock.py freeze "/absolute/AfterForge/YYYY-MM-DD_Vn" "cue_id" "/absolute/approved-hero.png"
python3 scripts/layout_lock.py approve "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/layout_lock.py verify "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/assemble_hyperframes.py "/absolute/AfterForge/YYYY-MM-DD_Vn"
python3 scripts/validate_hyperframes_adapter.py "/absolute/AfterForge/YYYY-MM-DD_Vn"
```

旧版迁移：

```bash
python3 scripts/migrate_single_source.py "/absolute/AfterForge/YYYY-MM-DD_Vn" \
  --hero-time cue_1=1.2 --hero-time cue_2=2.0
```

迁移从既有 `compositions/animation/` 提取最新正式布局和 inline timeline，分别写入 `cues/` 与 `motion/`，但保留旧 `frames/`、`animation/` 原文件作为迁移对照。迁移完成仍需用户确认新 review projection 与已通过 A11 的视觉结果一致，之后才能建立正式 layout lock。

## 检查边界

`validate_hyperframes_adapter.py` 负责阻止路径缺失、ID/时间线不一致、review 未引用 canonical cue、motion 改布局、依赖漏记和 layout lock 漂移。HyperFrames 自身 lint/check 继续负责运行时与框架契约。两者均不能替代 A11 审美验收，也不能从像素结果证明所有视觉意图正确。
