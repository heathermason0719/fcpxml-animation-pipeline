# 架构基线

## 文档职责

本文档定义 `fcpxml-animation-pipeline` 的长期架构基线：系统分层、组件职责、核心数据流、V1 输入输出、渲染后端边界和 FCPXML 回填边界。后续实现可以细化内部技术方案，但不得在未更新 `docs/PROJECT.md` 和 `docs/DECISIONS.md` 的情况下改变这里确定的核心设计。

本文档不记录开发进度；当前实现状态以 `docs/CURRENT.md` 为准。

## 总体架构

项目采用“Codex Skill + 确定性脚本工具链”的结构。Skill 负责需要理解语义、上下文和创作意图的判断；脚本负责必须稳定、可重复、可校验的机械操作。二者通过 `animation-manifest.json` 解耦。

```text
项目输入
├── rough-cut.fcpxml / .fcpxmld
├── narration.wav
├── captions.srt 或时间线字幕
├── animation-brief.yaml
└── 可选：字体、Logo、配色规范
             ↓
fcpxml-animation-pipeline Skill
├── 分析时间线
├── 对齐旁白、字幕与动画要求
├── 细化动画设计
├── 生成统一动画清单
├── 调用 HyperFrames
├── 转码透明动画
├── 回填 FCPXML
└── 完整性检查
             ↓
项目输出
├── completed.fcpxml
├── animations/*.mov
├── audio/*.wav
├── hyperframes-project/
└── animation-manifest.json
```

## Skill 与 scripts 分工

### Skill 负责创作性判断与流程编排

`SKILL.md` 负责指导 Agent：

- 理解口播内容及其表达目的；
- 结合字幕和粗略动画要求细化画面表现；
- 判断哪些位置保留电影原片，哪些位置使用文字动画、图形演示或其他视觉辅助；
- 统一动画节奏、信息层级和视觉风格；
- 在信息不足或无法可靠对齐时生成明确的人工确认项；
- 决定何时先输出动画清单或低分辨率预览供用户确认；
- 按既定顺序调用确定性脚本，并根据验证结果决定是否继续。

Skill 不自行承担 FCPXML 时间运算、XML 拼装、媒体转码或文件完整性校验。

### scripts 负责确定性操作

V1 计划由以下脚本组件承担机械操作；名称表达职责，具体模块边界可在实现计划中细化，但不得改变 Skill 与脚本的分工原则。

- `inspect_fcpxml.py`：解析画幅、帧率、时间基准、故事线和素材引用；
- `align_narration.py`：对齐旁白、字幕和动画提示；
- `build_manifest.py`：生成并校验统一动画清单；
- `scaffold_hyperframes.py`：根据动画清单创建 HyperFrames 场景；
- `render_animations.py`：检查并渲染动画；
- `transcode_alpha.py`：将透明动画转换为 ProRes 4444；
- `inject_fcpxml.py`：将动画和音效引用写入新的时间线；
- `validate_delivery.py`：检查素材路径、帧率、时长、引用关系和 XML 合法性。

脚本必须把原始项目输入视为只读，并产生可单独检查的新输出。

## `animation-manifest.json` 中间层

`animation-manifest.json` 是内容分析、动画渲染与 FCPXML 回填之间的稳定契约，也是项目泛用性的核心。分析阶段先生成清单，渲染后端消费清单，回填阶段同时依据清单和实际渲染结果定位素材。

概念结构如下：

```json
{
  "project": {
    "width": 1920,
    "height": 1080,
    "frameRate": 25
  },
  "cues": [
    {
      "id": "anim_001",
      "start": "38.20",
      "duration": "4.80",
      "script": "我们看到的世界，真的是世界本身吗？",
      "captionRange": [16, 18],
      "type": "kinetic-title",
      "visualIntent": "空间逐渐收紧，制造被监视感",
      "text": ["我们看到的世界", "真的是世界本身吗？"],
      "sound": "low-impact",
      "layer": 2
    }
  ]
}
```

正式实现前必须把该概念结构收敛为可验证的数据模式。至少应表达：

- 项目画幅、帧率和时间基准；
- 每个动画提示的稳定标识、时间位置和时长；
- 对应口播、字幕范围和用户原始要求；
- 动画类型、视觉意图、展示文字和层级；
- 音乐或音效提示；
- 人工确认状态；
- 渲染结果及其可回填引用。

所有写入 FCPXML 的时间最终必须转换为符合源项目时间基准的精确表示；示例中的十进制字符串只展示概念，不定义最终回写算法。

