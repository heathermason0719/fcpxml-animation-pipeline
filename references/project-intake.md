# 项目入口报告契约

## 用途

`scripts/intake_project.py` 对用户指定的投放版本目录执行只读扫描，并把已发现材料、时间线证据、就绪状态和必要问题输出为 JSON。该目录通常是实际项目根目录下的 `user-inbox/YYYY-MM-DD_Vn/`，由用户创建、选择和维护。入口报告用于决定能否开始后续内容分析，不是最终 `animation-manifest.json`。

## 命令与退出码

```bash
python3 scripts/intake_project.py --flat "/absolute/project/workspace/user-inbox/YYYY-MM-DD_Vn"
```

- 退出码 `0`：`status` 为 `ready`；
- 退出码 `2`：`status` 为 `blocked`；
- JSON 写入 stdout；脚本不在版本目录或 `user-inbox/` 中创建文件。
- `--flat` 只检查版本目录根层，忽略普通子目录；用于落实用户投放材料平铺约定，同时保留脚本原有递归模式供既有调用使用。

## 报告字段

| 字段 | 含义 |
|---|---|
| `schema_version` | 当前入口报告契约版本；V1 为 `1.0`。 |
| `workspace` | 规范化后的绝对工作区路径。 |
| `status` | `ready` 或 `blocked`。 |
| `selected` | 唯一选中的 FCPXML/FCPXMLD 与低码参考视频。 |
| `candidates` | 扫描发现的必要输入候选，用于解释自动选择或歧义。 |
| `materials` | 已发现的旁白/转写来源和设计 notes。 |
| `timeline` | 项目规格、精确时间、空缺、文字和 Marker 证据。 |
| `ambiguities` | 不能可靠分类的具体时间线文字及原因；不等于入口阻塞。 |
| `warnings` | 可以继续但后续需要注意的限制。 |
| `blockers` | 缺失、同级歧义或无法解析的必要输入及阻塞原因。 |
| `questions` | 只从 `blockers` 派生的最小用户问题。 |

## 必要输入选择

FCPXML/FCPXMLD 和低码粗剪参考视频各自必须能够唯一确定。目录中只有一个候选时直接使用；存在多个候选时，根据文件名和目录中的 `rough`、`proxy`、`preview`、`reference`、`粗剪`、`参考`、`低码` 等信号排序。最高分只有一个时自动选择；同等可信的最高分候选不得猜测，必须产生 `ambiguous_*` blocker。

旁白材料和设计材料不是必要输入候选，不参与入口阻塞。一个已存在的 SRT、时间线 caption、转写稿或文稿只要足以支撑后续对应关系，就不再索取其他格式。

## 时间线空缺

- `explicit`：FCPXML spine 中已有的 `<gap>`；
- `implicit`：相邻 primary storyline 子项之间由 `offset` 与前项结束位置形成的内部时间洞。

所有时间保留为 FCPXML 风格的精确有理数，例如 `1/25s`、`3s`。入口只识别并报告空缺，不改变 spine 顺序、素材位置或时长。

## 时间线文字分类

每个 `text_items` 条目输出 `classification` 和 `evidence`：

- `narration_subtitle`：来自 `<caption>`，名称/角色含字幕信号，或规范化文字与外部旁白材料匹配；
- `design_text`：名称/角色含动画、设计、动效、备注等信号；
- `ambiguous`：没有足够证据，或旁白证据与设计证据冲突。

外部匹配会去除空白与标点后比较文本，但不会把字体、屏幕位置或视觉直觉当作确定性证据。歧义条目必须保留原文、时间位置和原因，供后续具体判断。

Marker、chapter marker、keyword 等单独保存在 `timeline.markers`，作为潜在主观设计约束，不自动等同于最终动画指令。

## Blocker 与 warning 边界

以下情况阻塞入口：

- 工作区不存在；
- 找不到 FCPXML/FCPXMLD；
- 找不到低码粗剪参考视频；
- 必要输入存在多个同等可信候选；
- 选中的 FCPXML/FCPXMLD 无法解析或缺少 sequence/spine。

没有 animation brief、逐镜设计稿、品牌资料或重复旁白格式不构成 blocker。没有现成旁白文本但可以在后续利用参考视频音频建立转写时，只生成 warning，不立即询问用户。
