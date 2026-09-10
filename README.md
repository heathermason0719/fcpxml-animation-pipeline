# AfterForge · FCPXML Animation Pipeline

用同一份制作源理解脚本、试做动画、接收反馈并生成可导入 Final Cut Pro 的透明动画包。以“电影系列 → 单集 → 制作版本 → 修改与交付”组织工作，支持文案起步和粗剪起步。

新版使用 manifest 3.0 / work model 2.0。静态未批准可以试做动态；改说明不重渲，改摆放复用动画媒体；完整审阅批准后才制作正式交付。旧 schema 2.0 工程原位只读展示，继续制作明确创建新副本，不继承旧授权。

## 使用

需要本地 Python、FFmpeg/ffprobe、Node/npm，以及明确版本的 HyperFrames。Python 依赖在 `requirements.txt`。依赖安装和 Skill 安装需单独授权；命令不会探测 latest 或自动迁移旧工程。

```bash
.venv/bin/python scripts/afterforge.py open "/workspace/AfterForge"
.venv/bin/python scripts/afterforge.py open "/workspace/AfterForge" --request-file /tmp/open.json
.venv/bin/python scripts/afterforge.py status "<version-root>"
.venv/bin/python scripts/afterforge.py update "<version-root>" --request-file /tmp/update.json
.venv/bin/python scripts/afterforge.py preview "<version-root>" --request-file /tmp/preview.json
.venv/bin/python scripts/serve_workflow_review.py "/workspace/AfterForge" --port 8765
.venv/bin/python scripts/afterforge.py deliver "<version-root>" --request-file /tmp/deliver.json
.venv/bin/python scripts/afterforge.py resume "<version-root>" --request-file /tmp/resume.json
```

CLI 与 Review 共用业务层；结构化写入使用 `requestId` 和 `expectedRevision`。相同请求重试去重，冲突保留原草稿和位置。CLI 返回生成的稳定 ID、版本根目录、状态与产物路径。

无粗剪起步的 open 请求：

```json
{"requestId":"episode-01","expectedRevision":0,"title":"电影系列","episodeTitle":"01 开场","brief":{"summary":"本集希望观众理解什么","segments":[]}}
```

绑定粗剪时增加用户明确选择的 `inputDirectory`；同一集新版本使用 `episodeId`，可用 `copyFrom` 继承创意源。`user-inbox/` 从不写入。源 FCPXML、参考视频与旁白材料在制作版内保存所需副本。

从旧工程创建副本时，仅继承视觉与运动默认；新副本会替换已知旧审核模板，并明确旧阶段文字不再是执行指令。原规范不改，旧规范路径和冻结哈希不进入新副本。新建版从 `工程/frame.md` 读取系列默认；既有项目的 AGENTS/CLAUDE 和根层规范须在明确授权的衔接清理中同步，普通 open 不自动覆盖或迁移这些文件。

初次制作通过 `update` 的 `operation: "runtime", version: "X.Y.Z"` 初始化本地已缓存的精确 runtime。若该安装不包含 GSAP，可把现有本地 vendor 放到本版 `.staging/` 并传 `vendorSource`。缺少 runtime 时明确报错，不自动安装。

Agent 把代码和素材准备到 `.staging/`，用 `operation: "edit"` 的 `files: [{path, source}]` 与 `patch: {brief, cues, project}` 一次发布。无需手改 manifest、写连接脚本或维护阶段字段。具体源格式见 [制作源合同](references/hyperframes-single-source.md)。

完整预览请求为 `{"requestId":"preview-1","expectedRevision":1,"scope":"full"}`；局部指定 `cueIds`、`segmentIds` 或有理数 `range`。完整小样与重叠 Cue 的完整补充小样组成审阅集合。`allowDraft` 可生成标明未完成部分的讨论稿，不能批准交付。

合并批准与授权的交付请求：

```json
{"requestId":"deliver-1","expectedRevision":2,"decision":{"kind":"approve-and-deliver","reviewSetId":"<当前集合ID>","source":{"channel":"chat","text":"用户明确要求批准并制作这版交付的原话","reference":"对应消息引用"}}}
```

示例中的 revision、ID 与原话必须来自真实当前状态和用户决定。只认可画面时记录 approve，之后可以 authorize；不得用示例文字制造授权。恢复任务传 `jobId` 和当前 revision。

## 文件与交付

```text
AfterForge/
├── AGENTS.md, CLAUDE.md
├── 交付/<集名--ID>/交付0001/<集名>.fcpxmld
└── 工程/
    ├── project.json, 创作记忆.md, frame.md
    └── episodes/<episodeId>/<versionId>/
        ├── animation-manifest.json, compositions/, assets/
        ├── previews/, cache/, jobs/
        └── releases/
```

页面集中展示脚本思路、本轮变化、小样、反馈和交付；支持从当前版本内容导出 Markdown 脚本、局部时间定位、多 Cue 评论、版本对照与独立 MOV 下载。480p 预览保留原粗剪声音；正式交付为源帧率 1920×1080 ProRes 4444。包内仅 Info.fcpxml 与 MOV，源时间线不改。

快照记录实际依赖、已批准审阅和完整素材。相同输入复用经核验包；草稿继续修改不会覆盖历史包，也不必等待旧包 FCP 验收。实际导入用 `update operation: "decision", kind: "accept-import"` 记录；首次协议 2 的 FCP re-export 用 `operation: "roundtrip"` 验证并建立基线。自动测试不代替实际 FCP 验收。

## 开发验证

首次依赖设置经授权后执行 `python3 -m venv .venv` 和 `.venv/bin/python -m pip install -r requirements.txt`。常规检查：

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
.venv/bin/python scripts/sync_workflow_stage_contract.py --check
```

另有显式、隔离的真实一分钟样片回归；只使用合成媒体，输出目录不得已存在：

```bash
.venv/bin/python -B tests/work_model_real_smoke.py --run --root /private/tmp/afterforge-real-check --runtime 0.8.33 --gsap-source /absolute/local/gsap.min.js
```

不修改已交付《楚门》工程，不默认 commit、push、安装、迁移或 FCP 导入。十分钟以上实际制作和协议 2 实际 FCP 往返仍需另行验证。

开发约束见 [AGENTS.md](AGENTS.md)，项目边界见 [PROJECT](docs/PROJECT.md)，可靠状态见 [CURRENT](docs/CURRENT.md)，接口与实现见 [ARCHITECTURE](docs/ARCHITECTURE.md)，决策适用范围见 [DECISIONS](docs/DECISIONS.md)。