## 渲染后端边界

HyperFrames 是 V1 的动画渲染后端，但不是整个系统的架构中心。它负责根据动画清单生成可预览、可渲染的动画工程和素材，不负责：

- 解析或修改 FCPXML；
- 决定口播与字幕的语义对应关系；
- 定义整个项目的中间数据结构；
- 直接操作 Final Cut Pro 资源库。

未来可以用 Apple Motion 模板、After Effects、Remotion、Blender 或人工制作替换渲染后端。替换时只应新增或更换渲染适配层，不应重写前端分析、`animation-manifest.json` 或 FCPXML 回填逻辑。

V1 中，HyperFrames 先生成透明动画，交付前转换为适合 Final Cut Pro 合成的 ProRes 4444 MOV。

## FCPXML 回填边界

回填阶段只根据已经确认的动画清单和实际存在的渲染素材工作，并遵守以下边界：

- 永不覆盖原始 FCPXML 或 FCPXMLD；
- 输出一个新命名的 Final Cut Pro 项目描述；
- 保留原有粗剪结构，不把动画生成流程变成重新剪辑电影原片；
- 将动画作为可继续调整的连接片段放置在对应画面上方；
- 将音效和音乐素材以独立引用保留，便于后续混音；
- 使用可迁移、可校验的项目素材路径；
- 回填前后校验项目帧率、时间基准、总时长、片段位置和素材引用；
- 不直接修改 Final Cut Pro 资源库，最终由用户导入新 FCPXML；
- 无法可靠对齐或无法验证的项目不得静默写入，必须进入人工确认清单。

## V1 工作流

V1 采用先审阅、后高质量渲染与回填的两阶段工作模式。

### 阶段一：分析与确认

1. 检查 FCPXML/FCPXMLD、旁白 WAV、SRT 或时间线字幕、YAML 动画提示及可选视觉规范；
2. 解析项目规格、时间线、素材引用和字幕信息；
3. 对齐旁白、字幕与用户提供的大致动画时间点；
4. 细化动画设计并生成 `animation-manifest.json`；
5. 输出时间线分析、逐句对齐结果、动画清单和必要的低分辨率预览；
6. 收集用户确认，并保留无法可靠判断的人工确认项。

### 阶段二：渲染、回填与验证

1. 根据已确认清单创建并渲染 HyperFrames 动画；
2. 将透明动画转换为 ProRes 4444 MOV；
3. 生成独立音效或音乐素材；
4. 将渲染结果注册并写入新的 FCPXML；
5. 验证 XML、素材引用、时间位置、帧率和总时长；
6. 交付完整、可迁移的项目目录，由用户导入 Final Cut Pro 继续检查和编辑。

## V1 范围

第一版固定支持以下主流程：

- 输入：FCPXML/FCPXMLD、旁白 WAV、SRT 字幕、YAML 动画提示；
- 视觉场景：以 16:9 横屏口播类视频为首要目标；
- 渲染：HyperFrames；
- 透明动画交付：ProRes 4444 MOV；
- 回填：生成新的 FCPXML 和关联媒体，不覆盖原始输入；
- 审阅：在批量高质量渲染前确认动画清单和必要的低分辨率预览；
- 异常处理：不能可靠对齐的内容进入人工确认清单。

V1 不包含 Plugin 打包、多用户分发、直接修改 Final Cut Pro 资源库，也不扩展为通用视频编辑平台。

## 预期 Skill 目录结构

以下结构是后续实现的边界说明，不代表相关文件已经存在：

```text
fcpxml-animation-pipeline/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
├── references/
├── assets/
└── docs/
    ├── PROJECT.md
    ├── CURRENT.md
    ├── DECISIONS.md
    └── ARCHITECTURE.md
```

遵循渐进披露原则：`SKILL.md` 只保留核心工作流和资源导航；详细数据模式、FCPXML 约束和渲染后端说明按需放入 `references/`；确定性实现放入 `scripts/`；输出模板或可复用工程资源放入 `assets/`。

## 架构验收原则

后续实现必须能够证明：

- Skill 的创作性判断与脚本的确定性操作边界清楚；
- `animation-manifest.json` 可以独立审阅、验证并驱动渲染和回填；
- HyperFrames 可以被其他渲染后端替换而不破坏前后流程；
- 原始输入不被修改，输出可回退；
- FCPXML 的时间与素材引用经过自动校验；
- 最终交付能够由 Final Cut Pro 实际导入并继续编辑。
